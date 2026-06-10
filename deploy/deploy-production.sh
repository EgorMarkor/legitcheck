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

"$PYTHON" manage.py check
"$PYTHON" manage.py migrate --noinput
"$PYTHON" manage.py collectstatic --noinput --clear

systemctl restart gunicorn telegram-login-bot
systemctl is-active --quiet gunicorn
systemctl is-active --quiet telegram-login-bot

echo "Deployment complete. Database backup: $backup_path"
