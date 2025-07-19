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
    """
    Принимает либо GET параметры (классический redirect),
    либо POST JSON (ваш кастомный фронтенд).
    """
    # 1. Собираем входные данные
    if request.method == 'POST' and request.content_type.startswith('application/json'):
        try:
            raw = request.body.decode('utf-8')
            data = json.loads(raw)
        except Exception:
            return HttpResponseBadRequest('Некорректный JSON')
    else:
        # QueryDict -> обычный dict (последнее значение каждого ключа)
        data = request.GET.dict()

    # 2. Проверка подписи
    ok, cleaned = verify_telegram_auth_dict(data, max_age=TELEGRAM_LOGIN_MAX_AGE)
    if not ok:
        if request.method == 'POST':
            return HttpResponseBadRequest("Неверная подпись Telegram")
        return HttpResponseBadRequest("Неверная подпись Telegram")

    # 3. Извлекаем данные
    tg_id = int(cleaned['id'])
    img_url = cleaned.get('photo_url', '')
    full_name = (cleaned.get('first_name', '') + ' ' + cleaned.get('last_name', '')).strip()
    username = cleaned.get('username') or ''

    user, created = User.objects.get_or_create(
        tgId=tg_id,
        defaults={
            'img': img_url,
            'name': full_name,
            'username': username,
        }
    )
    if not created:
        # обновляем (опционально можно делать через update_fields)
        if img_url:
            user.img = img_url
        if full_name:
            user.name = full_name
        if username:
            user.username = username
        user.save()

    # 4. Сессия
    request.session['webapp_user_tgId'] = user.tgId

    # 5. next (только если он пришёл в query — в POST логично передавать тоже query строкой)
    next_url = request.GET.get('next')
    if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
        if request.method == 'POST':
            return JsonResponse({'status': 'ok', 'redirect': next_url})
        return redirect(next_url)

    # 6. Ответ
    if request.method == 'POST':
        return JsonResponse({'status': 'ok'})
    return redirect('pc_account')

def verify_telegram_auth_dict(data: dict, max_age=300):
    """
    Проверяет словарь параметров Telegram Login.
    Ожидает presence hash. Возвращает (bool, cleaned_data).
    """
    hash_received = data.get('hash')
    if not hash_received:
        return False, None

    # формируем список key=value для всех, кроме hash
    items = []
    for key in sorted(k for k in data.keys() if k != 'hash'):
        # все значения приводим к str
        items.append(f"{key}={data[key]}")

    data_check_string = "\n".join(items)

    # секрет = sha256(BOT_TOKEN)
    secret_key = hashlib.sha256(settings.TELEGRAM_BOT_TOKEN.encode('utf-8')).digest()
    calc_hash = hmac.new(secret_key, data_check_string.encode('utf-8'), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(calc_hash, hash_received):
        return False, None

    # проверка времени
    try:
        auth_date = int(data.get('auth_date', 0))
    except ValueError:
        return False, None

    if time.time() - auth_date > max_age:
        return False, None

    return True, data



def telegram_logout(request):
    request.session.pop('webapp_user_tgId', None)
    return redirect('pc_home')
