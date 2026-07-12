#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="${APP_DIR:-/root/legitcheck}"
ENV_FILE="${ENV_FILE:-/etc/legitcheck/legitcheck.env}"
PYTHON="${PYTHON:-$APP_DIR/env/bin/python}"
PIP="${PIP:-$APP_DIR/env/bin/pip}"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/legitcheck}"

cd "$APP_DIR"

backup_path="$BACKUP_DIR/db-$(date -u +%Y%m%dT%H%M%SZ).sqlite3"
install -d -m 750 "$BACKUP_DIR"
"$PYTHON" - "$backup_path" <<'PY'
import sqlite3
import sys

with sqlite3.connect("db.sqlite3") as source:
    with sqlite3.connect(sys.argv[1]) as destination:
        source.backup(destination)
PY

git pull --ff-only
"$PIP" install --disable-pip-version-check -r requirements.txt

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

: "${YOOKASSA_ACCOUNT_ID:?YOOKASSA_ACCOUNT_ID is missing in $ENV_FILE}"
: "${YOOKASSA_SECRET_KEY:?YOOKASSA_SECRET_KEY is missing in $ENV_FILE}"
: "${TELEGRAM_BOT_TOKEN:?TELEGRAM_BOT_TOKEN is missing in $ENV_FILE}"

"$PYTHON" manage.py check
"$PYTHON" manage.py migrate --noinput
"$PYTHON" manage.py cleanup_login_tokens --retention-days 7
"$PYTHON" manage.py collectstatic --noinput --clear

install -m 0644 deploy/systemd/gunicorn.service /etc/systemd/system/gunicorn.service
install -m 0644 deploy/systemd/telegram-login-bot.service /etc/systemd/system/telegram-login-bot.service
install -m 0644 deploy/systemd/legitcheck-telegram-verdicts.service /etc/systemd/system/legitcheck-telegram-verdicts.service
if [[ -n "${VK_GROUP_TOKEN:-}" && -n "${VK_GROUP_ID:-}" ]]; then
  install -m 0644 deploy/systemd/legitcheck-vk-bot.service /etc/systemd/system/legitcheck-vk-bot.service
fi
systemctl daemon-reload
systemctl enable legitcheck-telegram-verdicts.service

services=(gunicorn telegram-login-bot)
if systemctl list-unit-files --type=service --no-legend legitcheck-telegram-verdicts.service 2>/dev/null | grep -q '^legitcheck-telegram-verdicts\.service'; then
  services+=(legitcheck-telegram-verdicts)
fi
if systemctl list-unit-files --type=service --no-legend legitcheck-vk-bot.service 2>/dev/null | grep -q '^legitcheck-vk-bot\.service'; then
  services+=(legitcheck-vk-bot)
fi

systemctl restart "${services[@]}"
for service in "${services[@]}"; do
  systemctl is-active --quiet "$service"
done

echo "Deployment complete. Database backup: $backup_path"
