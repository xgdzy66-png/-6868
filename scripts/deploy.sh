#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ ! -f .env ]]; then
  echo "Create .env from .env.example, set your own domain and credentials, then retry." >&2
  exit 2
fi
command -v docker >/dev/null || { echo "Docker is required." >&2; exit 2; }
command -v curl >/dev/null || { echo "curl is required." >&2; exit 2; }
# Compose resolves .env internally; never source it into the shell or print it.
DOMAIN="$(docker compose config --format json | python3 -c 'import json,sys;print(json.load(sys.stdin)["services"]["caddy"]["environment"]["DOMAIN"])')"
if [[ ! "$DOMAIN" =~ ^[A-Za-z0-9][A-Za-z0-9.-]+[A-Za-z0-9]$ ]]; then
  echo "DOMAIN must be a valid public DNS name." >&2
  exit 2
fi
docker compose up -d --build
for attempt in {1..30}; do
  if curl -fsS --connect-timeout 4 --max-time 8 "https://${DOMAIN}/readyz" >/dev/null; then
    docker compose exec -T app python -m scripts.register_webhook
    echo "Deployment complete: https://${DOMAIN}/ and https://t.me/kucunxbot"
    exit 0
  fi
  sleep 5
done
echo "HTTPS health check failed. Check DNS, port 80/443, TLS and docker compose logs." >&2
exit 1
