import os
import django
import requests
import telebot
from telebot import types

# --- Django initialization ---
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "legitcheck.settings")
django.setup()

from webapp.models import Verdict

API_TOKEN = "7620197633:AAHqBbPgVEtloxy6we7YyvMU7eWK9-hSyrU"
SERVER_URL = "https://legitcheck.one"

bot = telebot.TeleBot(API_TOKEN, parse_mode="HTML")


def fetch_verdict_by_code(code):
    """Return Verdict instance and first photo path for given code."""
    try:
        verdict = Verdict.objects.prefetch_related("photos").get(code__iexact=code)
    except Verdict.DoesNotExist:
        return None, None

    first = verdict.photos.first()
    photo_path = first.image.path if first else None
    return verdict, photo_path


@bot.message_handler(commands=["start"])
def handle_start(message: telebot.types.Message):
    """Handle /start with either a verdict code or login token."""
    parts = message.text.split(maxsplit=1)
    args = parts[1].strip() if len(parts) > 1 else ""

    if not args:
        bot.reply_to(
            message,
            "❗️ Пожалуйста, запускайте бота по ссылке вида https://t.me/YourBot?start=<token>.",
        )
        return

    if args.startswith("login_"):
        token = args[len("login_"):]
        payload = {
            "token": token,
            "user": {
                "id": message.from_user.id,
                "first_name": message.from_user.first_name or "",
                "last_name": message.from_user.last_name or "",
                "username": message.from_user.username or "",
            },
        }
        try:
            r = requests.post(f"{SERVER_URL}/pc/telegram/bot-login/", json=payload, timeout=5)
            if r.ok:
                bot.reply_to(message, "Вы успешно авторизованы на сайте.")
            else:
                bot.reply_to(message, f"Ошибка авторизации: {r.text}")
        except Exception:
            bot.reply_to(message, "Не удалось связаться с сервером.")
        return

    code = args
    verdict, photo_path = fetch_verdict_by_code(code)
    if not verdict:
        bot.reply_to(message, f"❌ Вердикт с кодом <b>{code}</b> не найден.")
        return

    webapp_url = f"{SERVER_URL}/verdict?code={code}"
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton(text="🔗 Открыть веб-приложение", web_app=types.WebAppInfo(url=webapp_url)))

    caption = (
        f"<b>Код:</b> {verdict.code}\n"
        f"<b>Категория вещи:</b> {verdict.get_category_display()}\n"
        f"<b>Бренд:</b> {verdict.brand}\n"
        f"<b>Модель:</b> {verdict.item_model}\n"
        f"<b>Статус проверки:</b> {verdict.get_status_display()}\n"
        f"<b>Дата:</b> {verdict.created_at:%Y-%m-%d %H:%M}\n"
        f"<b>Комментарий:</b> {verdict.comment}\n"
        f"<b>Комментарий пользователя:</b> {verdict.comment_from_user}"
    )

    if photo_path and os.path.exists(photo_path):
        with open(photo_path, "rb") as f:
            bot.send_photo(message.chat.id, f, caption=caption, reply_markup=markup)
    else:
        bot.send_message(message.chat.id, caption, reply_markup=markup)


def main():
    bot.infinity_polling()


if __name__ == "__main__":
    main()
