from django.shortcuts import render, redirect, get_object_or_404
from telebot.util import parse_web_app_data
from .models import User, Verdict, VerdictPhoto
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_protect
from django.urls import reverse
from django.utils.crypto import get_random_string
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse, HttpResponseBadRequest
import random

TELEGRAM_BOT_TOKEN = "7620197633:AAHqBbPgVEtloxy6we7YyvMU7eWK9-hSyrU"

# URL аватарки по умолчанию на случай отсутствия фото у пользователя
DEFAULT_AVATAR_URL = "/static/avatar.png"

def _generate_device_id():
    """Генерирует уникальный отрицательный ID для аккаунта устройства."""
    while True:
        device_id = -random.randint(1, 2_147_483_647)
        if not User.objects.filter(tgId=device_id).exists():
            return device_id


def init(request):
    raw_init_data = request.GET.get('init_data')
    device_flag = request.GET.get('device')

    # Если не переданы параметры, но в сессии уже есть пользователь — сразу показываем главную
    if not raw_init_data and device_flag is None:
        tg_id_session = request.session.get('tg_id')
        if tg_id_session:
            try:
                tg_user = User.objects.get(tgId=tg_id_session)
                return render(request, 'index.html', {'tg_user': tg_user})
            except User.DoesNotExist:
                pass
        return render(request, 'init.html')

    tg_user = None
    if raw_init_data:
        # Инициализация через Telegram WebApp
        webapp_data = parse_web_app_data(TELEGRAM_BOT_TOKEN, raw_init_data)
        tg_user_data = webapp_data.get('user', {})

        tg_id = tg_user_data.get('id')
        name = tg_user_data.get('first_name', '')
        username = tg_user_data.get('username', '')
        photo = tg_user_data.get('photo_url') or DEFAULT_AVATAR_URL

        if tg_id:
            tg_user, created = User.objects.get_or_create(
                tgId=tg_id,
                defaults={
                    'name': name,
                    'username': username,
                    'img': photo,
                    'balance': '0',
                }
            )

            if not created and not tg_user.img:
                tg_user.img = photo
                tg_user.save(update_fields=['img'])

            request.session['tg_id'] = tg_id
            response = render(request, 'index.html', {'tg_user': tg_user})
            response.set_cookie('device_user_id', tg_id, max_age=60 * 60 * 24 * 365 * 10)
            return response

    # Инициализация без Telegram – по устройству
    device_cookie = request.COOKIES.get('device_user_id')
    if device_cookie:
        try:
            tg_user = User.objects.get(tgId=int(device_cookie))
        except (ValueError, User.DoesNotExist):
            tg_user = None

    if tg_user is None:
        device_id = _generate_device_id()
        tg_user = User.objects.create(
            tgId=device_id,
            name='Гость',
            username=None,
            img=DEFAULT_AVATAR_URL,
            balance='0',
        )
        response = render(request, 'index.html', {'tg_user': tg_user})
        response.set_cookie('device_user_id', tg_user.tgId, max_age=60 * 60 * 24 * 365 * 10)
    else:
        response = render(request, 'index.html', {'tg_user': tg_user})

    request.session['tg_id'] = tg_user.tgId
    return response

def index(request):
    """
    После первого захода из WebApp-а в GET-параметре приходит init_data.
    Распарсим его, сверим или создадим пользователя, запишем tg_id в сессию.
    """
    raw_init_data = request.GET.get('init_data')
    if not raw_init_data:
        # Если пользователь перешёл сюда не из WebApp — отправляем заново на init
        return redirect('init')

    # Распарсим данные от Telegram
    webapp_data = parse_web_app_data(TELEGRAM_BOT_TOKEN, raw_init_data)
    tg_user_data = webapp_data.get('user', {})

    tg_id    = tg_user_data.get('id')
    name     = tg_user_data.get('first_name', '')
    username = tg_user_data.get('username', '')
    photo    = tg_user_data.get('photo_url') or DEFAULT_AVATAR_URL

    if not tg_id:
        return redirect('init')

    # Найдём или создадим запись в БД
    tg_user, created = User.objects.get_or_create(
        tgId=tg_id,
        defaults={
            'name':     name,
            'username': username,
            'img':      photo,
            'balance':  '0',
        }
    )

    # Если пользователь уже существует и у него отсутствует аватар — задаём плейсхолдер
    if not created and not tg_user.img:
        tg_user.img = photo
        tg_user.save(update_fields=['img'])

    # Сохраним tg_id в сессии — при присвоении любому ключу сессия будет создана
    request.session['tg_id'] = tg_id

    # Рендерим главную страницу WebApp
    return render(request, 'index.html', {'tg_user': tg_user})

def _require_tg_user(view_func):
    """
    Декоратор для остальных страниц — проверяет наличие tg_id в сессии
    и подгружает объект User, или редиректит на init.
    """
    def wrapped(request, *args, **kwargs):
        tg_id = request.session.get('tg_id')
        if not tg_id:
            return redirect('init')
        try:
            request.tg_user = User.objects.get(tgId=tg_id)
        except User.DoesNotExist:
            return redirect('init')
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

@csrf_exempt
@require_POST
@_require_tg_user
def create_verdict(request):
    user = request.tg_user

    # 2) Обязательные поля
    category = request.POST.get('category')        # например "sneakers"
    brand    = request.POST.get('brand')           # "nike", "jordan" и т.д.
    comment  = request.POST.get('comment', '').strip()

    if not category or not brand:
        return JsonResponse({'success': False, 'error': 'Не выбрана категория или бренд'}, status=400)

    # 3) Создаём Verdict
    verdict = Verdict.objects.create(
        user=user,
        status='inpending',             # например, сразу «в обработке»
        category=category,
        brand=brand,
        item_model='',                  # можно передавать, если нужно
        comment='',                     # внутренняя заметка, оставляем пустой
        comment_from_user=comment,
        code=_generate_unique_code()
    )

    # 4) Прикрепляем фото
    #   * все файлы <input name="photos"> и <input name="additional_photos">
    for f in request.FILES.getlist('photos'):
        VerdictPhoto.objects.create(verdict=verdict, image=f)
    for f in request.FILES.getlist('additional_photos'):
        VerdictPhoto.objects.create(verdict=verdict, image=f)

    # 5) Всё ок — вернём JSON с редиректом
    return JsonResponse({
        'success': True,
        'redirect_url': reverse('home')  # например, страница с итогом
    })

@_require_tg_user
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
    })


@_require_tg_user
def cab(request):
    verdicts = request.tg_user.verdicts.all().order_by('-created_at')
    return render(request, 'cab.html', {
        'tg_user':  request.tg_user,
        'verdicts': verdicts,
    })
    
    
@_require_tg_user
def articles(request):
    return render(request, 'articles.html', {
        'tg_user':  request.tg_user,
    })

@_require_tg_user
def verdicts(request):
    return render(request, 'verdicts.html', {
        'tg_user': request.tg_user,
    })

@_require_tg_user
def check(request):
    return render(request, 'check.html', {
        'tg_user': request.tg_user,
    })

@_require_tg_user
def payment(request):
    return render(request, 'payment.html', {
        'tg_user': request.tg_user,
    })

@_require_tg_user
def confident(request):
    return render(request, 'confident.html', {
        'tg_user': request.tg_user,
    })

@_require_tg_user
def license(request):
    return render(request, 'license_sogl.html', {
        'tg_user': request.tg_user,
    })
