import os
import django
from django.utils import timezone

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'legitcheck.settings')
django.setup()

from telegram import Update
from telegram.ext import Application, MessageHandler, CommandHandler, filters, ContextTypes
from pcwebapp.models import LoginToken
from webapp.models import User

BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', 'YOUR_TOKEN')

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text('Send the login code you received on the site.')

async def handle_token(update: Update, context: ContextTypes.DEFAULT_TYPE):
    code = update.message.text.strip()
    try:
        token = LoginToken.objects.get(token=code, used_at__isnull=True)
    except LoginToken.DoesNotExist:
        await update.message.reply_text('Invalid or expired code.')
        return
    if token.is_expired():
        await update.message.reply_text('Code expired.')
        return
    tg_id = update.effective_user.id
    username = update.effective_user.username or ''
    user, _ = User.objects.get_or_create(tgId=tg_id, defaults={'username': username, 'img': '', 'name': username, 'balance': '0'})
    token.user = user
    token.used_at = timezone.now()
    token.save(update_fields=['user', 'used_at'])
    await update.message.reply_text('Authentication successful. Return to the website.')


def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler('start', start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_token))
    app.run_polling()


if __name__ == '__main__':
    main()
