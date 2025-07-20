#!/usr/bin/env python3
"""
Telegram Login Bot: deep-link /start login_<token>
Подтверждает токен на backend, помечает его использованным.
Работает с backend endpoint: POST /internal/telegram/confirm/
JSON: { token: <hex>, telegram_id: <int> }
Ответы backend:
  {"ok": true, "username": "..."}                    # успех
  {"ok": false, "reason": "expired|not_found|used|forbidden"}  # ошибка
"""

import os
import re
import logging
import asyncio
from dataclasses import dataclass
import json
import requests
from typing import Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler,
    MessageHandler, ContextTypes, filters
)

try:
    # Optional: load .env
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

# --- Config ----------------------------------------------------------------

BOT_TOKEN: str = os.environ.get(
    "BOT_TOKEN",
    "7620197633:AAHqBbPgVEtloxy6we7YyvMU7eWK9-hSyrU",
)
BACKEND_BASE_URL: str = "https://legitcheck.one/"
BOT_BACKEND_SECRET: Optional[str] = os.environ.get("BOT_BACKEND_SECRET") or None

if not BACKEND_BASE_URL:
    raise RuntimeError("BACKEND_BASE_URL env empty")


TOKEN_PREFIX = "login_"
TOKEN_RE = re.compile(rf"^{TOKEN_PREFIX}([a-f0-9]{16})$")  # 16 hex chars token

CONFIRM_ENDPOINT = f"{BACKEND_BASE_URL}/internal/telegram/confirm/"

# --- Exceptions -------------------------------------------------------------

class BackendError(Exception):
    pass

# --- HTTP helper ------------------------------------------------------------

def backend_confirm(token_hex: str, telegram_id: int) -> dict:
    """POST confirm to backend. Raises BackendError on any failure."""
    payload = {"token": token_hex, "telegram_id": telegram_id}
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "TGLoginBot/1.0"
    }
    if BOT_BACKEND_SECRET:
        headers["X-Bot-Secret"] = BOT_BACKEND_SECRET
    try:
        r = requests.post(CONFIRM_ENDPOINT, json=payload, headers=headers, timeout=6)
    except requests.RequestException as e:
        raise BackendError(f"net: {e}") from e

    try:
        data = r.json()
    except ValueError:
        raise BackendError(f"bad-json status={r.status_code} body={r.text[:200]!r}")

    if r.status_code != 200:
        raise BackendError(f"http {r.status_code} body={data}")
    return data

# --- Handlers ---------------------------------------------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /start [login_<token>] — подтверждаем токен, иначе показываем подсказку.
    """
    user = update.effective_user
    args = context.args

    if args:
        raw = args[0]
        m = TOKEN_RE.match(raw)
        if m:
            token_hex = m.group(1)
            await confirm_token_flow(update, token_hex)
            return

    # /start без токена
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔐 Как войти на сайте", url=f"{BACKEND_BASE_URL}/pc/telegram/help/")]
    ])
    text = (
        "👋 Отправьте мне ссылку (кнопку), сгенерированную на сайте при входе.\n\n"
        "Алгоритм:\n"
        "1. На сайте нажмите «Войти через Telegram».\n"
        "2. Откроется чат — появится /start login_... (или нажмите START).\n"
        "3. Я подтвержу токен.\n"
        "4. Вернитесь в браузер — страница обновится."
    )
    await safe_reply(update, text, reply_markup=keyboard)

async def confirm_token_flow(update: Update, token_hex: str):
    msg = update.effective_message
    user = update.effective_user

    await safe_reply(update, f"⏳ Проверяю токен…")

    try:
        data = await asyncio.to_thread(backend_confirm, token_hex, user.id)
    except BackendError as e:
        log.warning("confirm error token=%s.. tg=%s: %s", token_hex[:8], user.id, e)
        await safe_reply(update, "⚠️ Сервер недоступен. Попробуйте ещё раз через минуту.")
        return

    if not data.get("ok"):
        reason = data.get("reason")
        msg_map = {
            "expired": "⌛ Токен истёк. Сформируйте новый на сайте.",
            "not_found": "❓ Токен не найден. Сгенерируйте новый.",
            "used": "🔁 Токен уже использован. Повторите вход.",
            "forbidden": "🚫 Токен привязан к другой сессии. Сгенерируйте новый."
        }
        txt = msg_map.get(reason, "❌ Не удалось подтвердить токен.")
        await safe_reply(update, txt)
        return

    username = data.get("username")
    extra = f"\nСайт-профиль: *{username}*" if username else ""
    await safe_reply(
        update,
        "✅ Авторизация подтверждена." + extra +
        "\nВернитесь в браузер — логин завершится автоматически.",
        parse_mode="Markdown"
    )

async def unlink(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Заглушка — настоящий unlink можно реализовать аналогично confirm (отдельный endpoint)
    await safe_reply(update, "ℹ️ Функция отвязки пока не реализована. Напишите, если нужна — я дам код.")

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await safe_reply(update,
        "Инструкция:\n"
        "1. На сайте — «Войти через Telegram».\n"
        "2. Открылся чат со мной → /start login_<token>.\n"
        "3. Я подтверждаю.\n"
        "4. Сайт увидит вход (poll) и авторизует.\n\n"
        "Если долго висит «Ожидание» — сгенерируйте новый токен."
    )

async def fallback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    if text.startswith("/start login_"):
        await safe_reply(update, "⚠️ Формат токена неверный или токен слишком короткий. Сформируйте новый на сайте.")
    else:
        await safe_reply(update, "Отправьте ссылку /start login_<token> или используйте /help.")

# --- Utility reply wrapper --------------------------------------------------

async def safe_reply(update: Update, text: str, **kwargs):
    """
    Безопасно отвечает либо reply, либо sendMessage (если сообщение удалено).
    """
    msg = update.effective_message
    try:
        if msg:
            await msg.reply_text(text, **kwargs)
        else:
            await update.effective_chat.send_message(text, **kwargs)
    except Exception as e:
        log.debug("reply failed: %s", e)

# --- Main -------------------------------------------------------------------

def main():
    log.info(
        "Starting bot (secret=%s)...",
        "set" if BOT_BACKEND_SECRET else "NOT SET (INSECURE MODE)"
    )
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("unlink", unlink))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, fallback))

    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
