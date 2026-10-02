"""Authentication and inventory dashboard integration tests using an isolated SQLite DB."""
from __future__ import annotations

import base64
import json
import os
import tempfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from threading import Barrier
from urllib.parse import parse_qs, urlsplit

os.environ["DATABASE_URL"] = f"sqlite:///{Path(tempfile.gettempdir()) / 'kucun-admin-import-test.db'}"

import jwt
import pytest
from sqlalchemy import select

from app.admin_auth import COOKIE, PRODUCTION_ORIGIN, _csrf_value
from app.bot import claim_code, webhook_secret
from app.server import create_app
from app.storage import AdminIdentity, Movement, Product, make_session_factory

TOKEN = "123456:ADMIN_FAKE_TEST_TOKEN"
SECRET = "admin-test-key-32-characters-and-more"


@pytest.fixture
def web(tmp_path, monkeypatch):
    monkeypatch.setenv("MANUS_PROJECT_ID", "test-project")
    monkeypatch.setenv("MANUS_JWT_SECRET", SECRET)
    monkeypatch.setenv("MANUS_OAUTH_PORTAL_URL", "https://auth.example.test")
    monkeypatch.setenv("MANUS_OAUTH_API_URL", "https://identity.example.test")
    url = "sqlite:///" + str(tmp_path / "admin.db")
    sent = []
    app = create_app(database_url=url, bot_token=TOKEN,
                     sender=lambda _token, cid, message: sent.append((cid, message)) or True)
    client = app.test_client()
    return client, url, sent, monkeypatch


def post(client, path, data):
    return client.post(path, json=data, headers={"Origin": PRODUCTION_ORIGIN}, base_url=PRODUCTION_ORIGIN)


def current(client):
    return client.get("/admin/api/session", base_url=PRODUCTION_ORIGIN).json


def telegram(client, sent, command, update_id, sender=42):
    response = client.post("/api/telegram/webhook", json={
        "update_id": update_id,
        "message": {"chat": {"id": sender, "type": "private"},
                    "from": {"id": sender}, "text": command},
    }, headers={"X-Telegram-Bot-Api-Secret-Token": webhook_secret(TOKEN)},
        base_url=PRODUCTION_ORIGIN)
    assert response.status_code == 200
    return sent[-1][1]


def oauth_login(web, open_id="manus-owner"):
    client, _, _, monkeypatch = web
    class Reply:
        def __init__(self, data):
            self.data = data

        def raise_for_status(self):
            pass

        def json(self):
            return self.data

    def fake_post(url, *, json, timeout):
        if url.endswith("ExchangeToken"):
            assert json["clientId"] == "test-project"
            assert json["grantType"] == "authorization_code"
            assert json["redirectUri"] == PRODUCTION_ORIGIN + "/admin/auth/callback"
            return Reply({"accessToken": "temporary-test-token"})
        assert url.endswith("GetUserInfo")
        assert json == {"accessToken": "temporary-test-token"}
        return Reply({"openId": open_id, "name": "店主", "email": "owner@example.test"})

    monkeypatch.setattr("app.admin_auth.requests.post", fake_post)
    start = post(client, "/admin/api/oauth/start", {"origin": PRODUCTION_ORIGIN})
    assert start.status_code == 200
    assert "Secure" in start.headers["Set-Cookie"]
    assert "HttpOnly" in start.headers["Set-Cookie"]
    assert "SameSite=None" in start.headers["Set-Cookie"]
    params = parse_qs(urlsplit(start.json["url"]).query)
    assert params["appId"] == ["test-project"]
    assert params["redirectUri"] == [PRODUCTION_ORIGIN + "/admin/auth/callback"]
    callback = client.get("/admin/auth/callback", query_string={"code": "test-code", "state": params["state"][0]},
                          base_url=PRODUCTION_ORIGIN)
    assert callback.status_code == 302
    assert callback.headers["Location"] == "/admin"
    assert "SameSite=None" in callback.headers.getlist("Set-Cookie")[0]
    assert current(client)["authenticated"] is True
    return current(client)["csrf"]


def bind_owner(web, csrf):
    client, _, sent, _ = web
    telegram(client, sent, "/claim " + claim_code(TOKEN), 1)
    result = post(client, "/admin/api/bind", {})
    # CSRF is mandatory, even for requesting a binding code.
    assert result.status_code == 403
    result = client.post("/admin/api/bind", json={}, headers={"Origin": PRODUCTION_ORIGIN, "X-CSRF-Token": csrf},
                         base_url=PRODUCTION_ORIGIN)
    assert result.status_code == 200
    command = result.json["command"]
    assert command.startswith("/bind ")
    assert "无权限" in telegram(client, sent, command, 2, sender=77)
    assert "后台绑定成功" in telegram(client, sent, command, 3)
    assert current(client)["authorized"] is True
    return command


def test_login_state_and_cookie_validation(web):
    client, _, _, _ = web
    assert current(client) == {"authenticated": False, "authorized": False}
    assert client.get("/admin", base_url=PRODUCTION_ORIGIN).status_code == 200
    assert client.get("/admin/api/products", base_url=PRODUCTION_ORIGIN).status_code == 401
    assert post(client, "/admin/api/oauth/start", {"origin": "https://evil.example"}).status_code == 403
    proxy_headers = {"Origin": "http://127.0.0.1:3000", "Referer": PRODUCTION_ORIGIN + "/admin",
                     "X-Forwarded-Host": "kucunbot-gbtkg6he.manus.space"}
    assert client.post("/admin/api/oauth/start", json={"origin": PRODUCTION_ORIGIN},
                       headers=proxy_headers, base_url=PRODUCTION_ORIGIN).status_code == 200
    proxy_headers["Referer"] = "https://evil.example/admin"
    assert client.post("/admin/api/oauth/start", json={"origin": PRODUCTION_ORIGIN},
                       headers=proxy_headers, base_url=PRODUCTION_ORIGIN).status_code == 403
    proxy_headers.pop("Referer")
    proxy_headers["Sec-Fetch-Site"] = "same-origin"
    assert client.post("/admin/api/oauth/start", json={"origin": PRODUCTION_ORIGIN},
                       headers=proxy_headers, base_url=PRODUCTION_ORIGIN).status_code == 200
    proxy_headers["Sec-Fetch-Site"] = "cross-site"
    assert client.post("/admin/api/oauth/start", json={"origin": PRODUCTION_ORIGIN},
                       headers=proxy_headers, base_url=PRODUCTION_ORIGIN).status_code == 403
    # A forged or expired platform session must not create an application identity.
    expired = jwt.encode({"openId": "fake", "appId": "test-project", "exp": 1}, SECRET, algorithm="HS256")
    client.set_cookie(COOKIE, expired, domain="kucunbot-gbtkg6he.manus.space", secure=True)
    assert current(client)["authenticated"] is False
    client.delete_cookie(COOKIE, domain="kucunbot-gbtkg6he.manus.space")
    oauth_login(web)
    assert current(client)["authorized"] is False
    assert client.get("/admin/api/products", base_url=PRODUCTION_ORIGIN).status_code == 403
    assert client.get("/admin", base_url=PRODUCTION_ORIGIN).headers["Cache-Control"] == "private, no-store"
    assert "frame-ancestors https://manus.im" in client.get("/admin", base_url=PRODUCTION_ORIGIN).headers["Content-Security-Policy"]


def test_oauth_rejects_tampered_nonce(web):
    client, _, _, _ = web
    start = post(client, "/admin/api/oauth/start", {"origin": PRODUCTION_ORIGIN})
    original = parse_qs(urlsplit(start.json["url"]).query)["state"][0]
    data = json.loads(base64.urlsafe_b64decode(original + "=" * (-len(original) % 4)))
    data["nonce"] = "wrong-nonce"
    altered = base64.urlsafe_b64encode(json.dumps(data).encode()).decode().rstrip("=")
    callback = client.get("/admin/auth/callback", query_string={"code": "bogus", "state": altered},
                          base_url=PRODUCTION_ORIGIN)
    assert callback.status_code == 403
    assert current(client)["authenticated"] is False


def test_telegram_binding_and_inventory_transactions(web):
    client, url, sent, _ = web
    csrf = oauth_login(web)
    bind_owner(web, csrf)
    bad_origin = client.post("/admin/api/stock", json={"action": "add", "product_id": "123", "quantity": 5},
                             headers={"Origin": "https://evil.example", "X-CSRF-Token": csrf},
                             base_url=PRODUCTION_ORIGIN)
    assert bad_origin.status_code == 403
    missing_csrf = post(client, "/admin/api/stock", {"action": "add", "product_id": "123", "quantity": 5})
    assert missing_csrf.status_code == 403
    def stock(action, qty):
        return client.post("/admin/api/stock", json={"action": action, "product_id": "123", "quantity": qty},
                           headers={"Origin": PRODUCTION_ORIGIN, "X-CSRF-Token": csrf},
                           base_url=PRODUCTION_ORIGIN)
    assert stock("add", 5).status_code == 200
    proxy_headers = {"Origin": "http://127.0.0.1:3000", "Referer": PRODUCTION_ORIGIN + "/admin",
                     "X-Forwarded-Host": "kucunbot-gbtkg6he.manus.space", "X-CSRF-Token": csrf}
    assert client.post("/admin/api/stock", json={"action": "add", "product_id": "123", "quantity": 1},
                       headers=proxy_headers, base_url=PRODUCTION_ORIGIN).status_code == 200
    assert stock("remove", 7).status_code == 409
    assert stock("remove", 3).status_code == 200
    products = client.get("/admin/api/products?q=123", base_url=PRODUCTION_ORIGIN).json
    assert products["items"] == [{"product_id": "123", "quantity": "3"}]
    assert client.get("/admin/api/summary", base_url=PRODUCTION_ORIGIN).json["total_units"] == "3"
    assert client.get("/admin/api/movements?product_id=123", base_url=PRODUCTION_ORIGIN).json["total"] == 3
    today = datetime.now(timezone.utc).astimezone(__import__("zoneinfo").ZoneInfo("Asia/Bangkok")).date().isoformat()
    stats = client.get(f"/admin/api/stats?start={today}&end={today}", base_url=PRODUCTION_ORIGIN).json
    assert stats["days"][0]["incoming"] == "6"
    assert stats["days"][0]["outgoing"] == "3"
    assert client.get("/admin/api/stats?start=2026-10-05&end=2026-10-01", base_url=PRODUCTION_ORIGIN).status_code == 400
    response = client.delete("/admin/api/products", json={"product_id": "123"},
                             headers={"Origin": PRODUCTION_ORIGIN, "X-CSRF-Token": csrf}, base_url=PRODUCTION_ORIGIN)
    assert response.status_code == 200
    with make_session_factory(url)() as db:
        assert db.get(Product, "123") is None
        assert [m.action for m in db.scalars(select(Movement).order_by(Movement.id))] == ["in", "in", "out", "delete"]
        identity = db.get(AdminIdentity, 1)
        assert identity is not None and identity.telegram_user_id == 42
    assert "不存在" in telegram(client, sent, "/stock 123", 4)
    result = client.post("/admin/api/logout", json={}, headers={"Origin": PRODUCTION_ORIGIN, "X-CSRF-Token": csrf},
                         base_url=PRODUCTION_ORIGIN)
    assert result.status_code == 200
    assert current(client)["authenticated"] is False
    assert client.get("/admin/api/products", base_url=PRODUCTION_ORIGIN).status_code == 401


def test_concurrent_dashboard_and_bot_writes_keep_stock_consistent(web):
    client, url, sent, _ = web
    csrf = oauth_login(web)
    bind_owner(web, csrf)
    app = client.application
    signed = jwt.encode({"openId": "manus-owner", "appId": "test-project",
                         "exp": datetime.now(timezone.utc).timestamp() + 3600}, SECRET, algorithm="HS256")
    barrier = Barrier(8)

    def worker(index):
        worker_client = app.test_client()
        barrier.wait()
        if index % 2 == 0:
            worker_client.set_cookie(COOKIE, signed, domain="kucunbot-gbtkg6he.manus.space", secure=True)
            response = worker_client.post("/admin/api/stock", json={"action": "add", "product_id": "RACE", "quantity": 1},
                headers={"Origin": PRODUCTION_ORIGIN, "X-CSRF-Token": _csrf_value(signed)}, base_url=PRODUCTION_ORIGIN)
        else:
            response = worker_client.post("/api/telegram/webhook", json={
                "update_id": 200 + index,
                "message": {"chat": {"id": 42, "type": "private"}, "from": {"id": 42}, "text": "/add RACE 1"},
            }, headers={"X-Telegram-Bot-Api-Secret-Token": webhook_secret(TOKEN)}, base_url=PRODUCTION_ORIGIN)
        return response.status_code

    with ThreadPoolExecutor(max_workers=8) as pool:
        assert list(pool.map(worker, range(8))) == [200] * 8
    with make_session_factory(url)() as db:
        product = db.get(Product, "RACE")
        assert product is not None and product.quantity == 8
        assert len(db.scalars(select(Movement).where(Movement.product_id == "RACE")).all()) == 8
