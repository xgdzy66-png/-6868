from __future__ import annotations

import os
import tempfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from threading import Barrier

# The production module creates a database-backed WSGI application on import.
# Force a harmless test-only SQLite URL even if WebDev injected a production DSN.
os.environ["DATABASE_URL"] = f"sqlite:///{Path(tempfile.gettempdir()) / 'kucun-import-test.db'}"

import pytest
from sqlalchemy import select

from app.bot import claim_code, process_update, webhook_secret
from app.server import create_app
from app.storage import Movement, Product, make_session_factory

TOKEN = "123456:FAKE_TEST_TOKEN"


@pytest.fixture
def harness(tmp_path):
    sent = []
    url = "sqlite:///" + str(tmp_path / "inventory.db")
    app = create_app(database_url=url, bot_token=TOKEN,
                     sender=lambda _token, chat_id, text: sent.append((chat_id, text)) or True)
    return app.test_client(), sent, url


def send(client, sent, text, update_id, user_id=42, header=True, chat_type="private"):
    headers = {"X-Telegram-Bot-Api-Secret-Token": webhook_secret(TOKEN)} if header else {}
    response = client.post("/api/telegram/webhook", headers=headers, json={
        "update_id": update_id,
        "message": {"chat": {"id": user_id, "type": chat_type},
                    "from": {"id": user_id}, "text": text},
    })
    return response, [message for _, message in sent]


def claim(client, sent):
    result, messages = send(client, sent, "/claim " + claim_code(TOKEN), 1)
    assert result.status_code == 200
    assert "绑定成功" in messages[-1]


def test_health_and_webhook_signature(harness):
    client, sent, _ = harness
    assert client.get("/healthz").status_code == 200
    assert client.get("/readyz").status_code == 200
    assert client.get("/manus-routes.json").json["routes"][0]["path"] == "/"
    assert client.get("/static/box.png").status_code == 200
    response, _ = send(client, sent, "/start", 1, header=False)
    assert response.status_code == 403
    assert not sent
    response, _ = send(client, sent, "/start", 2, chat_type="group")
    assert response.status_code == 200
    assert not sent


def test_readiness_requires_bot_token(tmp_path):
    app = create_app(database_url="sqlite:///" + str(tmp_path / "empty.db"), bot_token="")
    assert app.test_client().get("/readyz").status_code == 503


def test_remote_mysql_rejects_plaintext(monkeypatch):
    monkeypatch.delenv("ALLOW_PLAINTEXT_DB", raising=False)
    with pytest.raises(ValueError, match="requires verified TLS"):
        make_session_factory("mysql+pymysql://user:password@remote.example/inventory")


def test_claim_authorization_stock_and_delete(harness):
    client, sent, url = harness
    send(client, sent, "/add SKU-1 8", 1)
    assert "无权限" in sent[-1][1]
    send(client, sent, "/claim wrong", 2)
    assert "错误" in sent[-1][1]
    send(client, sent, "/claim " + claim_code(TOKEN), 3)
    assert "绑定成功" in sent[-1][1]
    send(client, sent, "/claim " + claim_code(TOKEN), 4, user_id=7)
    assert "已绑定" in sent[-1][1]
    send(client, sent, "/add SKU-1 8", 5)
    assert "当前库存：8" in sent[-1][1]
    send(client, sent, "/remove SKU-1 9", 6)
    assert "库存不足" in sent[-1][1]
    send(client, sent, "/remove SKU-1 3", 7)
    assert "当前库存：5" in sent[-1][1]
    send(client, sent, "/stock SKU-1", 8)
    assert "当前库存：5" in sent[-1][1]
    send(client, sent, "/list", 9)
    assert "SKU-1：5" in sent[-1][1]
    send(client, sent, "/delete SKU-1", 10)
    assert "历史流水保留" in sent[-1][1]
    send(client, sent, "/delete SKU-1", 11)
    assert "不存在" in sent[-1][1]
    session_factory = make_session_factory(url)
    with session_factory() as db:
        assert db.get(Product, "SKU-1") is None
        actions = [m.action for m in db.scalars(select(Movement).order_by(Movement.id))]
        assert actions == ["in", "out", "delete"]


def test_bad_quantity_and_duplicate_update(harness):
    client, sent, url = harness
    claim(client, sent)
    for i, quantity in enumerate(["-1", "0", "1.5", "abc", "1000000001"], 2):
        send(client, sent, f"/add SKU {quantity}", i)
        assert "用法" in sent[-1][1]
    send(client, sent, "/add SKU 10", 20)
    send(client, sent, "/add SKU 10", 20)  # Telegram retried an acknowledged update.
    session_factory = make_session_factory(url)
    with session_factory() as db:
        product = db.get(Product, "SKU")
        assert product is not None and product.quantity == 10
        assert len(db.scalars(select(Movement)).all()) == 1
    assert sent[-1][1] == sent[-2][1]


def test_concurrent_duplicate_update(harness):
    client, sent, url = harness
    claim(client, sent)
    factory = make_session_factory(url)
    update = {"update_id": 100, "message": {"chat": {"id": 42, "type": "private"},
              "from": {"id": 42}, "text": "/add CONCURRENT 4"}}
    barrier = Barrier(2)

    def worker():
        barrier.wait()
        with factory() as db:
            return process_update(db, update, TOKEN, "kucunxbot")

    with ThreadPoolExecutor(max_workers=2) as pool:
        first, second = list(pool.map(lambda _: worker(), range(2)))
    assert first == second
    with factory() as db:
        product = db.get(Product, "CONCURRENT")
        assert product is not None and product.quantity == 4
        assert len(db.scalars(select(Movement).where(Movement.product_id == "CONCURRENT")).all()) == 1


def test_stats_local_date_boundary_and_history(harness):
    client, sent, url = harness
    claim(client, sent)
    send(client, sent, "/add 笔记本 7", 2)
    send(client, sent, "/remove 笔记本 2", 3)
    session_factory = make_session_factory(url)
    with session_factory.begin() as db:
        rows = db.scalars(select(Movement).order_by(Movement.id)).all()
        rows[0].occurred_at = datetime(2026, 10, 1, 16, 30)  # UTC+7: October 1
        rows[1].occurred_at = datetime(2026, 10, 1, 17, 30)  # UTC+7: October 2
    send(client, sent, "/stats 2026-10-01 2026-10-03", 4)
    assert "2026-10-01: 入库 7 / 出库 0" in sent[-1][1]
    assert "2026-10-02: 入库 0 / 出库 2" in sent[-1][1]
    assert "2026-10-03: 入库 0 / 出库 0" in sent[-1][1]
    send(client, sent, "/history 笔记本", 5)
    assert "入库 7" in sent[-1][1] and "出库 2" in sent[-1][1]
    send(client, sent, "/stats 2026-02-30 2026-10-01", 6)
    assert "日期格式" in sent[-1][1]


def test_bounded_pagination(harness):
    client, sent, url = harness
    claim(client, sent)
    for n in range(28):
        send(client, sent, f"/add SKU{n:03d} 1", n + 2)
    send(client, sent, "/list", 50)
    assert sent[-1][1].count("• ") == 25
    assert "下一页：/list 2" in sent[-1][1]
    send(client, sent, "/list 2", 51)
    assert sent[-1][1].count("• ") == 3
    send(client, sent, "/stats 2026-10-01 2026-11-09", 52)
    assert "第 1/2 页" in sent[-1][1]
    assert "下一页：/stats 2026-10-01 2026-11-09 2" in sent[-1][1]
    send(client, sent, "/stats 2026-10-01 2026-11-09 2", 53)
    assert "第 2/2 页" in sent[-1][1]
    assert "2026-11-09" in sent[-1][1]
