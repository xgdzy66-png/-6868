#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
umask 077
if [ ! -f .env ]; then
  cp .env.example .env
  chmod 600 .env
  printf '%s\n' '已创建 .env，请先填写自己的 Telegram 应用凭据和 AI 密钥。'
  printf '%s\n' '之后先执行手机号登录，再设置群白名单；详情见 README.md。'
  exit 0
fi
if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
  .venv/bin/pip install -r requirements.txt
fi
.venv/bin/python -m tg_ai check
exec .venv/bin/python -m tg_ai run
