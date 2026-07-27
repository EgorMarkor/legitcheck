from django.urls import path, include
from . import views
from django.http import HttpResponse
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
from . import vkchat


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def manifest(request):
    manifest_path = Path(__file__).resolve().parent.parent / "manifest.json"
    with open(manifest_path, encoding="utf-8") as f:
        return HttpResponse(f.read(), content_type="application/manifest+json")


def service_worker(request):
    service_worker_path = Path(__file__).resolve().parent.parent / "sw.js"
    response = HttpResponse(
        service_worker_path.read_text(encoding="utf-8"),
        content_type="application/javascript; charset=utf-8",
    )
    response["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response["Pragma"] = "no-cache"
    response["Service-Worker-Allowed"] = "/"
    return response
    
router = DefaultRouter()
router.register(r'users', UserViewSet)
router.register(r'verdicts', VerdictViewSet)
router.register(r'verdict-photos', VerdictPhotoViewSet)
router.register(r'payments', PaymentViewSet)

urlpatterns = [
    path('vkchat/', vkchat.vkchat_app, name='vkchat_app'),
    path('vkchat/manifest.json', vkchat.vkchat_manifest, name='vkchat_manifest'),
    path('vkchat/api/config/', vkchat.vkchat_config, name='vkchat_config'),
    path('vkchat/api/conversations/', vkchat.vkchat_conversations, name='vkchat_conversations'),
    path('vkchat/api/conversations/<int:peer_id>/messages/', vkchat.vkchat_messages, name='vkchat_messages'),
    path('vkchat/api/conversations/<int:peer_id>/read/', vkchat.vkchat_mark_read, name='vkchat_mark_read'),
    path('vkchat/api/sync/', vkchat.vkchat_sync, name='vkchat_sync'),
    path('vkchat/api/push/subscribe/', vkchat.vkchat_push_subscribe, name='vkchat_push_subscribe'),
    path('vkchat/api/push/unsubscribe/', vkchat.vkchat_push_unsubscribe, name='vkchat_push_unsubscribe'),
    path('', views.init, name='init'),  # пример маршрута
    path('home/', views.index, name='home'),  # пример маршрута
    path('about/', views.about, name='about'),  # ещё один маршрут
    path('account/', views.cab, name="lk"),
    path('account/delete/', views.account_delete, name="account_delete"),
    path('promo/', views.promo, name="promo"),
    path('verdicts/', views.verdicts, name="verdicts"),
    path('check/', views.check, name="check"),
    path('payment/', views.payment, name="payment"),
    path('confident/', views.confident, name="confident"),
    path('license/', views.license, name="license"),
    path('verdict/', views.check_verdict, name="verdict"),
    path('verdict/create/', views.create_verdict, name='create_verdict'),
    path('verdict/create/free/', views.create_free_verdict, name='create_free_verdict'),
    path('api/verdict/photos/upload/', views.api_upload_verdict_photos, name='api_upload_verdict_photos'),
    path('api/verdict/create/', views.api_create_verdict, name='api_create_verdict'),
    path('api/mobile/verdict/photos/upload/', views.api_mobile_upload_verdict_photos, name='api_mobile_upload_verdict_photos'),
    path('api/mobile/verdict/create/', views.api_mobile_create_verdict, name='api_mobile_create_verdict'),
    path('api/mobile/verdict/by-code/<str:code>/', views.api_mobile_get_verdict_by_code, name='api_mobile_get_verdict_by_code'),
    path('api/mobile/verdict/<int:verdict_id>/upload-photo/', views.api_mobile_upload_verdict_photo, name='api_mobile_upload_verdict_photo'),
    path('api/push/config/', views.api_push_config, name='api_push_config'),
    path('api/push/web/subscribe/', views.api_push_web_subscribe, name='api_push_web_subscribe'),
    path('api/push/native/register/', views.api_push_native_register, name='api_push_native_register'),
    path('articles/', views.articles, name="articles"),
    path('auth_check/', views.auth_check, name="auth_check"),
    path('our_support/', views.our_support, name="our_support"),
    path('feedbacks/', views.feedbacks, name="feedbacks"),
    path('start_check/', views.start_check, name="start_check"),
    path("payment/create/", views.create_payment),
    path("api/payment/create-yookassa/", views.create_yookassa_payment_api),
    path("yookassa/webhook/", views.yookassa_webhook),
    path("payment/success/", views.payment_success),
    path('verdict/<int:verdict_id>/upload-photo/', views.upload_verdict_photo, name='upload_verdict_photo'),
    path('api/auth/token/', views.api_create_login_token, name='api_create_login_token'),
    path('api/auth/poll/<str:token>/', views.api_poll_login_token, name='api_poll_login_token'),
    path('api/auth/web-login/<str:token>/', views.api_web_login_with_token, name='api_web_login_with_token'),
    path('api/auth/restore/', views.api_auth_restore, name='api_auth_restore'),
    
    path("manifest.json", manifest),
    path("manifest.json/", manifest),
    path("manifest.webmanifest", manifest),
    
    path("sw.js", service_worker, name="service_worker"),

    # ВСЕ папки (ios/, android/, windows11/)
    re_path(
        r'^(?P<path>(ios|android|windows11)/.*)$',
        serve,
        {'document_root': BASE_DIR}
    ),
    path('api/', include(router.urls)),

    # Email authentication
    path('email-login/', views.email_login_page, name='email_login'),
    path('email/send-otp/', views.email_send_otp, name='email_send_otp'),
    path('email/verify/', views.email_verify_page, name='email_verify'),
    path('email/verify-otp/', views.email_verify_otp, name='email_verify_otp'),
]
