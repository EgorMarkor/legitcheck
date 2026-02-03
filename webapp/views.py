from django.shortcuts import render, redirect, get_object_or_404
from telebot.util import parse_web_app_data
from .models import User, Verdict, VerdictPhoto
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_protect
from django.urls import reverse
from django.utils.crypto import get_random_string
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse, HttpResponseBadRequest, HttpResponse
import uuid
from yookassa import Configuration, Payment as YooPayment
from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from yookassa import Payment as YooPayment
from yookassa.domain.notification import WebhookNotification
from decimal import Decimal, ROUND_HALF_UP
import os
import traceback
from .models import Payment
import json
import logging
import urllib.request
import requests


Configuration.account_id = 1222154
Configuration.secret_key = "live_E_z0lmFEzaq0D-6XyHfgCIz9WS32jXgMcLQIkdZOZ8s"

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


def init(request):
    # Точка входа: показываем кнопку Telegram WebApp
    return render(request, 'init.html')


def index(request):
    raw_init_data = (
        request.GET.get("init_data")
        or request.GET.get("tgWebAppData")
    )

    if not raw_init_data:
        return redirect("init")

    try:
        webapp_data = parse_web_app_data(
            TELEGRAM_BOT_TOKEN,
            raw_init_data
        )
    except Exception:
        return redirect("init")

    tg_user_data = webapp_data.get("user")
    if not tg_user_data:
        return redirect("init")

    tg_id = tg_user_data.get("id")
    if not tg_id:
        return redirect("init")

    user, _ = User.objects.get_or_create(
        tgId=tg_id,
        defaults={
            "name": tg_user_data.get("first_name", ""),
            "username": tg_user_data.get("username"),
            "img": tg_user_data.get("photo_url") or DEFAULT_AVATAR_URL,
            "balance": "0",
        }
    )

    request.session["tg_id"] = tg_id

    return render(request, "index.html", {
        "tg_user": user
    })


def require_user(view_func):
    def wrapped(request, *args, **kwargs):
        tg_id = request.session.get("tg_id")

        if not tg_id:
            return redirect("init")

        try:
            request.tg_user = User.objects.get(tgId=tg_id)
        except User.DoesNotExist:
            request.session.pop("tg_id", None)
            return redirect("init")

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

from decimal import Decimal
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
        user_id = self.request.query_params.get('user_id')
        if user_id:
            return self.queryset.filter(user__tgId=user_id)
        return self.queryset


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
