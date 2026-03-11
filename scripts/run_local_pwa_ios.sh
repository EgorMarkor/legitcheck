#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOST="127.0.0.1"
PORT="8000"
BASE_URL="http://${HOST}:${PORT}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV_DIR="$ROOT_DIR/.venv_local"
REQ_FILE="$ROOT_DIR/scripts/requirements.local.txt"

cd "$ROOT_DIR"

export LOCAL_DEV=1
export PUBLIC_BASE_URL="$BASE_URL"
export PWA_URL="$BASE_URL"

if [[ ! -f "$REQ_FILE" ]]; then
  echo "Не найден файл зависимостей: $REQ_FILE"
  exit 1
fi

cleanup() {
  local code=$?
  if [[ -n "${BOT_PID:-}" ]] && kill -0 "$BOT_PID" 2>/dev/null; then
    kill "$BOT_PID" 2>/dev/null || true
  fi
  if [[ -n "${DJANGO_PID:-}" ]] && kill -0 "$DJANGO_PID" 2>/dev/null; then
    kill "$DJANGO_PID" 2>/dev/null || true
  fi
  exit "$code"
}
trap cleanup EXIT INT TERM

echo "[0/7] Готовим локальный Python venv..."
if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

VENV_PY="$VENV_DIR/bin/python"
VENV_PIP="$VENV_DIR/bin/pip"

echo "[1/7] Обновляем pip/setuptools/wheel..."
"$VENV_PIP" install --upgrade pip setuptools wheel

echo "[2/7] Ставим Python-зависимости из $REQ_FILE..."
"$VENV_PIP" install -r "$REQ_FILE"

echo "[3/7] Применяем миграции..."
"$VENV_PY" manage.py migrate

echo "[4/7] Запускаем Django: ${BASE_URL}"
"$VENV_PY" manage.py runserver "${HOST}:${PORT}" &
DJANGO_PID=$!
sleep 2

echo "[5/7] Запускаем Telegram login bot (локальная авторизация по коду)..."
"$VENV_PY" telegram_login_bot.py &
BOT_PID=$!

cd "$ROOT_DIR/mobile-pwa-shell"

echo "[6/7] Устанавливаем зависимости shell..."
npm install

if [[ ! -d "$ROOT_DIR/mobile-pwa-shell/ios/App" ]]; then
  echo "[7/7] Добавляем iOS проект Capacitor..."
  npm run add:ios
fi

echo "[7/7] Синхронизируем iOS shell с URL ${PWA_URL}"
PWA_URL="$PWA_URL" npm run sync:ios

echo "[7/7] Открываем Xcode"
PWA_URL="$PWA_URL" npm run open:ios

echo ""
echo "Готово. Что тестировать:"
echo "- Web/PWA в браузере: ${BASE_URL}/"
echo "- Вход вне Telegram: получите код на init-экране и отправьте его боту"
echo "- iOS shell: запустите из Xcode на симуляторе"
echo ""
echo "Сервер и бот запущены. Для остановки нажмите Ctrl+C в этом терминале."

wait "$DJANGO_PID"
