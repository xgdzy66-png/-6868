"""Private inventory dashboard API built on the bot's existing business transactions."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Callable

from flask import Flask, jsonify, request
from sqlalchemy import func, select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

from app.bot import LOCAL_TZ, MAX_DAYS, MAX_QTY, _valid_id, execute_command
from app.storage import Movement, Product


def _page() -> int | None:
    raw = request.args.get("page", "1")
    return int(raw) if raw.isascii() and raw.isdigit() and 1 <= len(raw) <= 6 and int(raw) >= 1 else None


def _local_date(raw: str) -> date | None:
    try:
        value = date.fromisoformat(raw)
        return value if value.isoformat() == raw else None
    except ValueError:
        return None


def _as_utc(local_date: date) -> datetime:
    return datetime.combine(local_date, time.min, LOCAL_TZ).astimezone(timezone.utc).replace(tzinfo=None)


def _lock_sqlite_writer(db: Session) -> None:
    # SQLite ignores SELECT FOR UPDATE: serialize writers before reading stock.
    if db.get_bind().dialect.name == "sqlite":
        db.execute(text("BEGIN IMMEDIATE"))


def register_admin_api(app: Flask, sessions: sessionmaker[Session], require_admin: Callable) -> None:
    @app.get("/admin/api/summary")
    def summary():
        _, denied = require_admin()
        if denied:
            return denied
        today = datetime.now(LOCAL_TZ).date()
        with sessions() as db:
            sku_count, units = db.execute(select(func.count(Product.product_id), func.coalesce(func.sum(Product.quantity), 0))).one()
            rows = db.execute(select(Movement.action, func.sum(Movement.quantity)).where(
                Movement.action.in_(["in", "out"]),
                Movement.occurred_at >= _as_utc(today),
                Movement.occurred_at < _as_utc(today + timedelta(days=1)),
            ).group_by(Movement.action)).all()
        today_totals = {action: int(amount) for action, amount in rows}
        return jsonify(sku_count=int(sku_count), total_units=str(units),
                       today_in=str(today_totals.get("in", 0)),
                       today_out=str(today_totals.get("out", 0)),
                       local_date=today.isoformat())

    @app.get("/admin/api/products")
    def products():
        _, denied = require_admin()
        if denied:
            return denied
        page = _page()
        search = request.args.get("q", "").strip()
        if page is None or len(search) > 64:
            return jsonify(error="搜索词或页码无效。"), 400
        clause = Product.product_id.contains(search, autoescape=True) if search else None
        with sessions() as db:
            base = select(Product).where(clause) if clause is not None else select(Product)
            count_query = select(func.count()).select_from(Product).where(clause) if clause is not None else select(func.count()).select_from(Product)
            count = db.scalar(count_query) or 0
            rows = db.scalars(base.order_by(Product.product_id).offset((page - 1) * 25).limit(25)).all()
        return jsonify(items=[{"product_id": p.product_id, "quantity": str(p.quantity)} for p in rows],
                       page=page, page_size=25, total=count)

    @app.get("/admin/api/movements")
    def movements():
        _, denied = require_admin()
        if denied:
            return denied
        page = _page()
        product_id = request.args.get("product_id", "").strip()
        if page is None or (product_id and not _valid_id(product_id)):
            return jsonify(error="商品ID或页码无效。"), 400
        clause = Movement.product_id == product_id if product_id else None
        with sessions() as db:
            base = select(Movement).where(clause) if clause is not None else select(Movement)
            count_query = select(func.count()).select_from(Movement).where(clause) if clause is not None else select(func.count()).select_from(Movement)
            count = db.scalar(count_query) or 0
            rows = db.scalars(base.order_by(Movement.id.desc()).offset((page - 1) * 20).limit(20)).all()
        return jsonify(items=[{
            "id": m.id, "product_id": m.product_id, "action": m.action,
            "quantity": str(m.quantity),
            "occurred_at": m.occurred_at.replace(tzinfo=timezone.utc).astimezone(LOCAL_TZ).isoformat(),
        } for m in rows], page=page, page_size=20, total=count)

    @app.get("/admin/api/stats")
    def stats():
        _, denied = require_admin()
        if denied:
            return denied
        today = datetime.now(LOCAL_TZ).date()
        start = _local_date(request.args.get("start", (today - timedelta(days=6)).isoformat()))
        end = _local_date(request.args.get("end", today.isoformat()))
        if not start or not end or end < start or (end - start).days >= MAX_DAYS:
            return jsonify(error=f"请选择有效日期，区间不能超过 {MAX_DAYS} 天。"), 400
        with sessions() as db:
            if db.get_bind().dialect.name == "mysql":
                local_day = func.date(func.date_add(Movement.occurred_at, text("INTERVAL 7 HOUR")))
            else:
                local_day = func.date(Movement.occurred_at, "+7 hours")
            rows = db.execute(select(local_day, Movement.action, func.sum(Movement.quantity)).where(
                Movement.action.in_(["in", "out"]),
                Movement.occurred_at >= _as_utc(start),
                Movement.occurred_at < _as_utc(end + timedelta(days=1)),
            ).group_by(local_day, Movement.action)).all()
        totals: dict[str, list[int]] = {}
        for day, action, amount in rows:
            totals.setdefault(str(day), [0, 0])[0 if action == "in" else 1] += int(amount)
        days = []
        current = start
        while current <= end:
            incoming, outgoing = totals.get(current.isoformat(), [0, 0])
            days.append({"date": current.isoformat(), "incoming": str(incoming), "outgoing": str(outgoing)})
            current += timedelta(days=1)
        return jsonify(start=start.isoformat(), end=end.isoformat(), timezone="UTC+7", days=days)

    @app.post("/admin/api/stock")
    def change_stock():
        owner_id, denied = require_admin(write=True)
        if denied:
            return denied
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify(error="请提交 JSON 库存操作。"), 400
        action, product_id, quantity = data.get("action"), data.get("product_id"), data.get("quantity")
        if action not in ("add", "remove") or not isinstance(product_id, str) or not _valid_id(product_id) or \
                isinstance(quantity, bool) or not isinstance(quantity, int) or not 1 <= quantity <= MAX_QTY:
            return jsonify(error=f"请填写商品ID和 1 至 {MAX_QTY} 的整数数量。"), 400
        try:
            with sessions.begin() as db:
                _lock_sqlite_writer(db)
                message = execute_command(db, f"/{action} {product_id} {quantity}", owner_id, "", "kucunxbot")
        except OperationalError:
            return jsonify(error="数据库正忙，请稍后重试。"), 503
        if message.startswith("库存不足"):
            return jsonify(error=message), 409
        if message.endswith("不存在。"):
            return jsonify(error=message), 404
        return jsonify(message=message)

    @app.delete("/admin/api/products")
    def delete_product():
        owner_id, denied = require_admin(write=True)
        if denied:
            return denied
        data = request.get_json(silent=True)
        product_id = data.get("product_id") if isinstance(data, dict) else None
        if not isinstance(product_id, str) or not _valid_id(product_id):
            return jsonify(error="请输入有效商品ID。"), 400
        try:
            with sessions.begin() as db:
                _lock_sqlite_writer(db)
                message = execute_command(db, f"/delete {product_id}", owner_id, "", "kucunxbot")
        except OperationalError:
            return jsonify(error="数据库正忙，请稍后重试。"), 503
        if message.endswith("不存在。"):
            return jsonify(error=message), 404
        return jsonify(message=message)
