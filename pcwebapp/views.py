import re
import functools
from datetime import timedelta

from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.utils.crypto import get_random_string
from django.utils import timezone
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.csrf import csrf_exempt

from .models import LoginToken, Brand
from webapp.models import User, Verdict, VerdictPhoto  # если VerdictPhoto используете

# ---------- Mobile detection ----------
MOBILE_UA_RE = re.compile(
    r"(android|iphone|ipad|ipod|opera mini|blackberry|iemobile|windows phone|webos|mobi)",
    re.I
)
TELEGRAM_BOT_URL = "https://t.me/LegitLogisticsBot?start=login"

def is_mobile(request):
    ua = request.META.get("HTTP_USER_AGENT", "")
    return bool(MOBILE_UA_RE.search(ua))

def mobile_redirect(view_func=None, *, skip_if_authenticated=True):
    """
    Декоратор: если мобильный клиент (по UA) и пользователь не авторизован,
    отправляем в Telegram бота.
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(request, *args, **kwargs):
            if is_mobile(request):
                if not (skip_if_authenticated and request.session.get("tg_id")):
                    return redirect(TELEGRAM_BOT_URL)
            return func(request, *args, **kwargs)
        return wrapper
    if view_func is not None:
        return decorator(view_func)
    return decorator

# ---------- Auth requirement decorator ----------
def _require_tg_user(view_func):
    @functools.wraps(view_func)
    def wrapped(request, *args, **kwargs):
        tg_id = request.session.get('tg_id')
        if not tg_id:
            return redirect('pc_home')
        try:
            request.tg_user = User.objects.get(tgId=tg_id)
        except User.DoesNotExist:
            return redirect('pc_home')
        return view_func(request, *args, **kwargs)
    return wrapped

# ---------- Views ----------

@mobile_redirect  # применяем: телефон -> Telegram
def home(request):
    """
    Главная страница (desktop / уже авторизованные мобильные).
    """
    tg_id = request.session.get('tg_id')
    if tg_id:
            return redirect('pc_home_page')
    sneakers = Brand.objects.filter(category='sneakers')
    return render(request, 'pc/index.html', {'sneakers': sneakers})


@_require_tg_user
def start_check(request):
    return render(request, 'pc/check.html', {'tg_user': request.tg_user})


@_require_tg_user
def pay(request):
    return render(request, 'pc/pay.html', {'tg_user': request.tg_user})


@_require_tg_user
def account(request):
    verdicts = request.tg_user.verdicts.all().order_by('-created_at')
    return render(request, 'pc/account.html', {'tg_user': request.tg_user, 'verdicts': verdicts})


@_require_tg_user
def user_agree(request):
    return render(request, 'pc/user_agree.html', {'tg_user': request.tg_user})


@_require_tg_user
def privacy_policy(request):
    return render(request, 'pc/privacy_policy.html', {'tg_user': request.tg_user})


@_require_tg_user
def verdict(request):
    code = request.GET.get('code', '').upper()
    verdict_obj = get_object_or_404(Verdict, code=code)
    photos = verdict_obj.photos.all()
    first_photo = photos.first()
    return render(request, 'pc/verdict.html', {
        'tg_user': request.tg_user,
        'verdict': verdict_obj,
        'first_photo': first_photo,
        'photos': photos,
    })


@_require_tg_user
def home_page(request):
    return render(request, 'pc/home_page.html', {'tg_user': request.tg_user})


def _client_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0]
    return request.META.get("REMOTE_ADDR")


ALLOWED_TOKEN_CHARS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'


def telegram_login(request):
    """
    Страница генерации токена (desktop). Мобильных можно тоже редиректить,
    если хотите — добавьте @mobile_redirect или проверку внутри.
    """
    # пример: если хотите тоже редиректить
    # if is_mobile(request) and not request.session.get('tg_id'):
    #     return redirect(TELEGRAM_BOT_URL)

    ip = _client_ip(request)
    active = (LoginToken.objects
              .filter(ip_address=ip,
                      used_at__isnull=True,
                      created_at__gte=timezone.now() - timedelta(minutes=5))
              .count())
    if active >= 5:
        return HttpResponse("Too many active tokens", status=429)

    token = get_random_string(6, allowed_chars=ALLOWED_TOKEN_CHARS)
    expires_at = timezone.now() + timedelta(minutes=5)

    LoginToken.objects.create(
        token=token,
        ip_address=ip,
        expires_at=expires_at,
    )

    return render(request, 'pc/tg_login.html', {
        'token': token,
        'expires_at_ts': int(expires_at.timestamp()),
    })


def poll_token(request, token):
    try:
        t = LoginToken.objects.get(token=token)
    except LoginToken.DoesNotExist:
        return JsonResponse({'authenticated': False})

    if t.is_expired():
        return JsonResponse({'authenticated': False, 'expired': True})

    if t.used_at and t.user:
        request.session['tg_id'] = t.user.tgId
        return JsonResponse({'authenticated': True})

    return JsonResponse({'authenticated': False})

def _generate_unique_code():
    # 5 цифр, гарантированно уникально
    code = get_random_string(5, allowed_chars='0123456789')
    while Verdict.objects.filter(code=code).exists():
        code = get_random_string(5, allowed_chars='0123456789')
    return code


@csrf_exempt
@require_POST
@_require_tg_user
def create_verdict(request):
    user = request.tg_user

    # 2) Обязательные поля
    category = request.POST.get('category')        # например "sneakers"
    brand    = request.POST.get('brand')           # "nike", "jordan" и т.д.
    comment  = request.POST.get('comment', '').strip()

    if not category or not brand:
        return JsonResponse({'success': False, 'error': 'Не выбрана категория или бренд'}, status=400)

    # 3) Создаём Verdict
    verdict = Verdict.objects.create(
        user=user,
        status='inpending',             # например, сразу «в обработке»
        category=category,
        brand=brand,
        item_model='',                  # можно передавать, если нужно
        comment='',                     # внутренняя заметка, оставляем пустой
        comment_from_user=comment,
        code=_generate_unique_code()
    )

    # 4) Прикрепляем фото
    #   * все файлы <input name="photos"> и <input name="additional_photos">
    for f in request.FILES.getlist('photos'):
        VerdictPhoto.objects.create(verdict=verdict, image=f)
    for f in request.FILES.getlist('additional_photos'):
        VerdictPhoto.objects.create(verdict=verdict, image=f)

    # 5) Всё ок — вернём JSON с редиректом
    return JsonResponse({
        'success': True,
        'redirect_url': reverse('pc_home')  # например, страница с итогом
    })