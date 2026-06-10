#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="${APP_DIR:-/root/legitcheck}"
ENV_FILE="${ENV_FILE:-/etc/legitcheck/legitcheck.env}"
PYTHON="${PYTHON:-$APP_DIR/env/bin/python}"
PIP="${PIP:-$APP_DIR/env/bin/pip}"

cd "$APP_DIR"

backup_dir="$APP_DIR/backups"
backup_path="$backup_dir/db-$(date -u +%Y%m%dT%H%M%SZ).sqlite3"
install -d -m 750 "$backup_dir"
cp --preserve=mode,timestamps db.sqlite3 "$backup_path"

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
