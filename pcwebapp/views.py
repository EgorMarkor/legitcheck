import json
import re
import functools
from decimal import Decimal, InvalidOperation
from datetime import timedelta

from django.db import transaction
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.utils.crypto import get_random_string
from django.utils import timezone
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt

from .models import LoginToken, Brand, UploadedVerdictPhoto
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
                    return render(request, 'pc/mobile_redir.html')
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

def uslugi(request):
    """
    Главная страница (desktop / уже авторизованные мобильные).
    """
    return render(request, 'pc/list_uslug.html')


def public_offer(request):
    return render(request, 'pc/public_offer.html')


def privacy_policy_public(request):
    return render(request, 'pc/privacy_policy_public.html')

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
    if active >= 30:
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


# ---------- API endpoints for mobile/web app auth ----------

@csrf_exempt
@require_POST
def api_create_login_token(request):
    """
    Create a short-lived login token for Telegram bot auth.
    Returns JSON with token and expiration timestamp.
    """
    ip = _client_ip(request)
    active = (LoginToken.objects
              .filter(ip_address=ip,
                      used_at__isnull=True,
                      created_at__gte=timezone.now() - timedelta(minutes=5))
              .count())
    if active >= 30:
        return JsonResponse({"error": "Too many active tokens"}, status=429)

    token = get_random_string(6, allowed_chars=ALLOWED_TOKEN_CHARS)
    expires_at = timezone.now() + timedelta(minutes=5)

    LoginToken.objects.create(
        token=token,
        ip_address=ip,
        expires_at=expires_at,
    )

    return JsonResponse({
        "token": token,
        "expires_at_ts": int(expires_at.timestamp()),
    })


@csrf_exempt
def api_poll_login_token(request, token):
    """
    Poll login token status. Returns authenticated/expired flags.
    If authenticated, includes minimal user payload.
    """
    try:
        t = LoginToken.objects.select_related("user").get(token=token)
    except LoginToken.DoesNotExist:
        return JsonResponse({"authenticated": False})

    if t.is_expired():
        return JsonResponse({"authenticated": False, "expired": True})

    if t.used_at and t.user:
        user = t.user
        return JsonResponse({
            "authenticated": True,
            "user": {
                "tgId": user.tgId,
                "name": user.name,
                "username": user.username,
                "img": user.img,
                "balance": user.balance,
            }
        })

    return JsonResponse({"authenticated": False})

def _generate_unique_code():
    # 5 цифр, гарантированно уникально
    code = get_random_string(5, allowed_chars='0123456789')
    while Verdict.objects.filter(code=code).exists():
        code = get_random_string(5, allowed_chars='0123456789')
    return code


DEFAULT_VERDICT_SPEED = "24h"
DEFAULT_VERDICT_PRICE = Decimal("0.00")
TRUTHY_VALUES = {"1", "true", "yes", "on"}


def _extract_auth_token(request, request_data=None):
    token = (request.headers.get("X-Auth-Token") or "").strip()
    if token:
        return token

    auth_header = request.headers.get("Authorization", "")
    if auth_header.lower().startswith("bearer "):
        token = auth_header.split(" ", 1)[1].strip()
        if token:
            return token

    if request_data and hasattr(request_data, "get"):
        token = (request_data.get("auth_token") or "").strip()
        if token:
            return token

    token = (request.POST.get("auth_token") or "").strip()
    if token:
        return token
    return (request.GET.get("auth_token") or "").strip()


def _resolve_api_user(request, request_data=None):
    tg_id = request.session.get("tg_id")
    if tg_id:
        user = User.objects.filter(tgId=tg_id).first()
        if user:
            return user

    token = _extract_auth_token(request, request_data=request_data)
    if not token:
        return None

    login_token = LoginToken.objects.select_related("user").filter(token=token).first()
    if not login_token or login_token.is_expired() or not login_token.used_at or not login_token.user:
        return None
    return login_token.user


def _request_payload(request):
    if "application/json" in (request.content_type or ""):
        try:
            payload = json.loads((request.body or b"").decode("utf-8") or "{}")
        except (json.JSONDecodeError, UnicodeDecodeError):
            return None
        if not isinstance(payload, dict):
            return None
        return payload
    return request.POST


def _collect_photo_files(request):
    files = []
    files.extend(request.FILES.getlist("photo"))
    files.extend(request.FILES.getlist("photos"))
    files.extend(request.FILES.getlist("additional_photos"))
    return files


def _parse_photo_ids(data):
    values = []
    if hasattr(data, "getlist"):
        values.extend(data.getlist("photo_ids"))

    raw_photo_ids = data.get("photo_ids")
    if isinstance(raw_photo_ids, list):
        values.extend(raw_photo_ids)
    elif raw_photo_ids not in (None, ""):
        values.append(raw_photo_ids)

    photo_ids = []
    seen = set()

    def add_id(value):
        try:
            photo_id = int(value)
        except (TypeError, ValueError):
            return
        if photo_id not in seen:
            seen.add(photo_id)
            photo_ids.append(photo_id)

    for raw_value in values:
        if isinstance(raw_value, list):
            for nested_value in raw_value:
                add_id(nested_value)
            continue

        if isinstance(raw_value, str):
            raw_value = raw_value.strip()
            if not raw_value:
                continue
            if raw_value.startswith("["):
                try:
                    parsed_json = json.loads(raw_value)
                except json.JSONDecodeError:
                    parsed_json = None
                if isinstance(parsed_json, list):
                    for nested_value in parsed_json:
                        add_id(nested_value)
                    continue
            if "," in raw_value:
                for chunk in raw_value.split(","):
                    add_id(chunk.strip())
                continue
        add_id(raw_value)

    return photo_ids


def _get_uploaded_photos_for_user(user, photo_ids):
    if not photo_ids:
        return [], []

    uploaded_photos = UploadedVerdictPhoto.objects.filter(
        user=user,
        id__in=photo_ids,
        verdict__isnull=True,
    )
    uploaded_map = {photo.id: photo for photo in uploaded_photos}
    missing_ids = [photo_id for photo_id in photo_ids if photo_id not in uploaded_map]
    ordered_photos = [uploaded_map[photo_id] for photo_id in photo_ids if photo_id in uploaded_map]
    return ordered_photos, missing_ids


def _build_verdict_payload(data):
    category = (data.get("category") or "").strip()
    brand = (data.get("brand") or "").strip()
    comment = (data.get("comment") or "").strip()
    item_model = (data.get("item_model") or "").strip()

    if not category or not brand:
        return None, JsonResponse(
            {"success": False, "error": "Не выбрана категория или бренд"},
            status=400,
        )

    allowed_categories = {item[0] for item in Verdict.ITEM_CHOICES}
    if category not in allowed_categories:
        return None, JsonResponse(
            {"success": False, "error": "Некорректная категория"},
            status=400,
        )

    speed = (data.get("speed") or DEFAULT_VERDICT_SPEED).strip() or DEFAULT_VERDICT_SPEED
    with_reason = str(data.get("with_reason", "")).strip().lower() in TRUTHY_VALUES

    raw_price = data.get("price")
    if raw_price in (None, ""):
        price = DEFAULT_VERDICT_PRICE
    else:
        try:
            price = Decimal(str(raw_price))
        except (InvalidOperation, TypeError, ValueError):
            return None, JsonResponse(
                {"success": False, "error": "Некорректная цена"},
                status=400,
            )

    return {
        "category": category,
        "brand": brand,
        "item_model": item_model,
        "comment_from_user": comment,
        "speed": speed,
        "price": price,
        "with_reason": with_reason,
    }, None


def _create_verdict_with_assets(user, verdict_payload, direct_files, uploaded_photos):
    with transaction.atomic():
        verdict = Verdict.objects.create(
            user=user,
            status="inpending",
            category=verdict_payload["category"],
            brand=verdict_payload["brand"],
            item_model=verdict_payload["item_model"],
            comment="",
            comment_from_user=verdict_payload["comment_from_user"],
            code=_generate_unique_code(),
            speed=verdict_payload["speed"],
            price=verdict_payload["price"],
            with_reason=verdict_payload["with_reason"],
        )

        for file_obj in direct_files:
            VerdictPhoto.objects.create(verdict=verdict, image=file_obj)

        for uploaded_photo in uploaded_photos:
            VerdictPhoto.objects.create(verdict=verdict, image=uploaded_photo.image.name)
            uploaded_photo.mark_used(verdict)

    return verdict


@csrf_exempt
@require_POST
@_require_tg_user
def create_verdict(request):
    user = request.tg_user

    verdict_payload, error_response = _build_verdict_payload(request.POST)
    if error_response:
        return error_response

    direct_files = _collect_photo_files(request)
    photo_ids = _parse_photo_ids(request.POST)
    uploaded_photos, missing_ids = _get_uploaded_photos_for_user(user, photo_ids)
    if missing_ids:
        return JsonResponse(
            {"success": False, "error": "Некоторые фото не найдены", "missing_photo_ids": missing_ids},
            status=400,
        )

    _create_verdict_with_assets(
        user=user,
        verdict_payload=verdict_payload,
        direct_files=direct_files,
        uploaded_photos=uploaded_photos,
    )

    # 5) Всё ок — вернём JSON с редиректом
    return JsonResponse({
        'success': True,
        'redirect_url': reverse('pc_home')  # например, страница с итогом
    })


@csrf_exempt
@require_POST
def api_upload_verdict_photos(request):
    user = _resolve_api_user(request)
    if not user:
        return JsonResponse({"success": False, "error": "Не авторизован"}, status=401)

    files = _collect_photo_files(request)
    if not files:
        return JsonResponse(
            {"success": False, "error": "Файлы не переданы"},
            status=400,
        )

    uploaded = []
    for file_obj in files:
        uploaded_photo = UploadedVerdictPhoto.objects.create(
            user=user,
            image=file_obj,
        )
        uploaded.append(
            {
                "id": uploaded_photo.id,
                "image_url": uploaded_photo.image.url,
                "uploaded_at": uploaded_photo.created_at.isoformat(),
            }
        )

    return JsonResponse(
        {
            "success": True,
            "photos": uploaded,
            "photo_ids": [photo["id"] for photo in uploaded],
        },
        status=201,
    )


@csrf_exempt
@require_POST
def api_create_verdict(request):
    request_data = _request_payload(request)
    if request_data is None:
        return JsonResponse({"success": False, "error": "Некорректный JSON"}, status=400)

    user = _resolve_api_user(request, request_data=request_data)
    if not user:
        return JsonResponse({"success": False, "error": "Не авторизован"}, status=401)

    verdict_payload, error_response = _build_verdict_payload(request_data)
    if error_response:
        return error_response

    photo_ids = _parse_photo_ids(request_data)
    uploaded_photos, missing_ids = _get_uploaded_photos_for_user(user, photo_ids)
    if missing_ids:
        return JsonResponse(
            {"success": False, "error": "Некоторые фото не найдены", "missing_photo_ids": missing_ids},
            status=400,
        )

    direct_files = _collect_photo_files(request)
    if not direct_files and not uploaded_photos:
        return JsonResponse(
            {"success": False, "error": "Нужно загрузить хотя бы одно фото"},
            status=400,
        )

    verdict = _create_verdict_with_assets(
        user=user,
        verdict_payload=verdict_payload,
        direct_files=direct_files,
        uploaded_photos=uploaded_photos,
    )

    return JsonResponse(
        {
            "success": True,
            "verdict": {
                "id": verdict.id,
                "code": verdict.code,
                "category": verdict.category,
                "brand": verdict.brand,
            },
            "verdict_url": f"{reverse('pc_verdicts')}?code={verdict.code}",
        },
        status=201,
    )
