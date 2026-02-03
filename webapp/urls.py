from django.urls import path, include
from . import views
from django.http import JsonResponse
import json
from pathlib import Path
from django.urls import re_path
from django.views.static import serve
from django.conf import settings
import os
from rest_framework.routers import DefaultRouter
from .views import (
    UserViewSet,
    VerdictViewSet,
    VerdictPhotoViewSet,
    PaymentViewSet
)


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def manifest(request):
    manifest_path = Path(__file__).resolve().parent.parent / "manifest.json"
    with open(manifest_path, encoding="utf-8") as f:
        return JsonResponse(json.load(f), safe=False)
    
router = DefaultRouter()
router.register(r'users', UserViewSet)
router.register(r'verdicts', VerdictViewSet)
router.register(r'verdict-photos', VerdictPhotoViewSet)
router.register(r'payments', PaymentViewSet)

urlpatterns = [
    path('', views.init, name='init'),  # пример маршрута
    path('home/', views.index, name='home'),  # пример маршрута
    path('about/', views.about, name='about'),  # ещё один маршрут
    path('account/', views.cab, name="lk"),
    path('verdicts/', views.verdicts, name="verdicts"),
    path('check/', views.check, name="check"),
    path('payment/', views.payment, name="payment"),
    path('confident/', views.confident, name="confident"),
    path('license/', views.license, name="license"),
    path('verdict/', views.check_verdict, name="verdict"),
    path('verdict/create/', views.create_verdict, name='create_verdict'),
    path('articles/', views.articles, name="articles"),
    path('auth_check/', views.auth_check, name="auth_check"),
    path('our_support/', views.our_support, name="our_support"),
    path('telegram/verdict-webhook/', views.telegram_verdict_webhook, name='telegram_verdict_webhook'),
    path('feedbacks/', views.feedbacks, name="feedbacks"),
    path('start_check/', views.start_check, name="start_check"),
    path("payment/create/", views.create_payment),
    path("api/payment/create-yookassa/", views.create_yookassa_payment_api),
    path("yookassa/webhook/", views.yookassa_webhook),
    path("payment/success/", views.payment_success),
    path('verdict/<int:verdict_id>/upload-photo/', views.upload_verdict_photo, name='upload_verdict_photo'),
    
    path("manifest.json/", manifest),
    
    re_path(
        r'^sw\.js$',
        serve,
        {'document_root': BASE_DIR, 'path': 'sw.js'}
    ),

    # ВСЕ папки (ios/, android/, windows11/)
    re_path(
        r'^(?P<path>(ios|android|windows11)/.*)$',
        serve,
        {'document_root': BASE_DIR}
    ),
    path('api/', include(router.urls)),
]
