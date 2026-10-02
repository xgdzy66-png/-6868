"""Manus OAuth and a Telegram-owner-approved identity for the web dashboard."""
from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Callable
from urllib.parse import urlencode, urlsplit

import jwt
import requests
from flask import Flask, jsonify, make_response, redirect, request
from sqlalchemy import delete
from sqlalchemy.orm import Session, sessionmaker

from app.storage import AdminIdentity, Owner, PendingAdminBind, utc_now

COOKIE = "webdev_app_session"
NONCE_COOKIE = "kucun_oauth_nonce"
CALLBACK_PATH = "/admin/auth/callback"
PRODUCTION_ORIGIN = "https://kucunbot-gbtkg6he.manus.space"
PREVIEW_ORIGIN = "https://8328-i8jg6nq90dkizry633uta-6d06148e.us1.manus.computer"


def allowed_origins() -> set[str]:
    values = {PRODUCTION_ORIGIN, PREVIEW_ORIGIN}
    values.update(x.strip().rstrip("/") for x in os.environ.get("ADMIN_PUBLIC_ORIGINS", "").split(",") if x.strip())
    for name in ("MANUS_ADDON_PREVIEW_PUBLIC_ORIGIN", "MANUS_ADDON_RUNTIME_PUBLIC_ORIGIN"):
        if os.environ.get(name):
            values.add(os.environ[name].rstrip("/"))
    return {x for x in values if urlsplit(x).scheme == "https" and urlsplit(x).netloc and
            urlsplit(x).path in ("", "/") and not urlsplit(x).query and not urlsplit(x).fragment}


def _csrf_value(cookie: str) -> str:
    return hashlib.sha256(b"kucun-admin-csrf-v1:" + cookie.encode()).hexdigest()


def register_admin_auth(app: Flask, sessions: sessionmaker[Session]) -> Callable:
    """Register login endpoints and return the API authorization checker."""
    project_id = os.environ.get("MANUS_PROJECT_ID", "")
    signing_key = os.environ.get("MANUS_JWT_SECRET", "")
    portal = os.environ.get("MANUS_OAUTH_PORTAL_URL", "").rstrip("/")
    oauth_api = os.environ.get("MANUS_OAUTH_API_URL", "").rstrip("/")
    origins = allowed_origins()

    def identity() -> dict | None:
        token = request.cookies.get(COOKIE, "")
        if not token or not project_id or not signing_key:
            return None
        try:
            payload = jwt.decode(token, signing_key, algorithms=["HS256"],
                                 options={"require": ["exp", "appId", "openId"]})
        except jwt.InvalidTokenError:
            return None
        if payload.get("appId") != project_id or not isinstance(payload.get("openId"), str) or not payload["openId"]:
            return None
        return payload

    def valid_origin() -> bool:
        incoming = request.headers.get("Origin", "")
        if incoming in origins:
            return True
        # The managed Preview proxy rewrites Origin to its internal listener,
        # and may enforce no-referrer. Fetch Metadata is browser-controlled;
        # cross-site requests must never use the proxy fallback.
        if incoming != "http://127.0.0.1:3000":
            return False
        forwarded = request.headers.get("X-Forwarded-Host", "")
        public_origin = "https://" + forwarded
        if public_origin not in origins:
            return False
        site = request.headers.get("Sec-Fetch-Site", "")
        if site == "same-origin":
            return True
        if site:
            return False
        # Older clients may omit Fetch Metadata; accept only their same-origin
        # Referer when the proxy has preserved it.
        ref = urlsplit(request.headers.get("Referer", ""))
        public = f"{ref.scheme}://{ref.netloc}"
        return bool(public == public_origin and ref.path.startswith("/admin"))

    def csrf_ok() -> bool:
        cookie = request.cookies.get(COOKIE, "")
        actual = request.headers.get("X-CSRF-Token", "")
        return bool(cookie and actual and valid_origin() and
                    hmac.compare_digest(actual, _csrf_value(cookie)))

    def authorized(db: Session, open_id: str) -> int | None:
        owner = db.get(Owner, 1)
        linked = db.get(AdminIdentity, 1)
        if owner and owner.telegram_user_id and linked and linked.open_id == open_id and \
                linked.telegram_user_id == owner.telegram_user_id:
            return owner.telegram_user_id
        return None

    def require_admin(*, write: bool = False):
        user = identity()
        if user is None:
            return None, (jsonify(error="请先登录 Manus 账号。"), 401)
        with sessions() as db:
            owner_id = authorized(db, user["openId"])
        if owner_id is None:
            return None, (jsonify(error="此账号尚未由机器人管理员授权。"), 403)
        if write and not csrf_ok():
            return None, (jsonify(error="安全校验失败，请刷新页面后重试。"), 403)
        return owner_id, None

    @app.after_request
    def protect_admin(response):
        if request.path.startswith("/admin"):
            response.headers["Cache-Control"] = "private, no-store"
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["Referrer-Policy"] = "same-origin"
            if request.path == "/admin":
                response.headers["Content-Security-Policy"] = (
                    "default-src 'self'; script-src 'self'; style-src 'self'; "
                    "img-src 'self' data:; connect-src 'self'; base-uri 'none'; form-action 'self'; "
                    "frame-ancestors https://manus.im https://*.manus.im"
                )
        return response

    @app.post("/admin/api/oauth/start")
    def oauth_start():
        if not all((project_id, signing_key, portal, oauth_api)):
            return jsonify(error="此环境尚未配置 Manus OAuth。"), 503
        body = request.get_json(silent=True) or {}
        origin = body.get("origin") if isinstance(body, dict) else None
        if not isinstance(origin, str) or origin not in origins or not valid_origin():
            return jsonify(error="不可信的登录来源。"), 403
        nonce = secrets.token_urlsafe(24)
        redirect_uri = origin + CALLBACK_PATH
        state = base64.urlsafe_b64encode(json.dumps(
            {"redirectUri": redirect_uri, "nonce": nonce}, separators=(",", ":")
        ).encode()).decode().rstrip("=")
        url = portal + "/app-auth?" + urlencode({
            "appId": project_id, "redirectUri": redirect_uri,
            "state": state, "responseType": "code",
        })
        response = make_response(jsonify(url=url))
        response.set_cookie(NONCE_COOKIE, nonce, max_age=600, path="/admin",
                            secure=True, httponly=True, samesite="None")
        return response

    @app.get(CALLBACK_PATH)
    def oauth_callback():
        raw_state, code = request.args.get("state", ""), request.args.get("code", "")
        if not raw_state or len(raw_state) > 2048 or not code or len(code) > 4096:
            return "登录参数不完整，请重新尝试。", 400
        try:
            state = json.loads(base64.urlsafe_b64decode(raw_state + "=" * (-len(raw_state) % 4)))
        except (ValueError, UnicodeDecodeError, binascii.Error):
            return "登录状态无效，请重新尝试。", 400
        if not isinstance(state, dict):
            return "登录状态无效，请重新尝试。", 400
        redirect_uri, nonce = state.get("redirectUri"), state.get("nonce")
        if not isinstance(redirect_uri, str) or not isinstance(nonce, str):
            return "登录状态无效，请重新尝试。", 400
        origin = redirect_uri[:-len(CALLBACK_PATH)] if redirect_uri.endswith(CALLBACK_PATH) else ""
        previous = request.cookies.get(NONCE_COOKIE, "")
        if origin not in origins or not previous or not hmac.compare_digest(previous, nonce):
            return "登录状态校验失败，请从后台重新登录。", 403
        if not all((project_id, signing_key, oauth_api)):
            return "登录暂不可用。", 503
        try:
            exchange = requests.post(
                oauth_api + "/webdev.v1.WebDevAuthPublicService/ExchangeToken",
                json={"clientId": project_id, "grantType": "authorization_code",
                      "code": code, "redirectUri": redirect_uri}, timeout=12,
            )
            exchange.raise_for_status()
            access = exchange.json().get("accessToken")
            if not isinstance(access, str) or not access:
                raise ValueError("missing access token")
            profile = requests.post(
                oauth_api + "/webdev.v1.WebDevAuthPublicService/GetUserInfo",
                json={"accessToken": access}, timeout=12,
            )
            profile.raise_for_status()
            account = profile.json()
            open_id = account.get("openId")
            if not isinstance(open_id, str) or not 0 < len(open_id) <= 255:
                raise ValueError("invalid openId")
        except (requests.RequestException, ValueError, TypeError):
            # The OAuth response can contain bearer credentials: never log its body or URL.
            return "Manus 登录未完成，请重新尝试。", 502
        now = datetime.now(timezone.utc)
        token = jwt.encode({
            "openId": open_id, "appId": project_id,
            "name": str(account.get("name") or "管理员")[:120],
            "iat": now, "exp": now + timedelta(hours=8),
        }, signing_key, algorithm="HS256")
        response = make_response(redirect("/admin", code=302))
        response.set_cookie(COOKIE, token, max_age=8 * 3600, path="/",
                            secure=True, httponly=True, samesite="None")
        response.delete_cookie(NONCE_COOKIE, path="/admin", secure=True, httponly=True, samesite="None")
        return response

    @app.get("/admin/api/session")
    def session_state():
        user = identity()
        if user is None:
            return jsonify(authenticated=False, authorized=False)
        with sessions() as db:
            owner_id = authorized(db, user["openId"])
            linked = db.get(AdminIdentity, 1)
        return jsonify(authenticated=True, authorized=bool(owner_id),
                       link_taken=bool(linked and linked.open_id != user["openId"]),
                       name=str(user.get("name") or "管理员")[:120],
                       csrf=_csrf_value(request.cookies[COOKIE]))

    @app.post("/admin/api/bind")
    def create_bind_code():
        user = identity()
        if user is None:
            return jsonify(error="请先登录 Manus 账号。"), 401
        if not csrf_ok():
            return jsonify(error="安全校验失败，请刷新页面后重试。"), 403
        with sessions.begin() as db:
            bound = db.get(AdminIdentity, 1)
            if bound:
                return (jsonify(error="后台已绑定其他账号，无法覆盖。"), 403) if bound.open_id != user["openId"] else jsonify(authorized=True)
            owner = db.get(Owner, 1)
            if not owner or not owner.telegram_user_id:
                return jsonify(error="请先在 Telegram 中认领机器人管理员。"), 409
            db.execute(delete(PendingAdminBind).where(
                (PendingAdminBind.open_id == user["openId"]) |
                (PendingAdminBind.expires_at < utc_now())
            ))
            code = secrets.token_urlsafe(18)
            db.add(PendingAdminBind(code_digest=hashlib.sha256(code.encode()).hexdigest(),
                                    open_id=user["openId"], expires_at=utc_now() + timedelta(minutes=5)))
        return jsonify(command="/bind " + code, expires_seconds=300)

    @app.post("/admin/api/logout")
    def logout():
        if identity() and not csrf_ok():
            return jsonify(error="安全校验失败。"), 403
        response = make_response(jsonify(ok=True))
        response.delete_cookie(COOKIE, path="/", secure=True, httponly=True, samesite="None")
        return response

    return require_admin
