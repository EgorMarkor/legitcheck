# LegitCheck PWA iOS Shell (Capacitor)

Эта папка нужна, чтобы собрать iOS-приложение-оболочку поверх PWA.
По умолчанию оболочка смотрит на `http://127.0.0.1:8000`.

## 1. Установка зависимостей

```bash
cd mobile-pwa-shell
npm install
```

## 2. Добавление iOS-проекта

```bash
npm run add:ios
```

## 3. Синхронизация

```bash
npm run sync:ios
```

## 4. Открыть Xcode

```bash
npm run open:ios
```

Дальше в Xcode:
1. Выберите Team и Bundle Identifier.
2. Выберите устройство/симулятор.
3. Build/Run или Archive для релизной сборки.

## Смена адреса сервера (опционально)

Чтобы оболочка открывала другой URL, можно переопределить `PWA_URL`:

```bash
PWA_URL=http://<ваш-local-ip>:8000 npm run sync:ios
```

Используйте `local-ip`, а не `localhost`, чтобы iOS-симулятор/устройство видел сервер.
