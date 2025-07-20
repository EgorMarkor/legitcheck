import hashlib
import hmac
import json
import logging
import time
from urllib.parse import unquote

from django.conf import settings
from django.contrib.sessions.backends.db import SessionStore
from django.contrib.auth import login
from django.http import HttpResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import render, redirect
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from webapp.models import User  # ваша модель webapp.User
from .decorators import webapp_login_required
from .models import LoginToken

logger = logging.getLogger(__name__)

TELEGRAM_LOGIN_MAX_AGE = 300  # секунд

def get_or_create_user(telegram_id):
    user, created = User.objects.get_or_create(
        telegram_id=telegram_id,
        defaults={'username': f'tg_{telegram_id}'}
    )
    return user

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



@require_POST
def telegram_request_login(request):
    if not request.session.session_key:
        request.session.create()
    # Rate limit (простая версия)
    recent = LoginToken.objects.filter(
        session_key=request.session.session_key,
        created_at__gt=timezone.now()-timezone.timedelta(seconds=10)
    ).count()
    if recent > 3:
        return JsonResponse({'error':'rate_limited'}, status=429)

    rec = LoginToken.create_for_session(request.session.session_key)
    start_link = f"https://t.me/LegitLogisticsBot?start=login_{rec.token}"
    return JsonResponse({"token": rec.token, "start_link": start_link})


@csrf_exempt
@require_POST
def telegram_bot_login(request):
    """Endpoint called by Telegram bot to complete login."""
    try:
        data = json.loads(request.body.decode())
    except Exception:
        return JsonResponse({"error": "invalid json"}, status=400)

    token = data.get("token")
    user_data = data.get("user") or {}
    if not token or "id" not in user_data:
        return JsonResponse({"error": "missing params"}, status=400)

    login_token = LoginToken.objects.filter(token=token, used=False).first()
    if not login_token:
        return JsonResponse({"error": "bad token"}, status=400)

    tg_id = str(user_data["id"])
    full_name = (user_data.get("first_name", "") + " " + user_data.get("last_name", "")).strip()
    username = user_data.get("username") or ""
    photo_url = user_data.get("photo_url", "")

    user, created = User.objects.get_or_create(
        tgId=tg_id,
        defaults={"name": full_name, "username": username, "img": photo_url},
    )
    if not created:
        changed = False
        if full_name and user.name != full_name:
            user.name = full_name
            changed = True
        if username and user.username != username:
            user.username = username
            changed = True
        if photo_url and user.img != photo_url:
            user.img = photo_url
            changed = True
        if changed:
            user.save()

    # update session referenced by token
    if login_token.session_key:
        store = SessionStore(session_key=login_token.session_key)
        store["webapp_user_tgId"] = tg_id
        store.save()

    login_token.user = user
    login_token.used = True
    login_token.save()

    return JsonResponse({"status": "ok"})


from django.views.decorators.csrf import csrf_exempt
from django.db import transaction

@csrf_exempt  # вызвать только с вашего бота (ограничьте по IP / секретному заголовку)
@require_POST
def telegram_confirm_token(request):
    import json
    data = json.loads(request.body.decode())
    token = data.get('token')
    tg_id = data.get('telegram_id')
    if not token or not tg_id:
        return HttpResponseBadRequest("missing fields")
    with transaction.atomic():
        try:
            rec = LoginToken.objects.select_for_update().get(pk=token, used=False)
        except LoginToken.DoesNotExist:
            return JsonResponse({'ok': False, 'reason':'not_found'})
        if rec.expires_at < timezone.now():
            return JsonResponse({'ok': False, 'reason':'expired'})
        rec.used = True
        rec.telegram_id = tg_id
        rec.save(update_fields=['used','telegram_id'])
    return JsonResponse({'ok': True})


def telegram_login(request):
    """
    Обрабатывает callback Telegram Login Widget.
    НЕТ ни одного redirect на главную.
    Только:
      - redirect на next (если валидно)
      - redirect на pc_account (успех)
      - HTTP 4xx/5xx ответы (ошибки)
    """
    if request.method != "GET":
        return HttpResponseBadRequest("Неверный метод (ожидается GET)")

    if 'hash' not in request.GET:
        logger.warning("Telegram login: нет параметров hash. GET=%s", dict(request.GET))
        return HttpResponseBadRequest("Нет параметров Telegram")

    ok, data, reason = verify_telegram_auth(request.GET, max_age=TELEGRAM_LOGIN_MAX_AGE)
    if not ok:
        logger.warning("Telegram login: verify FAILED: %s | raw=%s", reason, dict(request.GET))
        return HttpResponseBadRequest(f"Ошибка Telegram верификации: {reason}")

    tg_id = str(data['id'])
    full_name = (data.get('first_name', '') + ' ' + data.get('last_name', '')).strip()
    username = data.get('username') or ''
    photo_url = data.get('photo_url', '')

    user, created = User.objects.get_or_create(
        tgId=tg_id,
        defaults={'name': full_name, 'username': username, 'img': photo_url}
    )

    if not created:
        changed = False
        if full_name and user.name != full_name:
            user.name = full_name; changed = True
        if username and user.username != username:
            user.username = username; changed = True
        if photo_url and user.img != photo_url:
            user.img = photo_url; changed = True
        if changed:
            user.save()

    # Сохраняем идентификатор авторизованного пользователя в сессии
    request.session['webapp_user_tgId'] = tg_id

    # Обработка next
    next_url = request.GET.get('next')
    if next_url:
        next_url = unquote(next_url)
        if url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
            logger.info("Telegram login success (user=%s). Redirect to next=%s", user.pk, next_url)
            return redirect(next_url)
        else:
            logger.warning("Telegram login: отклонён небезопасный next=%s", next_url)

    logger.info("Telegram login success (user=%s). Redirect to pc_account", user.pk)
    return redirect('pc_account')


def telegram_logout(request):
    """
    Выход из Telegram сессии.
    Здесь ТАКЖЕ не редиректим на главную.
    Можешь поменять поведение на JsonResponse.
    """
    request.session.pop('webapp_user_tgId', None)
    # Можно вернуть пользователя к странице аккаунта (где увидит, что не авторизован)
    return HttpResponse("Вы вышли из Telegram-сессии.")


def verify_telegram_auth(params, max_age=86400):
    """
    Проверка подписи Telegram.
    Возвращает (ok: bool, cleaned_dict | None, reason: str | None)
    Никаких редиректов внутри — только логика.
    """
    try:
        data = dict(params.items())
    except Exception as e:
        return False, None, f"ошибка чтения параметров: {e}"

    hash_received = data.pop('hash', None)
    if not hash_received:
        return False, None, "hash отсутствует"

    # Составляем строку в формате k=v (отсортировано по ключу)
    check_pairs = [f"{k}={data[k]}" for k in sorted(data.keys())]
    data_check_string = "\n".join(check_pairs)

    secret_key = hashlib.sha256(settings.TELEGRAM_BOT_TOKEN.encode()).digest()
    calc_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(calc_hash, hash_received):
        return False, None, "подпись не совпала"

    try:
        auth_date = int(data.get('auth_date', 0))
    except (ValueError, TypeError):
        return False, None, "auth_date не число"

    now_ts = int(time.time())
    if now_ts - auth_date > max_age:
        return False, None, "истёк срок auth_date"

    # (не обязательно) проверка на слишком будущую дату
    if auth_date > now_ts + 300:
        return False, None, "auth_date из будущего"

    data['hash'] = hash_received
    return True, data, None


def tg_auth(request):
    return render(request, 'pc/tg_auth.html')



def tg_auth_finish(request):
    # Просто отобразим параметры (GET)
    # Список ключей может быть расширен, но берём стандартные
    data = {k: request.GET.get(k) for k in [
        'id','first_name','last_name','username','photo_url','auth_date','hash'
    ] if request.GET.get(k) is not None}

    # НЕ проверяем здесь — проверим уже после postMessage на основном окне (или можете здесь же)
    json_data = json.dumps(data, ensure_ascii=False)

    return HttpResponse(f"""
<!doctype html>
<html><head><meta charset="utf-8"><title>Telegram Auth Finish</title>
<style>
body {{ font-family: sans-serif; background:#111; color:#eee; text-align:center; padding:30px; }}
small {{ display:block; opacity:.6; margin-top:1rem; }}
button {{ padding: .6rem 1.2rem; border-radius:6px; background:#2d8cff; color:#fff; border:none; cursor:pointer; }}
</style>
</head>
<body>
<h3>Авторизация Telegram...</h3>
<script>
  (function() {{
    var data = {json_data};
    if (window.opener && !window.opener.closed) {{
      window.opener.postMessage({{ source:'telegram-auth', user:data }}, window.location.origin);
      // Подождём чуть-чуть и закроем
      setTimeout(function() {{ window.close(); }}, 1200);
    }} else {{
      document.write('<p>Главное окно закрыто. Скопируйте данные вручную.</p>');
      document.write('<pre>'+JSON.stringify(data,null,2)+'</pre>');
    }}
  }})();
</script>
<small>Можно закрыть это окно.</small>
</body></html>
    """)
    
    
@require_GET
def telegram_check_login(request):
    token = request.GET.get('token')
    if not token:
        return HttpResponseBadRequest("missing token")
    try:
        rec = LoginToken.objects.get(pk=token)
    except LoginToken.DoesNotExist:
        return JsonResponse({'status':'invalid'})
    # Привязка к текущей сессии
    if rec.session_key != request.session.session_key:
        return JsonResponse({'status':'forbidden'}, status=403)
    if rec.expires_at < timezone.now():
        return JsonResponse({'status':'expired'})
    if rec.used and rec.telegram_id:
        user = get_or_create_user(rec.telegram_id)
        if not request.user.is_authenticated:
            login(request, user)
        return JsonResponse({'logged': True})
    return JsonResponse({'logged': False, 'status':'pending'})
