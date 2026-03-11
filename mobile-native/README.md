# LegitCheck Native (Expo)

Нативный мобильный клиент (React Native + Expo), повторяющий ключевой UX и функционал Django Web App.

## Что реализовано

- Авторизация через Telegram login token (`/api/auth/token/` + polling `/api/auth/poll/<token>/`)
- Главный экран в стилистике web-версии
- Пошаговое создание заявки на проверку (бренд -> категория -> фото/тариф -> подтверждение)
- Создание вердикта через mobile API (`/api/mobile/verdict/photos/upload/`, `/api/mobile/verdict/create/`)
- Экран поиска вердикта по 5-значному коду
- Детальная карточка вердикта + загрузка дополнительных фото
- Профиль пользователя со списком заявок и фильтрами
- Платёжный экран через YooKassa API (`/api/payment/create-yookassa/`)

## Подготовка

1. Установите Node.js 20+
2. Установите зависимости:

```bash
cd mobile-native
npm install
```

## Запуск

```bash
npm run start
```

Для запуска на устройстве используйте Expo Go или соберите dev build:

```bash
npm run android
npm run ios
```

## Конфигурация API

Базовый URL бэкенда задается в `app.json`:

```json
{
  "expo": {
    "extra": {
      "apiBaseUrl": "https://legitcheck.one"
    }
  }
}
```

## Важные endpoint'ы (используются клиентом)

- `POST /api/auth/token/`
- `GET /api/auth/poll/<token>/`
- `GET /api/users/<tgId>/`
- `GET /api/verdicts/?user_id=<tgId>`
- `POST /api/mobile/verdict/photos/upload/`
- `POST /api/mobile/verdict/create/`
- `GET /api/mobile/verdict/by-code/<code>/`
- `POST /api/mobile/verdict/<id>/upload-photo/`
- `POST /api/payment/create-yookassa/`
