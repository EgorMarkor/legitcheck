from django.shortcuts import render, redirect, get_object_or_404
from telebot.util import parse_web_app_data
from .models import User, Verdict, VerdictPhoto, UploadedVerdictPhoto, Payment
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_protect
from django.urls import reverse
from django.utils.crypto import get_random_string
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
from pcwebapp.models import LoginToken
import json
import logging
import urllib.request
import requests


Configuration.account_id = 1222154
Configuration.secret_key = "live_Y3wIog3WrIrKkUvTF7HID1XDB6mgztrXZZFdx9VbwjQ"

TELEGRAM_BOT_TOKEN = "7620197633:AAHqBbPgVEtloxy6we7YyvMU7eWK9-hSyrU"
TELEGRAM_VERDICT_CHAT_ID = getattr(settings, "TELEGRAM_VERDICT_CHAT_ID", None)
TELEGRAM_MEDIA_GROUP_LIMIT = 10
DEFAULT_PUBLIC_BASE_URL = "https://legitcheck.one"

logger = logging.getLogger(__name__)

# URL аватарки по умолчанию на случай отсутствия фото у пользователя
DEFAULT_AVATAR_URL = "/static/avatar.png"

TARIFF_PRICES = {
    "24h": Decimal("450.00"),
    "15min-expensive": Decimal("650.00"),
    "15min-basic": Decimal("600.00"),
}

REASON_PRICE = Decimal("150.00")
DEFAULT_VERDICT_SPEED = "24h"
DEFAULT_VERDICT_PRICE = Decimal("0.00")
TRUTHY_VALUES = {"1", "true", "yes", "on"}


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


def index(request):
    raw_init_data = (
        request.GET.get("init_data")
        or request.GET.get("tgWebAppData")
    )

    if not raw_init_data:
        user = _session_user(request)
        if user:
            return render(request, "index.html", {"tg_user": user})
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
            "img": tg_user_data.get("photo_url") or DEFAULT_AVATAR_URL,
            "balance": "0",
        }
    )
    if not created:
        photo_url = tg_user_data.get("photo_url")
        if photo_url and user.img != photo_url:
            user.img = photo_url
            user.save(update_fields=["img"])

    request.session["tg_id"] = tg_id
    request.session.set_expiry(365 * 24 * 60 * 60)

    return render(request, "index.html", {
        "tg_user": user
    })


def require_user(view_func):
    def wrapped(request, *args, **kwargs):
        user = _session_user(request)
        if not user:
            return redirect("init")

        request.tg_user = user
        return view_func(request, *args, **kwargs)

    return wrapped



def about(request):
    return render(request, 'confident.html')

def _generate_unique_code():
    # 5 цифр, гарантированно уникально
    code = get_random_string(5, allowed_chars='0123456789')
    while Verdict.objects.filter(code=code).exists():
        code = get_random_string(5, allowed_chars='0123456789')
    return code

from django.db import transaction


def _telegram_api_request(method, payload):
    if not TELEGRAM_BOT_TOKEN:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/{method}"
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            response.read()
    except Exception:
        logger.exception("Failed to call Telegram API %s", method)


def _telegram_api_request_files(method, payload, files):
    if not TELEGRAM_BOT_TOKEN:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/{method}"
    try:
        response = requests.post(url, data=payload, files=files, timeout=20)
        response.raise_for_status()
    except Exception:
        logger.exception("Failed to call Telegram API %s with files", method)


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
    if not TELEGRAM_VERDICT_CHAT_ID:
        return
    text = _build_verdict_message(verdict, include_prompt=True)
    reply_markup = {
        "inline_keyboard": [
            [
                {"text": "Легит", "callback_data": f"verdict:{verdict.id}:legit"},
                {"text": "Не легит", "callback_data": f"verdict:{verdict.id}:fake"},
            ]
        ]
    }
    photos = list(verdict.photos.all())
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
            payload = {
                "chat_id": TELEGRAM_VERDICT_CHAT_ID,
                "media": json.dumps(media),
            }
            if files:
                _telegram_api_request_files("sendMediaGroup", payload, files)
                for file in files.values():
                    file.close()
            else:
                _telegram_api_request("sendMediaGroup", payload)
        _telegram_api_request(
            "sendMessage",
            {
                "chat_id": TELEGRAM_VERDICT_CHAT_ID,
                "text": text,
                "reply_markup": reply_markup,
            },
        )
    else:
        _telegram_api_request(
            "sendMessage",
            {
                "chat_id": TELEGRAM_VERDICT_CHAT_ID,
                "text": text,
                "reply_markup": reply_markup,
            },
        )


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

        transaction.on_commit(lambda: _send_verdict_to_telegram(verdict))

    return verdict


def _serialize_verdict_for_mobile(verdict):
    photos = []
    for photo in verdict.photos.all():
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

    if not category or not brand or not speed:
        return JsonResponse({
            "success": False,
            "error": "Не выбраны все параметры"
        }, status=400)

    if speed not in TARIFF_PRICES:
        return JsonResponse({
            "success": False,
            "error": "Неверный тариф"
        }, status=400)

    # 💰 считаем сумму НА БЭКЕ
    total_price = TARIFF_PRICES[speed]
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
        )

        for f in request.FILES.getlist('photos'):
            VerdictPhoto.objects.create(verdict=verdict, image=f)

        transaction.on_commit(lambda: _send_verdict_to_telegram(verdict))

    return JsonResponse({
        "success": True,
        "redirect_url": reverse("lk")
    })

@require_user
def check_verdict(request):
    code = request.GET.get('code', '').upper()
    verdict = get_object_or_404(Verdict, code=code)
    photos = verdict.photos.all()

    # вместо photos[0]
    first_photo = photos.first()  

    return render(request, 'verdict.html', {
        'tg_user':    request.tg_user,
        'verdict':    verdict,
        'first_photo': first_photo,
        'photos':     photos,
        'code': code,
    })


@require_user
def cab(request):
    verdicts = request.tg_user.verdicts.all().order_by('-created_at')
    return render(request, 'cab.html', {
        'tg_user':  request.tg_user,
        'verdicts': verdicts,
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
    return render(request, 'check.html', {
        'tg_user': request.tg_user,
        'balance': request.tg_user.balance,  # 👈 добавляем
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

    if decision not in {"legit", "fake"}:
        return JsonResponse({"ok": True})

    try:
        verdict = Verdict.objects.get(pk=int(verdict_id))
    except (Verdict.DoesNotExist, ValueError):
        _telegram_api_request(
            "answerCallbackQuery",
            {"callback_query_id": callback_query.get("id"), "text": "Вердикт не найден"},
        )
        return JsonResponse({"ok": True})

    verdict.status = decision
    verdict.save(update_fields=["status"])

    _telegram_api_request(
        "answerCallbackQuery",
        {"callback_query_id": callback_query.get("id"), "text": "Вердикт обновлен"},
    )

    message = callback_query.get("message", {})
    chat = message.get("chat", {})
    if chat.get("id") and message.get("message_id"):
        _telegram_api_request(
            "editMessageReplyMarkup",
            {
                "chat_id": chat.get("id"),
                "message_id": message.get("message_id"),
                "reply_markup": {"inline_keyboard": []},
            },
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
        payment = YooPayment.create(
            {
                "amount": {
                    "value": str(amount),
                    "currency": "RUB"
                },
                "confirmation": {
                    "type": "redirect",
                    "return_url": "https://legitcheck.one"
                },
                "capture": True,
                "description": "Пополнение баланса",
                "receipt": {
                    "customer": {"email": "no-reply@legitcheck.one"},
                    "tax_system_code": 2,
                    "items": [
                        {
                            "description": "Пополнение баланса",
                            "quantity": "1.00",
                            "amount": {"value": str(amount), "currency": "RUB"},
                            "vat_code": 1,
                            "payment_subject": "service",
                            "payment_mode": "full_payment",
                        }
                    ]
                },
                "metadata": {
                    "tg_id": request.tg_user.tgId
                }
            },
            uuid.uuid4()
        )

    except Exception as e:
        details = e.args[0] if getattr(e, "args", None) else str(e)
        return JsonResponse({"error": "YooKassa error", "details": details}, status=400)

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

    obj = data["object"]
    provider_payment_id = obj["id"]
    tg_id = obj.get("metadata", {}).get("tg_id")
    amount = Decimal(obj["amount"]["value"])

    # 🔒 1. Находим платёж
    try:
        payment = Payment.objects.select_for_update().get(
            provider_payment_id=provider_payment_id
        )
    except Payment.DoesNotExist:
        # ❗ неизвестный платёж — игнорируем
        return HttpResponse(status=200)

    # 🔒 2. Если уже обработан — ВЫХОД
    if payment.status == "COMPLETED":
        return HttpResponse(status=200)

    # 🔒 3. Начисляем баланс ОДИН РАЗ
    try:
        user = payment.user
        user.balance = str(
            Decimal(user.balance) + amount
        )
        user.save()

        payment.status = "COMPLETED"
        payment.save()

    except Exception:
        # если что-то пошло не так — не подтверждаем
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

    if 'photo' not in request.FILES:
        return JsonResponse({'error': 'Файл не передан'}, status=400)

    photo = VerdictPhoto.objects.create(
        verdict=verdict,
        image=request.FILES['photo']
    )

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
            "verdict_url": f"{reverse('verdicts')}?code={verdict.code}",
        },
        status=201,
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
            "verdict_url": f"{reverse('verdicts')}?code={verdict.code}",
        },
        status=201,
    )


@csrf_exempt
def api_mobile_get_verdict_by_code(request, code):
    normalized_code = (code or "").strip().upper()
    if not normalized_code:
        return JsonResponse({"success": False, "error": "Не указан код вердикта"}, status=400)

    verdict = (
        Verdict.objects.select_related("user")
        .prefetch_related("photos")
        .filter(code__iexact=normalized_code)
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
        .prefetch_related("photos")
        .filter(id=verdict_id, user=user)
        .first()
    )
    if not verdict:
        return JsonResponse({"success": False, "error": "Вердикт не найден"}, status=404)

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

    verdict = (
        Verdict.objects.select_related("user")
        .prefetch_related("photos")
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

    request.session["tg_id"] = login_token.user.tgId
    request.session.set_expiry(365 * 24 * 60 * 60)
    request.session.cycle_key()

    return JsonResponse(
        {
            "success": True,
            "redirect_url": reverse("home"),
            "user": {
                "tgId": login_token.user.tgId,
                "name": login_token.user.name,
                "username": login_token.user.username,
                "img": login_token.user.img,
                "balance": login_token.user.balance,
            },
        }
    )


def api_auth_restore(request, token):
    """Restore session from persistent auth_token stored in localStorage."""
    import uuid as _uuid
    try:
        parsed = _uuid.UUID(str(token))
    except (ValueError, AttributeError):
        return redirect('/init/?clear_token=1')

    user = User.objects.filter(auth_token=parsed).first()
    if not user:
        return redirect('/init/?clear_token=1')

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
        payment = YooPayment.create(
            {
                "amount": {
                    "value": str(amount),
                    "currency": "RUB"
                },
                "confirmation": {
                    "type": "redirect",
                    "return_url": "https://legitcheck.one"
                },
                "capture": True,
                "description": "Пополнение баланса",
                "receipt": {
                    "customer": {"email": "no-reply@legitcheck.one"},
                    "tax_system_code": 2,
                    "items": [
                        {
                            "description": "Пополнение баланса",
                            "quantity": "1.00",
                            "amount": {"value": str(amount), "currency": "RUB"},
                            "vat_code": 1,
                            "payment_subject": "service",
                            "payment_mode": "full_payment",
                        }
                    ]
                },
                "metadata": {
                    "tg_id": user.tgId
                }
            },
            uuid.uuid4()
        )
    except Exception as e:
        details = e.args[0] if getattr(e, "args", None) else str(e)
        return JsonResponse({"error": "YooKassa error", "details": details}, status=400)

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
            queryset = queryset.filter(code__iexact=code)

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
