from django.shortcuts import render
import hashlib
import hmac
import time
from django.conf import settings
from django.contrib.auth import login
from django.shortcuts import redirect
from django.contrib.auth.models import User
from django.http import HttpResponseBadRequest

# Create your views here.
def home(request):
    """
    Главная страница.
    """
    return render(request, 'index.html')


def start_check(request):
    """
    Главная страница.
    """
    return render(request, 'check.html')


def pay(request):
    return render(request, 'pay.html')

def account(request):
    return render(request, 'account.html')


def user_agree(request):
    return render(request, 'user_agree.html')


def privacy_policy(request):
    return render(request, 'privacy_policy.html')


def verdicts(request):
    return render(request, 'verdicts.html')


def home_page(request):
    return render(request, 'home_page.html')


def verify_telegram_auth(request):
    data = request.GET.copy()
    hash_received = data.pop('hash', [None])[0]
    if not hash_received:
        return False

    # 1) собрать data_check_string
    items = []
    for key in sorted(data.keys()):
        for val in data.getlist(key):
            items.append(f"{key}={val}")
    data_check_string = "\n".join(items)

    # 2) секретный ключ
    bot_token = settings.TELEGRAM_BOT_TOKEN
    secret_key = hashlib.sha256(bot_token.encode()).digest()

    # 3) вычислить HMAC
    hmac_obj = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256)
    hash_calculated = hmac_obj.hexdigest()

    # 4) проверить совпадение
    if not hmac.compare_digest(hash_calculated, hash_received):
        return False

    # 5) проверить свежесть (не старше 5 минут)
    auth_date = int(data.get('auth_date', 0))
    if time.time() - auth_date > 300:
        return False

    # Всё ок
    return True, data

def telegram_login(request):
    ok = verify_telegram_auth(request)
    if not ok:
        return HttpResponseBadRequest("Неверная подпись Telegram")

    verified, data = ok
    # Здесь data — dict с полями: id, first_name, last_name, username, photo_url, auth_date
    tg_id = data.get('id')
    username = data.get('username', f"tg_{tg_id}")

    # Попробуем найти или создать пользователя Django
    user, created = User.objects.get_or_create(
        username=f"tg_{tg_id}",
        defaults={
            'first_name': data.get('first_name', ''),
            'last_name': data.get('last_name', ''),
        }
    )

    # Авторизуем
    login(request, user)

    # Перенаправляем туда, куда нужно
    return redirect('home')