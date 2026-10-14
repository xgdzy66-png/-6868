#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
umask 077
if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
fi
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m tg_console init
printf '%s\n' '请在浏览器打开 http://127.0.0.1:8080，用刚设置的本机管理员密码登录。'
exec .venv/bin/python -m tg_console serve --host 127.0.0.1 --port 8080
