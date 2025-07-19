from django.shortcuts import render, redirect
import hashlib
import hmac
import time
import json
from django.conf import settings
from django.utils.http import url_has_allowed_host_and_scheme
from django.http import HttpResponseBadRequest, JsonResponse
from webapp.models import User  # ваша модель webapp.User
from .decorators import webapp_login_required

TELEGRAM_LOGIN_MAX_AGE = 300  # секунд

# Create your views here.
def home(request):
    """
    Главная страница.
    """
    tg_id = request.session.get('webapp_user_tgId')
    print("TGID", tg_id)
    if tg_id:
        request.webapp_user = User.objects.get(tgId=tg_id)
    else:
        request.webapp_user = None
    return render(request, 'pc/index.html')


def start_check(request):
    """
    Главная страница.
    """
    return render(request, 'pc/check.html')


def pay(request):
    return render(request, 'pc/pay.html')

@webapp_login_required
def account(request):
    user = request.webapp_user
    verdicts = user.verdicts.all().order_by('-created_at')
    return render(request, 'pc/account.html', {
        'user': user,
        'verdicts': verdicts,
    })


def user_agree(request):
    return render(request, 'pc/user_agree.html')


def privacy_policy(request):
    return render(request, 'pc/privacy_policy.html')


def verdicts(request):
    return render(request, 'pc/verdicts.html')


def home_page(request):
    return render(request, 'pc/home_page.html')


def telegram_login(request):
    # Параметры должны прийти в GET (redirect или callback onAuth)
    if 'hash' not in request.GET:
        return HttpResponseBadRequest("Нет параметров Telegram")

    ok, data, reason = verify_telegram_auth(request.GET, max_age=TELEGRAM_LOGIN_MAX_AGE)
    if not ok:
        return HttpResponseBadRequest(f"Ошибка Telegram: {reason}")

    tg_id = str(data['id'])  # строкой, чтобы не путаться с типами
    full_name = (data.get('first_name','') + ' ' + data.get('last_name','')).strip()
    username  = data.get('username') or ''
    photo_url = data.get('photo_url','')

    user, created = User.objects.get_or_create(
        tgId=tg_id,
        defaults={'name': full_name, 'username': username, 'img': photo_url}
    )
    if not created:
        # обновляем при наличии новых данных
        changed = False
        if full_name and user.name != full_name: user.name = full_name; changed = True
        if username and user.username != username: user.username = username; changed = True
        if photo_url and user.img != photo_url: user.img = photo_url; changed = True
        if changed: user.save()

    request.session['webapp_user_tgId'] = tg_id

    # next (безопасно)
    next_url = request.GET.get('next')
    if next_url:
        # Декодируем если URL‑encoded (виджет уже закодировал)
        from urllib.parse import unquote
        next_url = unquote(next_url)
        from django.utils.http import url_has_allowed_host_and_scheme
        if url_has_allowed_host_and_scheme(next_url, {request.get_host()}):
            return redirect(next_url)

    return redirect('pc_account')  # или куда нужно

def telegram_logout(request):
    request.session.pop('webapp_user_tgId', None)
    return redirect('pc_home')

def verify_telegram_auth(params, max_age=86400):
    """
    params: QueryDict / dict с параметрами Telegram.
    Возвращает (ok, cleaned_dict, reason)
    """
    data = dict(params.items())
    hash_received = data.pop('hash', None)
    if not hash_received:
        return False, None, "hash отсутствует"

    # формируем data_check_string
    check_pairs = [f"{k}={data[k]}" for k in sorted(data.keys())]
    data_check_string = "\n".join(check_pairs)

    secret_key = hashlib.sha256(settings.TELEGRAM_BOT_TOKEN.encode()).digest()
    calc_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(calc_hash, hash_received):
        return False, None, "подпись не совпала"

    try:
        auth_date = int(data.get('auth_date', 0))
    except ValueError:
        return False, None, "auth_date не число"

    if time.time() - auth_date > max_age:
        return False, None, "истёк срок auth_date"

    # возвращаем dict снова включая hash (если нужно)
    data['hash'] = hash_received
    return True, data, None