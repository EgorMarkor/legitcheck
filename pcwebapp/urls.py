from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),      # Главная страница
    path('start_check/', views.start_check, name='startcheck'),      # Главная страница
    path('pay/', views.pay, name='pay'),      # Главная страница
    path('account/', views.account, name='account'),      # Главная страница
    path('user_agree/', views.user_agree, name='user_agree'),      # Главная страница
    path('privacy_policy/', views.privacy_policy, name='privacy_policy'),      # Главная страница
    path('verdicts/', views.verdicts, name='verdicts'),      # Главная страница
    path('home/', views.home_page, name="home_page"),
    path('telegram/login/', views.telegram_login, name='telegram_login'),
]
