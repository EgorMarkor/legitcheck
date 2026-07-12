import asyncio
import logging
import os
import re

import django
from asgiref.sync import sync_to_async
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
from telegram.error import NetworkError
from telegram.request import HTTPXRequest

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "legitcheck.settings")
django.setup()

from pcwebapp.models import LoginToken
from webapp import telegram as tg_service
from webapp.models import TelegramVerdictDelivery, User, Verdict

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)

TOKEN_PATTERN = re.compile(r"[A-Z0-9]{6}")
DEFAULT_AVATAR_URL = "/static/avatar-placeholder.png"


class LoginTokenError(Exception):
    pass


class LoginTokenExpired(LoginTokenError):
    pass


class LoginTokenUnavailable(LoginTokenError):
    pass


@transaction.atomic
def _claim_login_token(code: str, user_data: dict):
    """Atomically claim a one-time code and attach it to a Telegram user."""
    now = timezone.now()
    tg_id = user_data["tgId"]

    claimed = LoginToken.objects.filter(
        token=code,
        used_at__isnull=True,
        expires_at__gt=now,
    ).update(
        used_at=now,
        telegram_id=tg_id,
    )
    if claimed != 1:
        token = LoginToken.objects.filter(token=code).only("expires_at").first()
        if token and token.expires_at <= now:
            raise LoginTokenExpired
        raise LoginTokenUnavailable

    username = user_data.get("username")
    full_name = user_data.get("full_name") or f"tg_{tg_id}"
    user, _ = User.objects.get_or_create(
        tgId=tg_id,
        defaults={
            "username": username,
            "name": full_name,
            "img": DEFAULT_AVATAR_URL,
            "balance": "0",
        },
    )

    changed_fields = []
    if user.username != username:
        user.username = username
        changed_fields.append("username")
    if user.name != full_name:
        user.name = full_name
        changed_fields.append("name")
    if not user.balance:
        user.balance = "0"
        changed_fields.append("balance")

    if changed_fields:
        user.save(update_fields=changed_fields)

    LoginToken.objects.filter(token=code).update(user=user)
    return user


claim_login_token = sync_to_async(_claim_login_token, thread_sensitive=True)


@transaction.atomic
def _apply_verdict_decision(verdict_id: int, decision: str):
    if decision not in {"legit", "fake", "todo"}:
        raise ValueError("Unsupported verdict decision")
    verdict = Verdict.objects.select_for_update().select_related("user").get(pk=verdict_id)
    verdict.status = decision
    verdict.save(update_fields=["status"])
    delivery = TelegramVerdictDelivery.objects.filter(verdict=verdict, active=True).first()
    delivery_data = None
    if delivery:
        delivery_data = (delivery.chat_id, list(delivery.message_ids or []))
        delivery.message_ids = []
        delivery.active = False
        delivery.save(update_fields=["message_ids", "active", "updated_at"])
    return verdict.code, verdict.user.tgId, delivery_data


apply_verdict_decision = sync_to_async(_apply_verdict_decision, thread_sensitive=True)


@sync_to_async(thread_sensitive=True)
def _save_avatar(user_id: int, avatar_url: str):
    User.objects.filter(pk=user_id).exclude(img=avatar_url).update(img=avatar_url)


async def refresh_avatar(user_id: int, telegram_id: int, bot_token: str):
    try:
        avatar_url = await sync_to_async(
            tg_service.download_and_cache_avatar,
            thread_sensitive=True,
        )(bot_token, telegram_id)
        if avatar_url:
            await _save_avatar(user_id, avatar_url)
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("Failed to refresh avatar for telegram_id=%s", telegram_id)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    await update.message.reply_text(
        "Пришлите мне ваш одноразовый код (6 символов A-Z0-9), который отображается на сайте."
    )


async def handle_token(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    raw = update.message.text.strip().upper()
    if not TOKEN_PATTERN.fullmatch(raw):
        await update.message.reply_text(
            "Формат токена неверен. Нужно 6 символов A-Z0-9."
        )
        return

    tg_user = update.effective_user
    if not tg_user:
        await update.message.reply_text("Не удалось определить пользователя Telegram.")
        return

    full_name = " ".join(
        part for part in (tg_user.first_name, tg_user.last_name) if part
    )
    try:
        user = await claim_login_token(
            raw,
            {
                "tgId": tg_user.id,
                "username": tg_user.username,
                "full_name": full_name,
            },
        )
    except LoginTokenExpired:
        await update.message.reply_text("Токен истёк.")
        return
    except LoginTokenUnavailable:
        await update.message.reply_text("Токен не найден или уже использован.")
        return
    except Exception:
        logger.exception("Failed to finalize login token")
        await update.message.reply_text("Ошибка сервера.")
        return

    username = f" (@{user.username})" if user.username else ""
    await update.message.reply_text(
        f"Успешно! Пользователь {user.name}{username} авторизован. Вернитесь на сайт."
    )
    context.application.create_task(
        refresh_avatar(user.pk, tg_user.id, context.bot.token),
        update=update,
    )


async def handle_verdict_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query or not query.data:
        return
    try:
        _, verdict_id, decision = query.data.split(":")
        code, user_tg_id, delivery_data = await apply_verdict_decision(int(verdict_id), decision)
    except (ValueError, Verdict.DoesNotExist):
        await query.answer("Вердикт не найден или данные некорректны", show_alert=True)
        return

    await query.answer("Решение сохранено")
    if delivery_data:
        chat_id, message_ids = delivery_data
        for message_id in message_ids:
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
            except Exception:
                logger.warning("Failed to delete verdict message chat=%s message=%s", chat_id, message_id)

    messages = {
        "legit": f"✅ Проверка {code} завершена: вынесен вердикт «Оригинал».",
        "fake": f"❌ Проверка {code} завершена: вынесен вердикт «Не оригинал».",
        "todo": (
            f"📷 Для проверки {code} нужны дополнительные фотографии. "
            f"Загрузите их на странице {settings.PUBLIC_BASE_URL.rstrip('/')}/verdict/?code={code}"
        ),
    }
    try:
        await context.bot.send_message(chat_id=user_tg_id, text=messages[decision])
    except Exception:
        logger.warning("Failed to notify Telegram user %s about verdict %s", user_tg_id, code)


async def handle_error(update: object, context: ContextTypes.DEFAULT_TYPE):
    error = context.error
    if error is None:
        logger.error("Telegram bot error handler called without an exception")
        return
    if isinstance(error, NetworkError):
        logger.warning("Temporary Telegram network error: %s", type(error).__name__)
        return
    logger.error(
        "Unhandled Telegram bot error",
        exc_info=(type(error), error, error.__traceback__),
    )


def _build_request(proxy_url: str, *, read_timeout: float, pool_size: int):
    kwargs = {
        "connection_pool_size": pool_size,
        "connect_timeout": 5,
        "read_timeout": read_timeout,
        "write_timeout": 15,
        "pool_timeout": 5,
    }
    if proxy_url:
        kwargs["proxy"] = proxy_url
    return HTTPXRequest(**kwargs)


def main():
    bot_token = settings.TELEGRAM_BOT_TOKEN
    if not bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not configured")

    proxy_url = getattr(settings, "TELEGRAM_API_PROXY", "")
    builder = (
        ApplicationBuilder()
        .token(bot_token)
        .request(_build_request(proxy_url, read_timeout=15, pool_size=8))
        .get_updates_request(_build_request(proxy_url, read_timeout=35, pool_size=1))
    )
    app = builder.build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(handle_verdict_callback, pattern=r"^verdict:\d+:(legit|fake|todo)$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_token))
    app.add_error_handler(handle_error)
    app.run_polling()


if __name__ == "__main__":
    main()
