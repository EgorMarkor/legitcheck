from django.shortcuts import render
import hashlib
import hmac
import time
from django.conf import settings
from django.contrib.auth import login
from django.shortcuts import redirect
from django.contrib.auth.models import User
from django.http import HttpResponseBadRequest

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
