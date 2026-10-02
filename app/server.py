"""Flask HTTP entrypoint for Telegram webhooks."""
from __future__ import annotations

import hmac
import os
from pathlib import Path
from typing import Callable

import requests
from flask import Flask, jsonify, request, send_from_directory
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.admin_api import register_admin_api
from app.admin_auth import register_admin_auth
from app.bot import process_update, webhook_secret
from app.storage import make_session_factory

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


def send_message(token: str, chat_id: int, message: str) -> bool:
    """True if sent or permanently undeliverable; False signals a retriable failure."""
    try:
        response = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": message, "disable_web_page_preview": True},
            timeout=10,
        )
        return response.status_code < 400 or (400 <= response.status_code < 500 and response.status_code != 429)
    except requests.RequestException:
        # Do not log exception URLs because Bot API paths contain the credential.
        return False


def create_app(*, database_url: str | None = None, bot_token: str | None = None,
               sender: Callable[[str, int, str], bool] | None = None) -> Flask:
    app = Flask(__name__, static_folder=None)
    app.config["MAX_CONTENT_LENGTH"] = 1024 * 1024
    token = bot_token if bot_token is not None else os.environ.get("BOT_TOKEN", "")
    sessions = make_session_factory(database_url)
    dispatch = sender or send_message

    @app.get("/")
    def home():
        return send_from_directory(STATIC_DIR, "index.html")

    @app.get("/admin")
    def admin_page():
        return send_from_directory(STATIC_DIR, "admin.html")

    @app.get("/static/<path:filename>")
    def static_asset(filename):
        return send_from_directory(STATIC_DIR, filename)

    @app.get("/manus-routes.json")
    def route_manifest():
        return send_from_directory(STATIC_DIR, "manus-routes.json")

    @app.get("/healthz")
    def health():
        return jsonify(status="ok")

    @app.get("/readyz")
    def ready():
        if not token:
            return jsonify(status="not ready"), 503
        try:
            with sessions() as session:
                session.execute(text("SELECT 1")).scalar_one()
        except SQLAlchemyError:
            return jsonify(status="not ready"), 503
        return jsonify(status="ready")

    @app.post("/api/telegram/webhook")
    def telegram_webhook():
        if not token:
            return "bot is not configured", 503
        actual = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if not hmac.compare_digest(actual, webhook_secret(token)):
            return "forbidden", 403
        update = request.get_json(silent=True)
        if not isinstance(update, dict):
            return "invalid update", 400
        try:
            with sessions() as session:
                chat_id, replies = process_update(session, update, token,
                                                   os.environ.get("BOT_USERNAME", "kucunxbot"))
        except SQLAlchemyError:
            # A transient database failure must not acknowledge an uncommitted update.
            return "database unavailable", 503
        if isinstance(chat_id, int):
            for reply in replies:
                if not dispatch(token, chat_id, reply):
                    return "reply delivery failed", 502
        return "ok", 200

    require_admin = register_admin_auth(app, sessions)
    register_admin_api(app, sessions, require_admin)
    return app


app = create_app()
