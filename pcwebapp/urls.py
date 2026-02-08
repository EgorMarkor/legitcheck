from django.urls import path
from webapp import views as webapp_views
from . import views

urlpatterns = [
    path('', views.home, name='pc_home'),      # Главная страница
    path('start_check/', views.start_check, name='pc_startcheck'),      # Главная страница
    path('pay/', views.pay, name='pc_pay'),      # Главная страница
    path('account/', views.account, name='pc_account'),      # Главная страница
    path('user_agree/', views.user_agree, name='pc_user_agree'),      # Главная страница
    path('privacy_policy/', views.privacy_policy, name='pc_privacy_policy'),      # Главная страница
    path('public-offer/', views.public_offer, name='pc_public_offer'),
    path('privacy/', views.privacy_policy_public, name='pc_privacy_policy_public'),
    path('verdict/', views.verdict, name='pc_verdicts'),      # Главная страница
    path('home/', views.home_page, name="pc_home_page"),
    path('login/', views.telegram_login, name='pc_login'),
    path('login/poll/<str:token>/', views.poll_token, name='pc_login_poll'),
    path('api/auth/token/', views.api_create_login_token, name='pc_api_create_login_token'),
    path('api/auth/poll/<str:token>/', views.api_poll_login_token, name='pc_api_poll_login_token'),
    path('api/verdict/photos/upload/', views.api_upload_verdict_photos, name='pc_api_upload_verdict_photos'),
    path('api/verdict/create/', views.api_create_verdict, name='pc_api_create_verdict'),
    path('verdict/create/', views.create_verdict, name='create_verdict'),
    path('uslugi/', views.uslugi, name='uslugi'),
    path('telegram/verdict-webhook/', webapp_views.telegram_verdict_webhook, name='telegram_verdict_webhook'),
]
