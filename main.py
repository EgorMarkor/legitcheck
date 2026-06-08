import os
import django
from aiogram import Bot, Dispatcher, executor, types
from asgiref.sync import sync_to_async
from aiogram.types import WebAppInfo, InlineKeyboardMarkup, InlineKeyboardButton
from django.conf import settings

# --- Инициализация Django ---
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "legitcheck.settings")
django.setup()

from webapp.models import Verdict

API_TOKEN = getattr(settings, "TELEGRAM_BOT_TOKEN", "")
if not API_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN is not configured")
TELEGRAM_API_PROXY = getattr(settings, "TELEGRAM_API_PROXY", "")
bot_kwargs = {
    "token": API_TOKEN,
    "parse_mode": types.ParseMode.HTML,
}
if TELEGRAM_API_PROXY:
    bot_kwargs["proxy"] = TELEGRAM_API_PROXY
bot = Bot(**bot_kwargs)
dp = Dispatcher(bot)
DEFAULT_PUBLIC_BASE_URL = "https://legitcheck.one"


# Синхронный доступ к одному Verdict по коду + первая фотография
@sync_to_async
def fetch_verdict_by_code(code):
    try:
        v = Verdict.objects.prefetch_related('photos').get(code__iexact=code)
    except Verdict.DoesNotExist:
        return None, None

    first = v.photos.first()
    photo_path = first.image.path if first else None
    return v, photo_path


@sync_to_async
def update_verdict_status(verdict_id, decision):
    try:
        verdict = Verdict.objects.get(pk=verdict_id)
    except Verdict.DoesNotExist:
        return None
    if decision not in {"legit", "fake"}:
        return None
    verdict.status = decision
    verdict.save(update_fields=["status"])
    return verdict


def build_admin_verdict_url(verdict):
    base_url = getattr(settings, "PUBLIC_BASE_URL", DEFAULT_PUBLIC_BASE_URL).rstrip("/")
    return f"{base_url}/admin/webapp/verdict/{verdict.id}/change/"


def build_verdict_message(verdict, include_prompt=False):
    comment_from_user = verdict.comment_from_user or "—"
    item_model = verdict.item_model or "—"
    admin_url = build_admin_verdict_url(verdict)
    lines = [
        "Новый вердикт поступил",
        f"Код: {verdict.code}",
        f"Пользователь: {verdict.user.name}",
        f"Категория: {verdict.get_category_display()}",
        f"Бренд: {verdict.brand}",
        f"Модель: {item_model}",
        f"Комментарий пользователя: {comment_from_user}",
        f"Статус: {verdict.get_status_display()}",
        f"Админка: {admin_url}",
    ]
    if include_prompt:
        lines.append("Выберите вердикт для позиции.")
    return "\n".join(lines)


@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    """
    Обрабатывает deep link /start=<code>:
    - если code передан, ищет Verdict по нему и присылает данные
    - иначе просит запустить бота со ссылкой
    """
    args = message.get_args().strip()
    if not args:
        await message.reply("❗️ Пожалуйста, запускайте бота по специальной ссылке вида `https://t.me/YourBot?start=<code>`.")
        return

    code = args
    webapp_url = f"https://legitcheck.one/verdict?code={code}"
    button = InlineKeyboardButton(
        text="🔗 Открыть веб-приложение",
        web_app=WebAppInfo(url=webapp_url)
    )
    markup = InlineKeyboardMarkup().add(button)
    v, photo_path = await fetch_verdict_by_code(code)
    if not v:
        await message.reply(f"❌ Вердикт с кодом <b>{code}</b> не найден.")
        return

    caption = (
        f"<b>Код:</b> {v.code}\n"
        f"<b>Категория вещи:</b> {v.get_category_display()}\n"
        f"<b>Бренд:</b> {v.brand}\n"
        f"<b>Модель:</b> {v.item_model}\n"
        f"<b>Статус проверки:</b> {v.get_status_display()}\n"
        f"<b>Дата:</b> {v.created_at:%Y-%m-%d %H:%M}\n"
        f"<b>Комментарий:</b> {v.comment}\n"
        f"<b>Комментарий пользователя:</b> {v.comment_from_user}"
    )

    if photo_path and os.path.exists(photo_path):
        photo = types.InputFile(photo_path)
        await bot.send_photo(
            chat_id=message.chat.id,
            photo=photo,
            caption=caption,
            reply_markup=markup
        )
    else:
        await message.answer(caption)


@dp.callback_query_handler(lambda query: query.data and query.data.startswith("verdict:"))
async def handle_verdict_callback(query: types.CallbackQuery):
    try:
        _, verdict_id, decision = query.data.split(":")
    except ValueError:
        await query.answer("Некорректные данные")
        return

    verdict = await update_verdict_status(int(verdict_id), decision)
    if not verdict:
        await query.answer("Вердикт не найден")
        return

    await query.answer("Вердикт обновлен")
    if query.message:
        updated_text = build_verdict_message(verdict)
        await query.message.edit_text(updated_text, parse_mode=None, reply_markup=None)


if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)
