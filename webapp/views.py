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
import traceback
from .models import Payment


Configuration.account_id = 1222154
Configuration.secret_key = "live_E_z0lmFEzaq0D-6XyHfgCIz9WS32jXgMcLQIkdZOZ8s"

TELEGRAM_BOT_TOKEN = "7620197633:AAHqBbPgVEtloxy6we7YyvMU7eWK9-hSyrU"

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
from .models import User, Verdict, VerdictPhoto, Payment
from .serializers import (
    UserSerializer,
    VerdictSerializer,
    VerdictPhotoSerializer,
    PaymentSerializer
)


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
