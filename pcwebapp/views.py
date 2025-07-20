from django.shortcuts import render, redirect
from django.utils.crypto import get_random_string
from django.utils import timezone
from django.http import JsonResponse, HttpResponse

from .models import LoginToken
from webapp.models import User

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

def account(request):
    return render(request, 'pc/account.html')


def user_agree(request):
    return render(request, 'pc/user_agree.html')


def privacy_policy(request):
    return render(request, 'pc/privacy_policy.html')


def verdicts(request):
    return render(request, 'pc/verdicts.html')


def home_page(request):
    return render(request, 'pc/home_page.html')


def _client_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0]
    return request.META.get("REMOTE_ADDR")


def telegram_login(request):
    ip = _client_ip(request)
    active = LoginToken.objects.filter(
        ip_address=ip,
        used_at__isnull=True,
        created_at__gte=timezone.now() - timezone.timedelta(minutes=5),
    ).count()
    if active >= 5:
        return HttpResponse("Too many active tokens", status=429)

    token = get_random_string(6)
    LoginToken.objects.create(token=token, ip_address=ip)
    return render(request, 'pc/tg_login.html', {'token': token})


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
