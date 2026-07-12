from django.shortcuts import render, redirect, get_object_or_404
from telebot.util import parse_web_app_data
from .models import (
    EmailOTPToken,
    HomePagePopularItem,
    Payment,
    PromoCode,
    PromoCodeRedemption,
    UploadedVerdictPhoto,
    User,
    Verdict,
    VerdictPhoto,
    TelegramVerdictDelivery,
)
from django.core.files.storage import default_storage
from django.core.exceptions import ImproperlyConfigured
from django.db.models import Prefetch, Q
from django.views.decorators.http import require_POST, require_http_methods
from django.views.decorators.csrf import csrf_protect
from django.urls import reverse
from django.utils.crypto import constant_time_compare, get_random_string
from django.views.decorators.csrf import csrf_exempt
from datetime import timedelta
from django.utils import timezone
from django.http import JsonResponse, HttpResponseBadRequest, HttpResponse
import uuid
from yookassa import Configuration, Payment as YooPayment
from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from yookassa import Payment as YooPayment
from yookassa.domain.notification import WebhookNotification
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import os
import traceback
import threading
from pcwebapp.models import LoginToken
from pcwebapp.models import UploadedVerdictPhoto as PcUploadedVerdictPhoto
import json
import logging
from urllib.parse import urlparse
from . import telegram as tg_service


Configuration.account_id = settings.YOOKASSA_ACCOUNT_ID
Configuration.secret_key = settings.YOOKASSA_SECRET_KEY

TELEGRAM_BOT_TOKEN = getattr(settings, "TELEGRAM_BOT_TOKEN", "")
TELEGRAM_VERDICT_CHAT_ID = getattr(settings, "TELEGRAM_VERDICT_CHAT_ID", None)
TELEGRAM_MEDIA_GROUP_LIMIT = 10
DEFAULT_PUBLIC_BASE_URL = "https://legitcheck.one"

logger = logging.getLogger(__name__)


def _configure_yookassa():
    account_id = str(getattr(settings, "YOOKASSA_ACCOUNT_ID", "")).strip()
    secret_key = str(getattr(settings, "YOOKASSA_SECRET_KEY", "")).strip()
    if not account_id or not secret_key:
        logger.error("YooKassa is disabled: YOOKASSA_ACCOUNT_ID/YOOKASSA_SECRET_KEY are missing")
        return False
    Configuration.account_id = account_id
    Configuration.secret_key = secret_key
    return True


def _yookassa_error_response(exc):
    logger.exception("YooKassa API request failed")
    details = str(exc) or type(exc).__name__
    return JsonResponse({"error": "Не удалось создать платёж", "details": details}, status=502)


def _create_yookassa_payment(user, amount):
    if not _configure_yookassa():
        raise ImproperlyConfigured("YooKassa credentials are not configured")
    receipt = {
        "customer": {"email": user.email or "no-reply@legitcheck.one"},
        "items": [{
            "description": "Пополнение баланса LegitCheck",
            "quantity": "1.00",
            "amount": {"value": str(amount), "currency": "RUB"},
            "vat_code": 1,
            "payment_subject": "service",
            "payment_mode": "full_payment",
        }],
    }
    tax_system_code = getattr(settings, "YOOKASSA_TAX_SYSTEM_CODE", "")
    if tax_system_code:
        receipt["tax_system_code"] = int(tax_system_code)
    return YooPayment.create(
        {
            "amount": {"value": str(amount), "currency": "RUB"},
            "confirmation": {
                "type": "redirect",
                "return_url": settings.YOOKASSA_RETURN_URL,
            },
            "capture": True,
            "description": "Пополнение баланса LegitCheck",
            "receipt": receipt,
            "metadata": {"tg_id": str(user.tgId)},
        },
        str(uuid.uuid4()),
    )

# URL аватарки по умолчанию на случай отсутствия фото у пользователя
DEFAULT_AVATAR_URL = "/static/avatar-placeholder.png"



LUXURY_BRANDS = {
    "Aesop",
    "Alexander McQueen",
    "Alexander Wang",
    "Audemars Piguet",
    "Balenciaga",
    "Cartier",
    "Celine",
    "Chrome Hearts",
    "Chloé",
    "Dior",
    "Fendi",
    "Goyard",
    "Gucci",
    "Hermes",
    "Jil Sander",
    "Jimmy Choo",
    "Loro Piana",
    "Louis Vuitton",
    "Miu Miu",
    "Moncler",
    "Palm Angels",
    "Prada",
    "PATEK PHILIPPE",
    "Rick Owens",
    "ROLEX",
    "Vetements",
}

TARIFF_PRICES = {
    "basic": {
        "standard": Decimal("149.00"),  # 2 часа
        "fast": Decimal("299.00"),      # 1 час
        "express": Decimal("499.00"),   # 15-30 минут
    },
    "luxury": {
        "standard": Decimal("299.00"),  # 3 часа
        "fast": Decimal("599.00"),      # 1 час
        "express": Decimal("999.00"),   # 15-30 минут
    },
}

REASON_PRICE = Decimal("150.00")
DEFAULT_VERDICT_SPEED = "standard"
DEFAULT_VERDICT_PRICE = Decimal("0.00")
FREE_CHECK_SPEED = "12h-free"
FREE_CHECK_COOLDOWN = timedelta(days=7)
TRUTHY_VALUES = {"1", "true", "yes", "on"}


def _tariff_group_for_brand(brand):
    return "luxury" if (brand or "").strip() in LUXURY_BRANDS else "basic"


def _tariff_price_for_brand(speed, brand):
    return TARIFF_PRICES.get(_tariff_group_for_brand(brand), {}).get(speed)


def init(request):
    # Точка входа: показываем кнопку Telegram WebApp
    return render(request, 'init.html')


def _session_user(request):
    tg_id = request.session.get("tg_id")
    if not tg_id:
        return None

    user = User.objects.filter(tgId=tg_id).first()
    if user:
        return user

    request.session.pop("tg_id", None)
    return None


def _homepage_popular_models():
    items_by_position = {
        item.position: item
        for item in HomePagePopularItem.objects.order_by("position")[:5]
    }
    items = []
    for fallback_item in HomePagePopularItem.default_items():
        items.append(items_by_position.get(fallback_item.position, fallback_item))
    return items


def _verdict_photos_prefetch():
    return Prefetch(
        "photos",
        queryset=VerdictPhoto.objects.order_by("id"),
        to_attr="prefetched_photos",
    )


def _verdicts_with_photos(queryset):
    return queryset.prefetch_related(_verdict_photos_prefetch())


def _verdict_photos(verdict):
    if hasattr(verdict, "prefetched_photos"):
        return list(verdict.prefetched_photos)
    return list(verdict.photos.order_by("id"))


def index(request):
    popular_models = _homepage_popular_models()
    raw_init_data = (
        request.GET.get("init_data")
        or request.GET.get("tgWebAppData")
    )

    if not raw_init_data:
        user = _session_user(request)
        if user:
            return render(request, "index.html", {
                "tg_user": user,
                "popular_models": popular_models,
            })
        return redirect("init")

    try:
        webapp_data = parse_web_app_data(TELEGRAM_BOT_TOKEN, raw_init_data)
    except Exception:
        logger.exception("parse_web_app_data raised, token_set=%s", bool(TELEGRAM_BOT_TOKEN))
        return redirect("init")

    if not webapp_data:
        logger.warning("parse_web_app_data returned falsy, token_set=%s", bool(TELEGRAM_BOT_TOKEN))
        return redirect("init")

    tg_user_data = webapp_data.get("user")
    if not tg_user_data:
        return redirect("init")

    if isinstance(tg_user_data, str):
        try:
            tg_user_data = json.loads(tg_user_data)
        except (json.JSONDecodeError, ValueError):
            return redirect("init")

    tg_id = tg_user_data.get("id")
    if not tg_id:
        return redirect("init")

    user, created = User.objects.get_or_create(
        tgId=tg_id,
        defaults={
            "name": tg_user_data.get("first_name", ""),
            "username": tg_user_data.get("username"),
            "img": DEFAULT_AVATAR_URL,
            "balance": "0",
        }
    )
    request.session["tg_id"] = tg_id
    request.session.set_expiry(365 * 24 * 60 * 60)

    return render(request, "index.html", {
        "tg_user": user,
        "popular_models": popular_models,
    })


def require_user(view_func):
    def wrapped(request, *args, **kwargs):
        user = _session_user(request)
        if not user:
            return redirect("init")

        request.tg_user = user
        return view_func(request, *args, **kwargs)

    return wrapped


def _refresh_free_check_state(user, save=True):
    now = timezone.now()
    next_timestamp = user.next_free_check_timestamp
    is_available = not next_timestamp or next_timestamp <= now
    update_fields = []

    if user.is_free_check_available != is_available:
        user.is_free_check_available = is_available
        update_fields.append("is_free_check_available")

    if is_available and next_timestamp is not None:
        user.next_free_check_timestamp = None
        next_timestamp = None
        update_fields.append("next_free_check_timestamp")

    if save and update_fields:
        user.save(update_fields=update_fields)

    return {
        "is_available": is_available,
        "next_timestamp": next_timestamp,
    }


def _free_check_json_state(user):
    state = _refresh_free_check_state(user)
    next_timestamp = state["next_timestamp"]
    return {
        "is_free_check_available": state["is_available"],
        "next_free_check_timestamp": next_timestamp.isoformat() if next_timestamp else None,
    }


def _storage_path_from_media_value(value):
    if not value:
        return None

    path = str(value).strip()
    if not path:
        return None

    parsed = urlparse(path)
    if parsed.scheme or parsed.netloc:
        path = parsed.path

    media_url = getattr(settings, "MEDIA_URL", "") or ""
    if media_url and path.startswith(media_url):
        path = path[len(media_url):]
    elif path.startswith("/"):
        return None

    path = path.lstrip("/")
    if not path or path.startswith("static/"):
        return None

    return path


def _collect_account_media_paths(user):
    media_paths = set()

    for value in VerdictPhoto.objects.filter(verdict__user=user).values_list("image", flat=True):
        path = _storage_path_from_media_value(value)
        if path:
            media_paths.add(path)

    for value in UploadedVerdictPhoto.objects.filter(user=user).values_list("image", flat=True):
        path = _storage_path_from_media_value(value)
        if path:
            media_paths.add(path)

    for value in PcUploadedVerdictPhoto.objects.filter(user=user).values_list("image", flat=True):
        path = _storage_path_from_media_value(value)
        if path:
            media_paths.add(path)

    avatar_path = _storage_path_from_media_value(user.img)
    if avatar_path:
        media_paths.add(avatar_path)

    return sorted(media_paths)


def _delete_storage_paths(paths):
    for path in paths:
        try:
            if default_storage.exists(path):
                default_storage.delete(path)
        except Exception:
            logger.warning("Failed to delete account media file: %s", path, exc_info=True)



def about(request):
    return render(request, 'confident.html')

def _generate_unique_code():
    # 5 цифр, гарантированно уникально
    code = get_random_string(5, allowed_chars='0123456789')
    while Verdict.objects.filter(code=code).exists():
        code = get_random_string(5, allowed_chars='0123456789')
    return code

from django.db import close_old_connections, transaction
from django.core.mail import send_mail
import random
import zlib




def _build_public_media_url(photo):
    url = photo.image.url
    if url.startswith("http://") or url.startswith("https://"):
        return url
    base_url = getattr(settings, "PUBLIC_BASE_URL", DEFAULT_PUBLIC_BASE_URL).rstrip("/")
    return f"{base_url}{url}"


def _build_admin_verdict_url(verdict):
    base_url = getattr(settings, "PUBLIC_BASE_URL", DEFAULT_PUBLIC_BASE_URL).rstrip("/")
    return f"{base_url}/admin/webapp/verdict/{verdict.id}/change/"


def _build_verdict_message(verdict, include_prompt=False):
    comment_from_user = verdict.comment_from_user or "—"
    item_model = verdict.item_model or "—"
    admin_url = _build_admin_verdict_url(verdict)
    parts = [
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
        parts.append("Выберите вердикт для позиции.")
    return "\n".join(parts)


def _chunked(items, size):
    for idx in range(0, len(items), size):
        yield items[idx:idx + size]


def _send_verdict_to_telegram(verdict):
    policy = _telegram_delivery_policy(verdict)
    if not policy:
        return []
    chat_id, _, _ = policy
    message_ids = []
    text = _build_verdict_message(verdict, include_prompt=True)
    reply_markup = {
        "inline_keyboard": [
            [
                {"text": "Вердикт", "callback_data": f"verdict:{verdict.id}:legit"},
                {"text": "Не вердикт", "callback_data": f"verdict:{verdict.id}:fake"},
            ],
            [
                {"text": "Загрузите доп. фото", "callback_data": f"verdict:{verdict.id}:todo"},
            ]
        ]
    }
    photos = _verdict_photos(verdict)
    if photos:
        first_caption = text
        for group in _chunked(photos, TELEGRAM_MEDIA_GROUP_LIMIT):
            media = []
            files = {}
            for index, photo in enumerate(group):
                file_key = f"photo_{index}"
                photo_path = getattr(photo.image, "path", "")
                use_upload = photo_path and os.path.exists(photo_path)
                item = {
                    "type": "photo",
                    "media": f"attach://{file_key}" if use_upload else _build_public_media_url(photo),
                }
                if first_caption and index == 0:
                    item["caption"] = first_caption
                    first_caption = None
                media.append(item)
                if use_upload:
                    files[file_key] = open(photo_path, "rb")
            if files:
                result = tg_service.send_media_group(TELEGRAM_BOT_TOKEN, chat_id, media, files=files)
                for file in files.values():
                    file.close()
            else:
                result = tg_service.send_media_group(TELEGRAM_BOT_TOKEN, chat_id, media)
            if not result:
                raise RuntimeError("Telegram rejected the verdict media group")
            message_ids.extend(item["message_id"] for item in result.get("result", []))
        result = tg_service.send_message(
            TELEGRAM_BOT_TOKEN,
            chat_id,
            text,
            reply_markup=reply_markup,
        )
    else:
        result = tg_service.send_message(
            TELEGRAM_BOT_TOKEN,
            chat_id,
            text,
            reply_markup=reply_markup,
        )
    if not result:
        raise RuntimeError("Telegram rejected the verdict message")
    message_ids.append(result["result"]["message_id"])
    return message_ids


def _telegram_delivery_policy(verdict):
    """Return (chat_id, lifetime, repeat interval) for a check SLA."""
    speed = (verdict.speed or "").lower()
    if speed == FREE_CHECK_SPEED or speed.startswith("12h"):
        bucket, lifetime, interval = "12H", timedelta(hours=12), timedelta(hours=1)
    elif speed == "express" or speed.startswith("15min") or speed.startswith("30min"):
        bucket, lifetime, interval = "15_30M", timedelta(minutes=30), timedelta(minutes=15)
    elif speed == "fast" or speed.startswith("1h"):
        bucket, lifetime, interval = "1H", timedelta(hours=1), timedelta(minutes=15)
    else:
        bucket, lifetime, interval = "2H", timedelta(hours=2), timedelta(minutes=30)
    chat_id = getattr(settings, f"TELEGRAM_VERDICT_CHAT_{bucket}_ID", "") or TELEGRAM_VERDICT_CHAT_ID
    return (str(chat_id), lifetime, interval) if chat_id else None


def _delete_telegram_messages(chat_id, message_ids):
    for message_id in message_ids or []:
        tg_service.delete_message(TELEGRAM_BOT_TOKEN, chat_id, message_id)


def _deliver_verdict_to_telegram(verdict, delivery=None):
    policy = _telegram_delivery_policy(verdict)
    if not policy:
        return
    chat_id, lifetime, interval = policy
    now = timezone.now()
    delivery = delivery or TelegramVerdictDelivery.objects.filter(verdict=verdict).first()
    if delivery:
        _delete_telegram_messages(delivery.chat_id, delivery.message_ids)
    message_ids = _send_verdict_to_telegram(verdict)
    TelegramVerdictDelivery.objects.update_or_create(
        verdict=verdict,
        defaults={
            "chat_id": chat_id,
            "message_ids": message_ids,
            "interval_minutes": int(interval.total_seconds() // 60),
            "expires_at": delivery.expires_at if delivery else now + lifetime,
            "next_send_at": now + interval,
            "active": verdict.status not in {"legit", "fake"},
            "last_error": "",
        },
    )


def _send_verdict_to_telegram_by_id(verdict_id):
    close_old_connections()
    try:
        verdict = (
            Verdict.objects
            .select_related("user")
            .prefetch_related(_verdict_photos_prefetch())
            .get(pk=verdict_id)
        )
        policy = _telegram_delivery_policy(verdict)
        if not policy:
            return
        chat_id, lifetime, interval = policy
        now = timezone.now()
        delivery, _ = TelegramVerdictDelivery.objects.get_or_create(
            verdict=verdict,
            defaults={
                "chat_id": chat_id,
                "interval_minutes": int(interval.total_seconds() // 60),
                "expires_at": now + lifetime,
                "next_send_at": now,
            },
        )
        _deliver_verdict_to_telegram(verdict, delivery=delivery)
    except Exception:
        logger.exception("Failed to send verdict %s to Telegram", verdict_id)
    finally:
        close_old_connections()


def _queue_verdict_telegram_send(verdict_id):
    if not TELEGRAM_BOT_TOKEN:
        return

    thread = threading.Thread(
        target=_send_verdict_to_telegram_by_id,
        args=(verdict_id,),
        name=f"telegram-verdict-{verdict_id}",
        daemon=True,
    )
    thread.start()


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


def _resolve_user_by_tg_id(request_data):
    raw_tg_id = request_data.get("tg_id")
    if raw_tg_id in (None, ""):
        raw_tg_id = request_data.get("tgId")

    if raw_tg_id in (None, ""):
        return None, JsonResponse(
            {"success": False, "error": "Не указан tg_id"},
            status=400,
        )

    try:
        tg_id = int(str(raw_tg_id).strip())
    except (TypeError, ValueError):
        return None, JsonResponse(
            {"success": False, "error": "Некорректный tg_id"},
            status=400,
        )

    user = User.objects.filter(tgId=tg_id).first()
    if not user:
        return None, JsonResponse(
            {"success": False, "error": "Пользователь не найден"},
            status=404,
        )

    return user, None


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


def _idempotency_key_from_data(data):
    key = (data.get("idempotency_key") or "").strip()
    if not key:
        return ""
    return key[:64]


def _find_idempotent_verdict(user, idempotency_key):
    if not idempotency_key:
        return None
    return Verdict.objects.filter(
        user=user,
        idempotency_key=idempotency_key,
    ).order_by("-id").first()


def _verdict_success_payload(verdict, duplicate=False):
    return {
        "success": True,
        "duplicate": duplicate,
        "verdict": {
            "id": verdict.id,
            "code": verdict.code,
            "category": verdict.category,
            "brand": verdict.brand,
        },
        "verdict_url": f"{reverse('verdicts')}?code={verdict.code}",
    }


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
        "idempotency_key": _idempotency_key_from_data(data),
    }, None


def _create_verdict_with_assets(user, verdict_payload, direct_files, uploaded_photos):
    with transaction.atomic():
        user = User.objects.select_for_update().get(pk=user.pk)
        existing_verdict = _find_idempotent_verdict(user, verdict_payload.get("idempotency_key"))
        if existing_verdict:
            return existing_verdict, False

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
            idempotency_key=verdict_payload.get("idempotency_key") or None,
        )

        for file_obj in direct_files:
            VerdictPhoto.objects.create(verdict=verdict, image=file_obj)

        for uploaded_photo in uploaded_photos:
            VerdictPhoto.objects.create(verdict=verdict, image=uploaded_photo.image.name)
            uploaded_photo.mark_used(verdict)

        transaction.on_commit(lambda verdict_id=verdict.id: _queue_verdict_telegram_send(verdict_id))

    return verdict, True


def _serialize_verdict_for_mobile(verdict):
    photos = []
    for photo in _verdict_photos(verdict):
        photos.append(
            {
                "id": photo.id,
                "image_url": _build_public_media_url(photo),
                "uploaded_at": photo.uploaded_at.isoformat(),
            }
        )

    return {
        "id": verdict.id,
        "code": verdict.code,
        "status": verdict.status,
        "status_display": verdict.get_status_display(),
        "category": verdict.category,
        "category_display": verdict.get_category_display(),
        "brand": verdict.brand,
        "item_model": verdict.item_model,
        "comment": verdict.comment,
        "comment_from_user": verdict.comment_from_user,
        "created_at": verdict.created_at.isoformat(),
        "speed": verdict.speed,
        "price": str(verdict.price),
        "with_reason": verdict.with_reason,
        "user": {
            "tgId": verdict.user.tgId,
            "name": verdict.user.name,
            "username": verdict.user.username,
            "img": verdict.user.img,
        },
        "photos": photos,
        "first_photo_url": photos[0]["image_url"] if photos else None,
    }


@csrf_exempt
@require_POST
@require_user
def create_verdict(request):
    user = request.tg_user

    category = request.POST.get('category')
    brand = request.POST.get('brand')
    speed = request.POST.get('speed')
    with_reason = request.POST.get('with_reason') == '1'
    comment = request.POST.get('comment', '').strip()
    idempotency_key = _idempotency_key_from_data(request.POST)

    existing_verdict = _find_idempotent_verdict(user, idempotency_key)
    if existing_verdict:
        return JsonResponse({
            "success": True,
            "duplicate": True,
            "redirect_url": reverse("lk"),
            "verdict": {
                "id": existing_verdict.id,
                "code": existing_verdict.code,
                "category": existing_verdict.category,
                "brand": existing_verdict.brand,
            },
        })

    if not category or not brand or not speed:
        return JsonResponse({
            "success": False,
            "error": "Не выбраны все параметры"
        }, status=400)

    total_price = _tariff_price_for_brand(speed, brand)
    if total_price is None:
        return JsonResponse({
            "success": False,
            "error": "Неверный тариф"
        }, status=400)

    # 💰 считаем сумму НА БЭКЕ
    if with_reason:
        total_price += REASON_PRICE

    user_balance = Decimal(user.balance)

    if user_balance < total_price:
        return JsonResponse({
            "success": False,
            "error": "Недостаточно средств"
        }, status=400)

    # 🔒 атомарно: списание + создание вердикта
    with transaction.atomic():
        user = User.objects.select_for_update().get(pk=user.pk)
        existing_verdict = _find_idempotent_verdict(user, idempotency_key)
        if existing_verdict:
            return JsonResponse({
                "success": True,
                "duplicate": True,
                "redirect_url": reverse("lk"),
                "verdict": {
                    "id": existing_verdict.id,
                    "code": existing_verdict.code,
                    "category": existing_verdict.category,
                    "brand": existing_verdict.brand,
                },
            })

        user_balance = Decimal(user.balance)
        if user_balance < total_price:
            return JsonResponse({
                "success": False,
                "error": "Недостаточно средств"
            }, status=400)

        user.balance = str(user_balance - total_price)
        user.save(update_fields=["balance"])

        verdict = Verdict.objects.create(
            user=user,
            status='inpending',
            category=category,
            brand=brand,
            comment_from_user=comment,
            code=_generate_unique_code(),
            # 👉 полезно сохранить:
            speed=speed,
            price=total_price,
            with_reason=with_reason,
            idempotency_key=idempotency_key or None,
        )

        for f in request.FILES.getlist('photos'):
            VerdictPhoto.objects.create(verdict=verdict, image=f)

        transaction.on_commit(lambda verdict_id=verdict.id: _queue_verdict_telegram_send(verdict_id))

    return JsonResponse({
        "success": True,
        "duplicate": False,
        "redirect_url": reverse("lk")
    })


@csrf_exempt
@require_POST
@require_user
def create_free_verdict(request):
    request_data = request.POST.copy()
    request_data["speed"] = FREE_CHECK_SPEED
    request_data["price"] = "0"
    request_data["with_reason"] = "0"

    verdict_payload, error_response = _build_verdict_payload(request_data)
    if error_response:
        return error_response

    verdict_payload.update({
        "speed": FREE_CHECK_SPEED,
        "price": Decimal("0.00"),
        "with_reason": False,
    })
    direct_files = _collect_photo_files(request)

    with transaction.atomic():
        user = User.objects.select_for_update().get(pk=request.tg_user.pk)
        existing_verdict = _find_idempotent_verdict(user, verdict_payload.get("idempotency_key"))
        if existing_verdict:
            return JsonResponse(
                {
                    **_verdict_success_payload(existing_verdict, duplicate=True),
                    "redirect_url": reverse("lk"),
                    "is_free_check_available": user.is_free_check_available,
                    "next_free_check_timestamp": (
                        user.next_free_check_timestamp.isoformat()
                        if user.next_free_check_timestamp
                        else None
                    ),
                    "balance": user.balance,
                },
                status=200,
            )

        state = _refresh_free_check_state(user)

        if not state["is_available"]:
            next_timestamp = state["next_timestamp"]
            seconds_remaining = 0
            if next_timestamp:
                seconds_remaining = max(0, int((next_timestamp - timezone.now()).total_seconds()))

            return JsonResponse(
                {
                    "success": False,
                    "error": "Бесплатная проверка будет доступна позже",
                    "is_free_check_available": False,
                    "next_free_check_timestamp": next_timestamp.isoformat() if next_timestamp else None,
                    "seconds_remaining": seconds_remaining,
                },
                status=409,
            )

        next_timestamp = timezone.now() + FREE_CHECK_COOLDOWN
        user.is_free_check_available = False
        user.next_free_check_timestamp = next_timestamp
        user.save(update_fields=["is_free_check_available", "next_free_check_timestamp"])

        verdict, created = _create_verdict_with_assets(
            user=user,
            verdict_payload=verdict_payload,
            direct_files=direct_files,
            uploaded_photos=[],
        )

    return JsonResponse(
        {
            "success": True,
            "duplicate": not created,
            "redirect_url": reverse("lk"),
            "verdict": {
                "id": verdict.id,
                "code": verdict.code,
                "category": verdict.category,
                "brand": verdict.brand,
            },
            "is_free_check_available": False,
            "next_free_check_timestamp": next_timestamp.isoformat(),
            "balance": user.balance,
        },
        status=201,
    )

@require_user
def check_verdict(request):
    code = request.GET.get('code', '').strip().upper()
    verdict = (
        Verdict.objects
        .select_related("user")
        .prefetch_related(_verdict_photos_prefetch())
        .filter(code=code, user=request.tg_user)
        .first()
    )
    if not verdict:
        return redirect(f"{reverse('verdicts')}?error=not_found&code={code}")
    photos = _verdict_photos(verdict)
    first_photo = photos[0] if photos else None

    return render(request, 'verdict.html', {
        'tg_user':    request.tg_user,
        'verdict':    verdict,
        'first_photo': first_photo,
        'photos':     photos,
        'code': code,
        'can_upload_extra_photos': (
            verdict.user_id == request.tg_user.pk and verdict.status == "todo"
        ),
    })


@require_user
def cab(request):
    verdicts = _verdicts_with_photos(
        request.tg_user.verdicts.only(
            "id",
            "user_id",
            "status",
            "code",
            "created_at",
        ).order_by("-created_at")
    )
    free_check_state = _free_check_json_state(request.tg_user)
    return render(request, 'cab.html', {
        'tg_user':  request.tg_user,
        'verdicts': verdicts,
        'free_check_available': free_check_state["is_free_check_available"],
        'free_check_next_timestamp': free_check_state["next_free_check_timestamp"],
    })


@require_http_methods(["GET", "HEAD", "POST"])
@require_user
def account_delete(request):
    if request.method in ("GET", "HEAD"):
        return render(request, "account_delete.html", {
            "tg_user": request.tg_user,
        })

    if request.POST.get("confirm_delete") != "1":
        return render(request, "account_delete.html", {
            "tg_user": request.tg_user,
            "error": "Подтвердите удаление аккаунта.",
        }, status=400)

    with transaction.atomic():
        user = User.objects.select_for_update().get(pk=request.tg_user.pk)
        media_paths = _collect_account_media_paths(user)
        user_email = user.email
        tg_id = user.tgId

        LoginToken.objects.filter(Q(user=user) | Q(telegram_id=tg_id)).delete()
        if user_email:
            EmailOTPToken.objects.filter(email__iexact=user_email).delete()

        user.delete()
        transaction.on_commit(lambda paths=tuple(media_paths): _delete_storage_paths(paths))

    request.session.flush()
    return render(request, "account_deleted.html")
    
    
@require_user
def promo(request):
    promo_code_value = ""
    promo_status = "idle"
    promo_message = ""
    credited_amount = None

    if request.method == "POST":
        promo_code_value = (request.POST.get("promo_code") or "").strip().upper()
        promo = PromoCode.objects.filter(
            code=promo_code_value,
            is_active=True,
        ).first()

        if not promo:
            promo_status = "invalid"
            promo_message = "Промокод не найден"
        elif PromoCodeRedemption.objects.filter(
            promo_code=promo,
            user=request.tg_user,
        ).exists():
            promo_status = "invalid"
            promo_message = "Этот промокод уже был активирован"
        else:
            reward = promo.reward_amount
            with transaction.atomic():
                user = User.objects.select_for_update().get(pk=request.tg_user.pk)
                current_balance = Decimal(user.balance)
                new_balance = (current_balance + reward).quantize(Decimal("0.01"))
                user.balance = str(new_balance)
                user.save(update_fields=["balance"])

                PromoCodeRedemption.objects.create(
                    promo_code=promo,
                    user=user,
                    amount=reward,
                )

            request.tg_user = user
            promo_status = "valid"
            promo_message = f"Начислено {reward} ₽"
            credited_amount = reward

    if request.method == "POST" and request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse({
            "status": promo_status,
            "message": promo_message,
            "promo_code_value": promo_code_value,
            "credited_amount": str(credited_amount) if credited_amount is not None else None,
        })

    return render(request, 'promo.html', {
        'tg_user':  request.tg_user,
        'promo_code_value': promo_code_value,
        'promo_status': promo_status,
        'promo_message': promo_message,
        'credited_amount': credited_amount,
    })
    
@require_user
def articles(request):
    return render(request, 'articles.html', {
        'tg_user':  request.tg_user,
    })

@require_user
def verdicts(request):
    return render(request, 'verdicts.html', {
        'tg_user': request.tg_user,
    })

@require_user
def check(request):
    free_check_state = _free_check_json_state(request.tg_user)
    return render(request, 'check.html', {
        'tg_user': request.tg_user,
        'balance': request.tg_user.balance,  # 👈 добавляем
        'free_check_available': free_check_state["is_free_check_available"],
        'free_check_next_timestamp': free_check_state["next_free_check_timestamp"],
    })

@require_user
def payment(request):
    return render(request, 'payment.html', {
        'tg_user': request.tg_user,
    })

@require_user
def confident(request):
    return render(request, 'confident.html', {
        'tg_user': request.tg_user,
    })

@require_user
def license(request):
    return render(request, 'license_sogl.html', {
        'tg_user': request.tg_user,
    })
    
    
@require_user
def auth_check(request):
    return render(request, 'auth_check.html', {
        'tg_user': request.tg_user,
    })
    
    
@require_user
def our_support(request):
    return render(request, 'our_support.html', {
        'tg_user': request.tg_user,
    })


@csrf_exempt
def telegram_verdict_webhook(request):
    if request.method != "POST":
        return HttpResponseBadRequest("Invalid method")

    try:
        payload = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return HttpResponseBadRequest("Invalid payload")

    callback_query = payload.get("callback_query")
    if not callback_query:
        return JsonResponse({"ok": True})

    data = callback_query.get("data", "")
    if not data.startswith("verdict:"):
        return JsonResponse({"ok": True})

    try:
        _, verdict_id, decision = data.split(":")
    except ValueError:
        return JsonResponse({"ok": True})

    if decision not in {"legit", "fake", "todo"}:
        return JsonResponse({"ok": True})

    try:
        verdict = Verdict.objects.get(pk=int(verdict_id))
    except (Verdict.DoesNotExist, ValueError):
        tg_service.answer_callback_query(
            TELEGRAM_BOT_TOKEN, callback_query.get("id"), "Вердикт не найден"
        )
        return JsonResponse({"ok": True})

    verdict.status = decision
    verdict.save(update_fields=["status"])

    delivery = TelegramVerdictDelivery.objects.filter(verdict=verdict, active=True).first()
    if delivery:
        _delete_telegram_messages(delivery.chat_id, delivery.message_ids)
        delivery.message_ids = []
        delivery.active = False
        delivery.save(update_fields=["message_ids", "active", "updated_at"])

    user_messages = {
        "legit": f"✅ Проверка {verdict.code} завершена: вынесен вердикт «Оригинал».",
        "fake": f"❌ Проверка {verdict.code} завершена: вынесен вердикт «Не оригинал».",
        "todo": (
            f"📷 Для проверки {verdict.code} нужны дополнительные фотографии. "
            f"Загрузите их на странице {getattr(settings, 'PUBLIC_BASE_URL', DEFAULT_PUBLIC_BASE_URL).rstrip('/')}/verdict/?code={verdict.code}"
        ),
    }
    tg_service.send_message(
        TELEGRAM_BOT_TOKEN,
        verdict.user.tgId,
        user_messages[decision],
    )

    tg_service.answer_callback_query(
        TELEGRAM_BOT_TOKEN, callback_query.get("id"), "Вердикт обновлен"
    )

    message = callback_query.get("message", {})
    chat = message.get("chat", {})
    if chat.get("id") and message.get("message_id"):
        tg_service.edit_message_reply_markup(
            TELEGRAM_BOT_TOKEN,
            chat.get("id"),
            message.get("message_id"),
            {"inline_keyboard": []},
        )

    return JsonResponse({"ok": True})
    

@require_user
def feedbacks(request):
    return render(request, 'feedback.html', {
        'tg_user': request.tg_user,
    })
    
    
@require_user
def start_check(request):
    return render(request, 'start_check.html', {
        'tg_user': request.tg_user,
    })
    
    
@csrf_exempt
@require_POST
@require_user
def create_payment(request):
    raw_amount = request.POST.get("amount", "").replace(",", ".")

    try:
        amount = Decimal(raw_amount).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except:
        return JsonResponse({"error": "Некорректная сумма"}, status=400)

    if amount < Decimal("10.00"):
        return JsonResponse({"error": "Минимум 10 ₽"}, status=400)

    try:
        payment = _create_yookassa_payment(request.tg_user, amount)
    except Exception as exc:
        return _yookassa_error_response(exc)

    Payment.objects.create(
        user=request.tg_user,
        amount=amount,
        status="PENDING",
        provider_payment_id=payment.id
    )

    return JsonResponse({
        "url": payment.confirmation.confirmation_url
    })


@csrf_exempt
def yookassa_webhook(request):
    import json

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return HttpResponse(status=400)

    if data.get("event") != "payment.succeeded":
        return HttpResponse(status=200)

    provider_payment_id = data.get("object", {}).get("id")
    if not provider_payment_id or not _configure_yookassa():
        return HttpResponse(status=503)

    # Never trust monetary fields from the unauthenticated notification body.
    try:
        provider_payment = YooPayment.find_one(provider_payment_id)
    except Exception:
        logger.exception("Failed to verify YooKassa payment %s", provider_payment_id)
        return HttpResponse(status=503)

    if provider_payment.status != "succeeded" or not provider_payment.paid:
        logger.warning("Ignoring unconfirmed YooKassa payment %s", provider_payment_id)
        return HttpResponse(status=200)

    try:
        with transaction.atomic():
            payment = Payment.objects.select_for_update().select_related("user").get(
                provider_payment_id=provider_payment_id
            )
            if payment.status == "COMPLETED":
                return HttpResponse(status=200)
            provider_amount = Decimal(provider_payment.amount.value)
            if provider_payment.amount.currency != "RUB" or provider_amount != payment.amount:
                logger.error("YooKassa amount mismatch for payment %s", provider_payment_id)
                return HttpResponse(status=400)
            if payment.user_id is None:
                logger.error("YooKassa payment %s has no local user", provider_payment_id)
                return HttpResponse(status=409)
            user = User.objects.select_for_update().get(pk=payment.user_id)
            user.balance = str(Decimal(user.balance) + payment.amount)
            user.save(update_fields=["balance"])
            payment.status = "COMPLETED"
            payment.save(update_fields=["status"])
    except Payment.DoesNotExist:
        return HttpResponse(status=200)
    except Exception:
        logger.exception("Failed to apply YooKassa payment %s", provider_payment_id)
        return HttpResponse(status=500)

    return HttpResponse(status=200)


@require_user
def payment_success(request):
    return render(request, "pay.html", {
        "tg_user": request.tg_user,
        "payment_success": True
    })


@csrf_exempt
@require_POST
@require_user
def upload_verdict_photo(request, verdict_id):
    verdict = get_object_or_404(Verdict, id=verdict_id, user=request.tg_user)

    if verdict.status != "todo":
        return JsonResponse(
            {"success": False, "error": "Дополнительные фото можно загрузить только по запросу эксперта"},
            status=409,
        )

    if 'photo' not in request.FILES:
        return JsonResponse({'error': 'Файл не передан'}, status=400)

    photo = VerdictPhoto.objects.create(
        verdict=verdict,
        image=request.FILES['photo']
    )
    verdict.status = "inpending"
    verdict.save(update_fields=["status"])
    TelegramVerdictDelivery.objects.filter(verdict=verdict).delete()
    transaction.on_commit(lambda verdict_id=verdict.id: _queue_verdict_telegram_send(verdict_id))

    return JsonResponse({
        'success': True,
        'image_url': photo.image.url
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

    existing_verdict = _find_idempotent_verdict(user, verdict_payload.get("idempotency_key"))
    if existing_verdict:
        return JsonResponse(_verdict_success_payload(existing_verdict, duplicate=True), status=200)

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

    verdict, created = _create_verdict_with_assets(
        user=user,
        verdict_payload=verdict_payload,
        direct_files=direct_files,
        uploaded_photos=uploaded_photos,
    )

    return JsonResponse(
        _verdict_success_payload(verdict, duplicate=not created),
        status=201 if created else 200,
    )


@csrf_exempt
@require_POST
def api_mobile_upload_verdict_photos(request):
    request_data = _request_payload(request)
    if request_data is None:
        return JsonResponse({"success": False, "error": "Некорректный JSON"}, status=400)

    user, error_response = _resolve_user_by_tg_id(request_data)
    if error_response:
        return error_response

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
def api_mobile_create_verdict(request):
    request_data = _request_payload(request)
    if request_data is None:
        return JsonResponse({"success": False, "error": "Некорректный JSON"}, status=400)

    user, error_response = _resolve_user_by_tg_id(request_data)
    if error_response:
        return error_response

    verdict_payload, error_response = _build_verdict_payload(request_data)
    if error_response:
        return error_response

    existing_verdict = _find_idempotent_verdict(user, verdict_payload.get("idempotency_key"))
    if existing_verdict:
        return JsonResponse(_verdict_success_payload(existing_verdict, duplicate=True), status=200)

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

    verdict, created = _create_verdict_with_assets(
        user=user,
        verdict_payload=verdict_payload,
        direct_files=direct_files,
        uploaded_photos=uploaded_photos,
    )

    return JsonResponse(
        _verdict_success_payload(verdict, duplicate=not created),
        status=201 if created else 200,
    )


@csrf_exempt
def api_mobile_get_verdict_by_code(request, code):
    normalized_code = (code or "").strip().upper()
    if not normalized_code:
        return JsonResponse({"success": False, "error": "Не указан код вердикта"}, status=400)

    verdict = (
        Verdict.objects.select_related("user")
        .prefetch_related(_verdict_photos_prefetch())
        .filter(code=normalized_code)
        .first()
    )
    if not verdict:
        return JsonResponse({"success": False, "error": "Вердикт не найден"}, status=404)

    return JsonResponse(
        {
            "success": True,
            "verdict": _serialize_verdict_for_mobile(verdict),
        }
    )


@csrf_exempt
@require_POST
def api_mobile_upload_verdict_photo(request, verdict_id):
    request_data = _request_payload(request)
    if request_data is None:
        return JsonResponse({"success": False, "error": "Некорректный JSON"}, status=400)

    user, error_response = _resolve_user_by_tg_id(request_data)
    if error_response:
        return error_response

    verdict = (
        Verdict.objects.select_related("user")
        .prefetch_related(_verdict_photos_prefetch())
        .filter(id=verdict_id, user=user)
        .first()
    )
    if not verdict:
        return JsonResponse({"success": False, "error": "Вердикт не найден"}, status=404)
    if verdict.status != "todo":
        return JsonResponse(
            {"success": False, "error": "Дополнительные фото можно загрузить только по запросу эксперта"},
            status=409,
        )

    files = _collect_photo_files(request)
    if not files:
        return JsonResponse({"success": False, "error": "Файлы не переданы"}, status=400)

    created_photos = []
    for file_obj in files:
        photo = VerdictPhoto.objects.create(verdict=verdict, image=file_obj)
        created_photos.append(
            {
                "id": photo.id,
                "image_url": _build_public_media_url(photo),
                "uploaded_at": photo.uploaded_at.isoformat(),
            }
        )

    verdict.status = "inpending"
    verdict.save(update_fields=["status"])
    TelegramVerdictDelivery.objects.filter(verdict=verdict).delete()
    transaction.on_commit(lambda verdict_id=verdict.id: _queue_verdict_telegram_send(verdict_id))

    verdict = (
        Verdict.objects.select_related("user")
        .prefetch_related(_verdict_photos_prefetch())
        .get(id=verdict.id)
    )

    return JsonResponse(
        {
            "success": True,
            "photos": created_photos,
            "verdict": _serialize_verdict_for_mobile(verdict),
        },
        status=201,
    )


# ---------- API endpoints for Telegram-bot auth (webapp) ----------

ALLOWED_LOGIN_TOKEN_CHARS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'


def _client_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0]
    return request.META.get("REMOTE_ADDR")


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

    token = get_random_string(6, allowed_chars=ALLOWED_LOGIN_TOKEN_CHARS)
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


@csrf_exempt
@require_POST
def api_web_login_with_token(request, token):
    """
    Finalize web login outside Telegram WebApp:
    if token already confirmed in bot, write tg_id into Django session.
    """
    token = (token or "").strip().upper()
    if not token:
        return JsonResponse({"success": False, "error": "Токен не указан"}, status=400)

    try:
        login_token = LoginToken.objects.select_related("user").get(token=token)
    except LoginToken.DoesNotExist:
        return JsonResponse({"success": False, "error": "Токен не найден"}, status=404)

    if login_token.is_expired():
        return JsonResponse({"success": False, "error": "Токен истек"}, status=400)

    if not login_token.used_at or not login_token.user:
        return JsonResponse({"success": False, "error": "Токен еще не подтвержден"}, status=409)

    user = login_token.user
    request.session["tg_id"] = user.tgId
    request.session.set_expiry(365 * 24 * 60 * 60)
    request.session.cycle_key()

    return JsonResponse(
        {
            "success": True,
            "redirect_url": reverse("home"),
            "user": {
                "tgId": user.tgId,
                "name": user.name,
                "username": user.username,
                "img": user.img,
                "balance": user.balance,
            },
        }
    )


def api_auth_restore(request, token):
    """Restore session from persistent auth_token stored in localStorage."""
    import uuid as _uuid
    try:
        parsed = _uuid.UUID(str(token))
    except (ValueError, AttributeError):
        return redirect('/?clear_token=1')

    user = User.objects.filter(auth_token=parsed).first()
    if not user:
        return redirect('/?clear_token=1')

    request.session['tg_id'] = user.tgId
    request.session.set_expiry(365 * 24 * 60 * 60)
    return redirect('home')


from rest_framework import viewsets
from rest_framework.permissions import AllowAny
from rest_framework.decorators import api_view, permission_classes
from .models import User, Verdict, VerdictPhoto, Payment
from .serializers import (
    UserSerializer,
    VerdictSerializer,
    VerdictPhotoSerializer,
    PaymentSerializer
)

@csrf_exempt
@api_view(["POST"])
@permission_classes([AllowAny])
def create_yookassa_payment_api(request):
    raw_amount = str(request.data.get("amount", "")).replace(",", ".")
    user_id = request.data.get("user_id")

    if not user_id:
        return JsonResponse({"error": "user_id is required"}, status=400)

    try:
        user = User.objects.get(tgId=user_id)
    except User.DoesNotExist:
        return JsonResponse({"error": "user not found"}, status=404)

    try:
        amount = Decimal(raw_amount).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except Exception:
        return JsonResponse({"error": "Некорректная сумма"}, status=400)

    if amount < Decimal("10.00"):
        return JsonResponse({"error": "Минимум 10 ₽"}, status=400)

    try:
        payment = _create_yookassa_payment(user, amount)
    except Exception as exc:
        return _yookassa_error_response(exc)

    local_payment = Payment.objects.create(
        user=user,
        amount=amount,
        status="PENDING",
        provider_payment_id=payment.id
    )

    return JsonResponse({
        "url": payment.confirmation.confirmation_url,
        "provider_payment_id": payment.id,
        "payment_uuid": str(local_payment.uuid),
    })


class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = [AllowAny]


class VerdictViewSet(viewsets.ModelViewSet):
    queryset = Verdict.objects.all().order_by('-created_at')
    serializer_class = VerdictSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        queryset = self.queryset.select_related('user').prefetch_related('photos')
        user_id = self.request.query_params.get('user_id')
        code = (self.request.query_params.get('code') or '').strip()

        if code:
            queryset = queryset.filter(code=code.upper())

        if user_id:
            queryset = queryset.filter(user__tgId=user_id)

        return queryset


class VerdictPhotoViewSet(viewsets.ModelViewSet):
    queryset = VerdictPhoto.objects.all()
    serializer_class = VerdictPhotoSerializer
    permission_classes = [AllowAny]


class PaymentViewSet(viewsets.ModelViewSet):
    queryset = Payment.objects.all().order_by('-date')
    serializer_class = PaymentSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        user_id = self.request.query_params.get('user_id')
        if user_id:
            return self.queryset.filter(user__tgId=user_id)
        return self.queryset


# ─── Email authentication ────────────────────────────────────────────────────

def _email_to_tg_id(email: str) -> int:
    """Генерирует отрицательный tgId для email-пользователей, чтобы не пересекаться с Telegram ID."""
    crc = zlib.crc32(email.lower().encode()) & 0x7FFFFFFF
    synthetic = -(crc or 1)
    # На случай коллизии — сдвигаем пока не найдём свободный
    while User.objects.filter(tgId=synthetic).exclude(email=email.lower()).exists():
        synthetic -= 1
    return synthetic


def _get_or_create_email_user(email: str, *, name=None):
    normalized_email = email.strip().lower()
    user = User.objects.filter(email__iexact=normalized_email).first()
    if user:
        return user

    return User.objects.create(
        tgId=_email_to_tg_id(normalized_email),
        email=normalized_email,
        name=name or normalized_email.split("@")[0],
        img=DEFAULT_AVATAR_URL,
        balance="0",
    )


def _set_session_user(request, user):
    request.session["tg_id"] = user.tgId
    request.session.set_expiry(365 * 24 * 60 * 60)
    request.session.pop("email_otp_pending", None)


def _app_review_demo_credentials_match(email: str, password: str) -> bool:
    demo_email = getattr(settings, "APP_REVIEW_DEMO_EMAIL", "").strip().lower()
    demo_password = getattr(settings, "APP_REVIEW_DEMO_PASSWORD", "")
    return bool(
        demo_email
        and demo_password
        and email.strip().lower() == demo_email
        and constant_time_compare(password, demo_password)
    )


def _app_review_demo_balance() -> str:
    raw_balance = str(getattr(settings, "APP_REVIEW_DEMO_BALANCE", "5000")).strip() or "5000"
    try:
        return str(Decimal(raw_balance).quantize(Decimal("0.01")))
    except (InvalidOperation, ValueError):
        return "5000.00"


def _login_app_review_demo_user(request, email: str):
    user = _get_or_create_email_user(email, name="App Review Demo")
    update_fields = []

    demo_balance = _app_review_demo_balance()
    if user.balance != demo_balance:
        user.balance = demo_balance
        update_fields.append("balance")

    if not user.is_free_check_available:
        user.is_free_check_available = True
        update_fields.append("is_free_check_available")

    if user.next_free_check_timestamp is not None:
        user.next_free_check_timestamp = None
        update_fields.append("next_free_check_timestamp")

    if update_fields:
        user.save(update_fields=update_fields)

    _set_session_user(request, user)
    EmailOTPToken.objects.filter(email__iexact=email.strip().lower(), used=False).update(used=True)
    return user


def email_login_page(request):
    """Страница ввода email."""
    if _session_user(request):
        return redirect("home")
    error = request.GET.get("error")
    return render(request, "email_login.html", {"error": error})


def email_send_otp(request):
    """POST: отправляет OTP на email и редиректит на страницу ввода кода."""
    if request.method != "POST":
        return redirect("email_login")

    email = request.POST.get("email", "").strip().lower()
    if not email or "@" not in email:
        return redirect("/email-login/?error=invalid")

    password = request.POST.get("password", "")
    if password:
        if _app_review_demo_credentials_match(email, password):
            _login_app_review_demo_user(request, email)
            return redirect("home")
        return redirect("/email-login/?error=invalid_credentials")

    # Генерируем 6-значный код
    code = "{:06d}".format(random.randint(0, 999999))

    # Инвалидируем старые неиспользованные коды для этого email
    EmailOTPToken.objects.filter(email=email, used=False).update(used=True)

    EmailOTPToken.objects.create(email=email, code=code)

    try:
        send_mail(
            subject="Ваш код входа в LegitCheck",
            message=(
                f"Ваш код для входа: {code}\n\n"
                f"Код действителен 10 минут.\n"
                f"Если вы не запрашивали код — игнорируйте это письмо."
            ),
            from_email=None,  # берётся из DEFAULT_FROM_EMAIL
            recipient_list=[email],
            fail_silently=False,
        )
    except Exception:
        logger.exception("Ошибка отправки OTP на %s", email)
        return redirect("/email-login/?error=send_failed")

    # Сохраняем email в сессии для страницы верификации
    request.session["email_otp_pending"] = email
    return redirect("email_verify")


def email_verify_page(request):
    """Страница ввода OTP-кода."""
    email = request.session.get("email_otp_pending")
    if not email:
        return redirect("email_login")
    error = request.GET.get("error")
    return render(request, "email_otp.html", {"email": email, "error": error})


def email_verify_otp(request):
    """POST: проверяет OTP, создаёт сессию."""
    if request.method != "POST":
        return redirect("email_verify")

    email = request.session.get("email_otp_pending")
    if not email:
        return redirect("email_login")

    code = request.POST.get("code", "").strip()

    token = (
        EmailOTPToken.objects
        .filter(email=email, code=code, used=False)
        .order_by("-created_at")
        .first()
    )

    if not token or token.is_expired:
        return redirect("/email/verify/?error=invalid")

    token.used = True
    token.save(update_fields=["used"])

    user = _get_or_create_email_user(email)
    _set_session_user(request, user)

    return redirect("home")
