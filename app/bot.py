"""Telegram command handling; all inventory mutations run in one DB transaction."""
from __future__ import annotations

import hashlib
import hmac
import json
import re
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import func, select, text
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.storage import Movement, Owner, ProcessedUpdate, Product

LOCAL_TZ = ZoneInfo("Asia/Bangkok")
MAX_QTY = 1_000_000_000
MAX_DAYS = 366
LIST_PAGE_SIZE = 25
STATS_PAGE_SIZE = 30
USAGE = (
    "库存机器人 · 使用说明\n"
    "/add 商品ID 数量 — 入库（自动新建商品）\n"
    "/remove 商品ID 数量 — 出库\n"
    "/stock 商品ID — 查询库存\n"
    "/list [页码] — 分页列出所有商品\n"
    "/delete 商品ID — 删除商品，保留流水\n"
    "/history [商品ID] — 最近20条出入库记录\n"
    "/stats YYYY-MM-DD YYYY-MM-DD [页码] — 每日统计（UTC+7）\n"
    "/myid — 查看自己的 Telegram ID\n"
    "首次使用请在私聊发送 /claim 一次性代码。"
)


def claim_code(bot_token: str) -> str:
    """One-time bootstrap code. Rotate bot token if this code was disclosed."""
    return hmac.new(bot_token.encode(), b"kucunbot-owner-claim-v1", hashlib.sha256).hexdigest()[:20]


def webhook_secret(bot_token: str) -> str:
    return hmac.new(bot_token.encode(), b"kucunbot-webhook-v1", hashlib.sha256).hexdigest()


def split_message(text: str, limit: int = 3500) -> list[str]:
    """Split at line boundaries, including unusually long individual lines."""
    chunks: list[str] = []
    current = ""
    for line in text.splitlines(keepends=True):
        while len(line) > limit:
            if current:
                chunks.append(current.rstrip())
                current = ""
            chunks.append(line[:limit])
            line = line[limit:]
        if len(current) + len(line) > limit:
            chunks.append(current.rstrip())
            current = ""
        current += line
    if current:
        chunks.append(current.rstrip())
    return chunks or [""]


def _parse_qty(raw: str) -> int | None:
    if not re.fullmatch(r"[1-9][0-9]*", raw):
        return None
    n = int(raw)
    return n if n <= MAX_QTY else None


def _parse_page(raw: str) -> int | None:
    if not re.fullmatch(r"[1-9][0-9]*", raw) or len(raw) > 6:
        return None
    return int(raw)


def _valid_id(raw: str) -> bool:
    return bool(raw and len(raw) <= 64 and not any(c.isspace() or ord(c) < 32 for c in raw))


def _insert_if_missing(session: Session, product_id: str) -> None:
    engine_name = session.get_bind().dialect.name
    if engine_name == "mysql":
        session.execute(mysql_insert(Product).values(product_id=product_id, quantity=0).prefix_with("IGNORE"))
    elif engine_name == "sqlite":
        session.execute(sqlite_insert(Product).values(product_id=product_id, quantity=0).on_conflict_do_nothing())
    else:
        # Supported deployments use MySQL or SQLite. Explicit failure avoids a silent race.
        raise RuntimeError(f"Unsupported database dialect: {engine_name}")


def _date(raw: str):
    try:
        parsed = datetime.strptime(raw, "%Y-%m-%d").date()
        if parsed.isoformat() != raw:
            return None
        return parsed
    except ValueError:
        return None


def _stats(session: Session, args: list[str]) -> str:
    if len(args) not in (2, 3):
        return "用法：/stats 2026-10-01 2026-10-07 [页码]"
    start, end = _date(args[0]), _date(args[1])
    if not start or not end or end < start or (end - start).days >= MAX_DAYS:
        return f"日期格式为 YYYY-MM-DD，起始日不得晚于结束日，最多查询 {MAX_DAYS} 天。"
    page = _parse_page(args[2]) if len(args) == 3 else 1
    if page is None:
        return "页码必须是正整数。"
    total_days = (end - start).days + 1
    total_pages = (total_days + STATS_PAGE_SIZE - 1) // STATS_PAGE_SIZE
    if page > total_pages:
        return f"页码超出范围，共 {total_pages} 页。"
    visible_start = start + timedelta(days=(page - 1) * STATS_PAGE_SIZE)
    visible_end = min(end, visible_start + timedelta(days=STATS_PAGE_SIZE - 1))
    start_utc = datetime.combine(visible_start, time.min, LOCAL_TZ).astimezone(timezone.utc).replace(tzinfo=None)
    end_utc = datetime.combine(visible_end + timedelta(days=1), time.min, LOCAL_TZ).astimezone(timezone.utc).replace(tzinfo=None)
    if session.get_bind().dialect.name == "mysql":
        local_day = func.date(func.date_add(Movement.occurred_at, text("INTERVAL 7 HOUR")))
    else:
        local_day = func.date(Movement.occurred_at, "+7 hours")
    rows = session.execute(
        select(local_day, Movement.action, func.sum(Movement.quantity)).where(
            Movement.action.in_(["in", "out"]),
            Movement.occurred_at >= start_utc,
            Movement.occurred_at < end_utc,
        ).group_by(local_day, Movement.action)
    )
    totals: dict[str, list[int]] = {}
    for day, action, quantity in rows:
        totals.setdefault(str(day), [0, 0])[0 if action == "in" else 1] += int(quantity)
    lines = [f"出入库日报（UTC+7）：{start} 至 {end} · 第 {page}/{total_pages} 页"]
    current = visible_start
    while current <= visible_end:
        incoming, outgoing = totals.get(current.isoformat(), [0, 0])
        lines.append(f"{current}: 入库 {incoming} / 出库 {outgoing}")
        current += timedelta(days=1)
    if page < total_pages:
        lines.append(f"下一页：/stats {start} {end} {page + 1}")
    return "\n".join(lines)


def execute_command(session: Session, text: str, user_id: int, token: str, bot_username: str) -> str:
    words = text.strip().split()
    if not words or not words[0].startswith("/"):
        return USAGE
    raw_command = words[0][1:]
    command, _, mention = raw_command.partition("@")
    if mention and mention.lower() != bot_username.lower().lstrip("@"):
        return "请直接向本机器人发送命令。"
    command = command.lower()
    args = words[1:]

    if command == "myid":
        return f"你的 Telegram ID：{user_id}"
    if command == "claim":
        if len(args) != 1:
            return "用法：/claim 一次性代码（请仅在与机器人的私聊中发送）"
        _insert_owner_slot(session)
        owner = session.scalar(select(Owner).where(Owner.id == 1).with_for_update())
        if owner is None:
            raise RuntimeError("Owner slot could not be created")
        if owner.telegram_user_id:
            return "管理员已绑定。" if owner.telegram_user_id != user_id else "你已是管理员。"
        if not hmac.compare_digest(args[0], claim_code(token)):
            return "认领代码错误。"
        owner.telegram_user_id = user_id
        return "管理员绑定成功。现在可以使用 /start 查看命令。"

    if command == "start":
        return USAGE
    owner = session.get(Owner, 1)
    if not owner or owner.telegram_user_id != user_id:
        return "无权限访问库存。请由管理员在私聊中操作；首次绑定使用 /claim 一次性代码。"

    if command in {"add", "remove"}:
        if len(args) != 2 or not _valid_id(args[0]) or (qty := _parse_qty(args[1])) is None:
            return f"用法：/{command} 商品ID 正整数数量（最多 {MAX_QTY}）"
        product_id = args[0]
        if command == "add":
            _insert_if_missing(session, product_id)
        product = session.scalar(select(Product).where(Product.product_id == product_id).with_for_update())
        if not product:
            return f"商品 {product_id} 不存在。"
        if command == "remove" and product.quantity < qty:
            return f"库存不足：{product_id} 当前仅 {product.quantity}。"
        product.quantity += qty if command == "add" else -qty
        session.add(Movement(action="in" if command == "add" else "out", product_id=product_id,
                             quantity=qty, actor_id=user_id))
        label = "入库" if command == "add" else "出库"
        return f"{product_id} {label} {qty}，当前库存：{product.quantity}"

    if command in {"stock", "delete"}:
        if len(args) != 1 or not _valid_id(args[0]):
            return f"用法：/{command} 商品ID"
        product = session.scalar(select(Product).where(Product.product_id == args[0]).with_for_update())
        if not product:
            return f"商品 {args[0]} 不存在。"
        if command == "stock":
            return f"{product.product_id} 当前库存：{product.quantity}"
        old_qty = product.quantity
        session.add(Movement(action="delete", product_id=args[0], quantity=old_qty, actor_id=user_id))
        session.delete(product)
        return f"已删除商品 {args[0]}（删除前库存 {old_qty}）；历史流水保留。"

    if command == "list":
        page = _parse_page(args[0]) if len(args) == 1 else 1
        if len(args) > 1 or page is None:
            return "用法：/list [正整数页码]"
        products = session.scalars(
            select(Product).order_by(Product.product_id)
            .offset((page - 1) * LIST_PAGE_SIZE).limit(LIST_PAGE_SIZE + 1)
        ).all()
        if not products:
            return "当前没有商品记录。" if page == 1 else "该页没有商品记录。"
        has_next = len(products) > LIST_PAGE_SIZE
        lines = [f"当前库存 · 第 {page} 页："] + [
            f"• {p.product_id}：{p.quantity}" for p in products[:LIST_PAGE_SIZE]
        ]
        if has_next:
            lines.append(f"下一页：/list {page + 1}")
        return "\n".join(lines)

    if command == "history":
        if len(args) > 1 or (args and not _valid_id(args[0])):
            return "用法：/history [商品ID]"
        query = select(Movement).order_by(Movement.id.desc()).limit(20)
        if args:
            query = query.where(Movement.product_id == args[0])
        rows = session.scalars(query).all()
        if not rows:
            return "暂无出入库记录。"
        labels = {"in": "入库", "out": "出库", "delete": "删除"}
        return "最近流水（UTC+7）：\n" + "\n".join(
            f"{m.occurred_at.replace(tzinfo=timezone.utc).astimezone(LOCAL_TZ):%Y-%m-%d %H:%M} "
            f"{m.product_id} {labels.get(m.action, m.action)} {m.quantity} · 操作人 {m.actor_id}"
            for m in rows
        )

    if command == "stats":
        return _stats(session, args)
    return "未知命令。\n" + USAGE


def _insert_owner_slot(session: Session) -> None:
    # Slot row exists with 0 until one private-chat user successfully claims it.
    if session.get_bind().dialect.name == "mysql":
        session.execute(mysql_insert(Owner).values(id=1, telegram_user_id=0).prefix_with("IGNORE"))
    else:
        session.execute(sqlite_insert(Owner).values(id=1, telegram_user_id=0).on_conflict_do_nothing())


def process_update(session: Session, update: dict, token: str, bot_username: str) -> tuple[int | None, list[str]]:
    """Commit both operation and dedupe marker before replying to Telegram."""
    update_id = update.get("update_id")
    if not isinstance(update_id, int) or isinstance(update_id, bool):
        return None, []
    with session.begin():
        dialect = session.get_bind().dialect.name
        values = {"update_id": update_id, "response_json": "[]"}
        if dialect == "mysql":
            result = session.execute(mysql_insert(ProcessedUpdate).values(**values).prefix_with("IGNORE"))
        elif dialect == "sqlite":
            result = session.execute(sqlite_insert(ProcessedUpdate).values(**values).on_conflict_do_nothing())
        else:
            raise RuntimeError(f"Unsupported database dialect: {dialect}")
        reserved = result.rowcount == 1
        if not reserved:
            old = session.get(ProcessedUpdate, update_id)
            if old is None:
                raise RuntimeError("Duplicate update has no committed response")
            message = update.get("message") or {}
            return (message.get("chat") or {}).get("id"), json.loads(old.response_json)
        message = update.get("message") or {}
        chat = message.get("chat") or {}
        sender = message.get("from") or {}
        chat_id, user_id = chat.get("id"), sender.get("id")
        if chat.get("type") == "private" and isinstance(chat_id, int) and isinstance(user_id, int):
            response = execute_command(session, str(message.get("text") or ""), user_id, token, bot_username)
            replies = split_message(response)
        else:
            chat_id, replies = None, []
        stored = session.get(ProcessedUpdate, update_id)
        if stored is None:
            raise RuntimeError("Reserved update could not be loaded")
        stored.response_json = json.dumps(replies, ensure_ascii=False)
        return chat_id, replies
