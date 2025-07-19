from django.shortcuts import render
import hashlib
import hmac
import time
from django.conf import settings
from django.shortcuts import redirect
from django.http import HttpResponseBadRequest
from webapp.models import User  # ваша модель webapp.User
from .decorators import webapp_login_required

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

@webapp_login_required
def account(request):
    user = request.webapp_user
    verdicts = user.verdicts.all().order_by('-created_at')
    return render(request, 'account.html', {
        'user': user,
        'verdicts': verdicts,
    })


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
        return False, None

    items = []
    for key in sorted(data.keys()):
        for val in data.getlist(key):
            items.append(f"{key}={val}")
    data_check_string = "\n".join(items)

    secret_key = hashlib.sha256(settings.TELEGRAM_BOT_TOKEN.encode()).digest()
    hmac_obj    = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256)
    if not hmac.compare_digest(hmac_obj.hexdigest(), hash_received):
        return False, None

    if time.time() - int(data.get('auth_date', 0)) > 300:
        return False, None

    return True, data

def telegram_login(request):
    ok, data = verify_telegram_auth(request)
    if not ok:
        return HttpResponseBadRequest("Неверная подпись Telegram")

    tg_id     = int(data['id'])
    img_url   = data.get('photo_url', '')
    full_name = (data.get('first_name','') + ' ' + data.get('last_name','')).strip()
    username  = data.get('username')

    user, created = User.objects.get_or_create(
        tgId=tg_id,
        defaults={
            'img':      img_url,
            'name':     full_name,
            'username': username,
        }
    )
    if not created:
        # обновляем данные на всякий случай
        user.img      = img_url
        user.name     = full_name
        user.username = username
        user.save()

    request.session['webapp_user_tgId'] = user.tgId

    return redirect('account')  # куда угодно внутри webapp

def telegram_logout(request):
    request.session.pop('webapp_user_tgId', None)
    return redirect('home')
