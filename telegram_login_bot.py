# telegram_login_bot.py
import os
import django
import logging
import re

from datetime import timedelta
from asgiref.sync import sync_to_async
from django.utils import timezone
from django.db import transaction

from telegram import Update
from telegram.ext import (
    ApplicationBuilder, MessageHandler, CommandHandler,
    ContextTypes, filters
)

# --- Django setup ---
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "legitcheck.settings")
django.setup()

from webapp.models import User
from pcwebapp.models import LoginToken

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN_PATTERN = re.compile(r"[A-Z0-9]{6}")

# Плейсхолдер аватарки, если у пользователя нет фотографии
DEFAULT_AVATAR_URL = "/static/avatar.png"

# ========== DB HELPERS ==========

@sync_to_async
def get_token(code: str):
    return (LoginToken.objects
            .select_related('user')
            .get(token=code, used_at__isnull=True))

@sync_to_async
@transaction.atomic
def finalize_token(token_obj, user_data: dict):
    """
    Заполняет все поля User. Если юзер уже есть — обновляем только пустые/изменившиеся.
    user_data = {
        'tgId': int,
        'username': str|None,
        'full_name': str,
        'photo_url': str|None,
        'default_balance': str
    }
    """
    if token_obj.expires_at and token_obj.expires_at < timezone.now():
        raise ValueError("expired")

    tg_id = user_data['tgId']
    username = user_data.get('username')
    full_name = user_data.get('full_name') or f"tg_{tg_id}"
    photo_url = user_data.get('photo_url') or DEFAULT_AVATAR_URL
    default_balance = user_data.get('default_balance', "0")

    user, created = User.objects.get_or_create(
        tgId=tg_id,
        defaults={
            "username": username,
            "name": full_name,
            "img": photo_url,
            "balance": default_balance,
        }
    )

    # Если существующий пользователь — обновляем поля, если они пустые или изменились
    changed = False

    if username and user.username != username:
        user.username = username
        changed = True

    if full_name and user.name != full_name:
        user.name = full_name
        changed = True

    if user.img != photo_url:
        user.img = photo_url
        changed = True

    # Если баланс пустой — задаём дефолт
    if not user.balance:
        user.balance = default_balance
        changed = True

    if changed:
        user.save(update_fields=["username", "name", "img", "balance"])

    token_obj.user = user
    token_obj.telegram_id = tg_id
    token_obj.used_at = timezone.now()
    token_obj.save(update_fields=["user", "telegram_id", "used_at"])

    return user

# ========== BOT HANDLERS ==========

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Пришлите мне ваш одноразовый код (6 символов A-Z0-9), который отображается на сайте."
    )


async def fetch_avatar_url(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> str | None:
    """
    Пытаемся получить URL аватарки:
    1) get_user_profile_photos (самый большой size)
    2) fallback -> get_chat().photo.big_file_id
    Возвращает прямой URL (можете заменить на локальное сохранение).
    """
    # 1. Основной способ
    try:
        photos = await context.bot.get_user_profile_photos(user_id=user_id, limit=1)
        if photos.total_count:
            sizes = photos.photos[0]
            largest = sizes[-1]
            file = await context.bot.get_file(largest.file_id)
            url = f"https://api.telegram.org/file/bot{context.bot.token}/{file.file_path}"
            logger.info("Avatar via get_user_profile_photos user=%s url=%s", user_id, url)
            return url
        else:
            logger.info("No photos via get_user_profile_photos for user=%s — trying get_chat fallback", user_id)
    except Exception:
        logger.exception("Error get_user_profile_photos for user=%s", user_id)

    # 2. Fallback: get_chat
    try:
        chat = await context.bot.get_chat(user_id)
        if chat and chat.photo:
            # big_file_id чаще 640x640
            file = await context.bot.get_file(chat.photo.big_file_id)
            url = f"{file.file_path}"
            logger.info("Avatar via get_chat fallback user=%s url=%s", user_id, url)
            return url
        else:
            logger.info("get_chat has no photo for user=%s", user_id)
    except Exception:
        logger.exception("Error get_chat fallback for user=%s", user_id)

    # Если аватар не найден, используем плейсхолдер
    return DEFAULT_AVATAR_URL



async def fetch_profile_photo_url(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> str | None:
    try:
        photos = await context.bot.get_user_profile_photos(user_id=user_id, limit=1)
        print('photos', photos)
        if not photos.total_count:
            return None
        # берем самый большой вариант
        photo_sizes = photos.photos[0]
        largest = photo_sizes[-1]  # последний — самый большой
        file = await context.bot.get_file(largest.file_id)
        url = f"https://api.telegram.org/file/bot{context.bot.token}/{file.file_path}"
        logger.info("Fetched avatar for %s: %s", user_id, url)
        return url
    except Exception:
        logger.exception("Не удалось получить аватар пользователя %s", user_id)
        return None


async def handle_token(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    raw = update.message.text.strip().upper()

    if not TOKEN_PATTERN.fullmatch(raw):
        await update.message.reply_text("Формат токена неверен. Нужно 6 символов A-Z0-9.")
        return

    try:
        token_obj = await get_token(raw)
    except LoginToken.DoesNotExist:
        await update.message.reply_text("Токен не найден или уже использован.")
        return
    except Exception:
        logger.exception("DB error fetching token")
        await update.message.reply_text("Временная ошибка. Попробуйте позже.")
        return

    # Дополнительная проверка срока
    if token_obj.expires_at and token_obj.expires_at < timezone.now():
        await update.message.reply_text("Токен истёк.")
        return

    tg_user = update.effective_user

    # Получаем аватар (не блокируем, но ждём)
    photo_url = await fetch_avatar_url(tg_user.id, context)

    full_name = (tg_user.first_name or "") + (" " + tg_user.last_name if tg_user.last_name else "")
    full_name = full_name.strip()

    try:
        user = await finalize_token(
            token_obj,
            {
                "tgId": tg_user.id,
                "username": tg_user.username,
                "full_name": full_name,
                "photo_url": photo_url,
                "default_balance": "0",  # Можете поменять на стартовый бонус, например '100'
            }
        )
    except ValueError as e:
        if str(e) == "expired":
            await update.message.reply_text("Токен истёк.")
        else:
            await update.message.reply_text("Ошибка токена.")
        return
    except Exception:
        logger.exception("DB error finalizing token")
        await update.message.reply_text("Ошибка сервера.")
        return

    await update.message.reply_text(
        f"Успешно! Пользователь {user.name} (@{user.username}) авторизован. Вернитесь на сайт."
    )

def main():
    bot_token = "7620197633:AAHqBbPgVEtloxy6we7YyvMU7eWK9-hSyrU"  # Замените / вынесите в env
    app = ApplicationBuilder().token(bot_token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_token))
    app.run_polling()

if __name__ == "__main__":
    main()
