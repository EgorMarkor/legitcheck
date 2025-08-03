from django.urls import path
from . import views

urlpatterns = [
    path('', views.init, name='init'),  # пример маршрута
    path('home/', views.init, name='home'),  # главная страница после инициализации
    path('about/', views.about, name='about'),  # ещё один маршрут
    path('account/', views.cab, name="lk"),
    path('verdicts/', views.verdicts, name="verdicts"),
    path('check/', views.check, name="check"),
    path('payment/', views.payment, name="payment"),
    path('confident/', views.confident, name="confident"),
    path('license/', views.license, name="license"),
    path('verdict/', views.check_verdict, name="verdict"),
    path('verdict/create/', views.create_verdict, name='create_verdict'),
    path('articles/', views.articles, name="articles")
]
