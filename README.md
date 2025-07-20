# legitcheck

В проекте используется Telegram‑бот `@LegitLogisticsBot` для авторизации
пользователей. Токены авторизации теперь короче (16 символов) и
передаются боту через ссылку вида:

```
https://t.me/LegitLogisticsBot?start=login_<token>
```

`BOT_TOKEN` и `TELEGRAM_BOT_TOKEN` можно задать через одноимённые
переменные окружения.
