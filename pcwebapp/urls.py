from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='pc_home'),      # Главная страница
    path('start_check/', views.start_check, name='pc_startcheck'),      # Главная страница
    path('pay/', views.pay, name='pc_pay'),      # Главная страница
    path('account/', views.account, name='pc_account'),      # Главная страница
    path('user_agree/', views.user_agree, name='pc_user_agree'),      # Главная страница
    path('privacy_policy/', views.privacy_policy, name='pc_privacy_policy'),      # Главная страница
    path('verdicts/', views.verdicts, name='pc_verdicts'),      # Главная страница
    path('home/', views.home_page, name="pc_home_page"),
    path('telegram/login/', views.telegram_login, name='pc_telegram_login'),
    path('telegram/logout/', views.telegram_logout, name='pc_telegram_logout'),
]
