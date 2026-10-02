#!/usr/bin/env python3
"""Register or inspect a Telegram webhook using BOT_TOKEN from the environment."""
import os
import sys

import requests

from app.bot import webhook_secret


def main() -> int:
    token = os.environ.get("BOT_TOKEN", "")
    base = os.environ.get("BOT_WEBHOOK_URL", "").rstrip("/")
    if not token or not base.startswith("https://"):
        print("Set BOT_TOKEN and an HTTPS BOT_WEBHOOK_URL (service origin).", file=sys.stderr)
        return 2
    api = f"https://api.telegram.org/bot{token}/"
    try:
        me = requests.post(api + "getMe", timeout=12).json()
        if not me.get("ok") or me.get("result", {}).get("username", "").lower() != "kucunxbot":
            print("Bot credentials do not identify @kucunxbot; webhook unchanged.", file=sys.stderr)
            return 1
        response = requests.post(api + "setWebhook", json={
            "url": base + "/api/telegram/webhook",
            "secret_token": webhook_secret(token),
            "allowed_updates": ["message"],
            "max_connections": 2,
            "drop_pending_updates": False,
        }, timeout=15).json()
        if not response.get("ok"):
            print("Telegram rejected setWebhook; inspect your bot credentials and HTTPS URL.", file=sys.stderr)
            return 1
        info = requests.post(api + "getWebhookInfo", timeout=12).json()
        details = info.get("result", {}) if info.get("ok") else {}
        target = base + "/api/telegram/webhook"
        if details.get("url") != target:
            print("Webhook registration could not be verified.", file=sys.stderr)
            return 1
        print(f"Webhook active for @kucunxbot: {target}")
        print(f"Pending updates: {details.get('pending_update_count', 'unknown')}")
        if details.get("last_error_message"):
            print("Telegram reported a previous delivery error; check current health and logs.")
        return 0
    except (requests.RequestException, ValueError):
        # An exception from requests may include the token-bearing request URL; do not print it.
        print("Telegram API connection failed; no credential details logged.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
