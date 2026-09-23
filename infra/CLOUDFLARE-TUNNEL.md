# infra/CLOUDFLARE-TUNNEL.md — публичный HTTPS для локального сервера

Пошаговая инструкция для настройки Cloudflare Tunnel со своим доменом.
Даст стабильный HTTPS-URL для Telegram webhook и Mini App.

---

## Что понадобится (30 минут работы)

1. Купленный домен. Любой (`.ru`, `.online`, `.dev` — от 500 руб/год).
   Регистраторы: reg.ru, timeweb.com, namecheap.com, cloudflare.com/registrar.
2. Аккаунт Cloudflare (бесплатный).
3. Ubuntu-сервер с уже установленным `cloudflared` (см. `infra/README.md`).

---

## Шаг 1. Добавить домен в Cloudflare (5 минут)

1. Зарегистрируйся на https://cloudflare.com/ (бесплатно).
2. Dashboard → «Add a Site» → введи свой домен без `www` (`example.com`).
3. Выбери план **Free**.
4. Cloudflare покажет два NS-сервера, например:
   ```
   ada.ns.cloudflare.com
   sam.ns.cloudflare.com
   ```
5. Зайди к регистратору, где покупал домен → раздел DNS/NS → замени NS-серверы
   на те, что дал Cloudflare.
6. Подожди 5-60 минут — Cloudflare пришлёт email «Site is active».

---

## Шаг 2. Авторизовать cloudflared на сервере (2 минуты)

На своём Ubuntu-сервере:

```bash
cloudflared tunnel login
```

Команда откроет URL в консоли. Скопируй его в браузер, залогинься в Cloudflare,
выбери свой домен, нажми «Authorize».

После этого на сервере в `~/.cloudflared/` появится файл `cert.pem`.

---

## Шаг 3. Создать именованный туннель (1 минута)

```bash
cloudflared tunnel create coursebot
```

Cloudflared создаст туннель с UUID (например `abcd1234-...`) и сохранит
credentials-файл в `~/.cloudflared/<UUID>.json`.

Запиши UUID куда-нибудь — понадобится.

---

## Шаг 4. Привязать поддомен к туннелю (1 минута)

```bash
cloudflared tunnel route dns coursebot coursebot.example.com
```

Замени `example.com` на свой домен. Cloudflare создаст CNAME-запись
`coursebot.example.com → <UUID>.cfargotunnel.com`.

Теперь `https://coursebot.example.com` — твой публичный HTTPS-URL.

---

## Шаг 5. Написать конфиг туннеля (3 минуты)

Создай файл `~/.cloudflared/config.yml`:

```yaml
tunnel: <UUID из шага 3>
credentials-file: /home/YOUR_USER/.cloudflared/<UUID>.json

ingress:
  - hostname: coursebot.example.com
    service: http://localhost:8080
  - service: http_status:404
```

Замени:
- `<UUID>` на реальный.
- `YOUR_USER` на твоё имя пользователя (см. `whoami`).
- `coursebot.example.com` на свой поддомен.
- `http://localhost:8080` на порт, где реально слушает твой backend
  (по `docker-compose.dev.yml` это `8080`).

---

## Шаг 6. Запустить туннель как сервис (5 минут)

Чтобы туннель работал 24/7 и стартовал при ребуте сервера:

```bash
sudo cloudflared service install
sudo systemctl enable cloudflared
sudo systemctl start cloudflared
sudo systemctl status cloudflared
```

Статус должен быть `active (running)`.

Логи туннеля:
```bash
sudo journalctl -u cloudflared -f
```

---

## Шаг 7. Вписать URL в .env и Telegram

В `course-bot/.env`:
```
WEBAPP_URL=https://coursebot.example.com
```

Перезапусти стек:
```bash
docker compose --env-file .env -f infra/docker-compose.dev.yml restart
```

Скажи Telegram, куда слать webhook:
```bash
BOT_TOKEN='<токен>'
WEBHOOK_URL='https://coursebot.example.com/webhook/telegram'
SECRET='<WEBHOOK_SECRET из .env>'
curl -F "url=${WEBHOOK_URL}" \
     -F "secret_token=${SECRET}" \
     "https://api.telegram.org/bot${BOT_TOKEN}/setWebhook"
```

Ответ: `{"ok":true, ...}`.

Скажи BotFather:
```
/setdomain
```
→ выбери бота → введи `https://coursebot.example.com`.

---

## Проверка

Открой в браузере `https://coursebot.example.com/healthz`
(эндпоинт появится у FastAPI, когда Агент реализует).
Ожидание: HTTP 200 и `{"status":"ok"}`.

Напиши боту `/start` в Telegram — должен ответить.

---

## Полезные команды

```bash
# Список туннелей
cloudflared tunnel list

# Инфо по туннелю
cloudflared tunnel info coursebot

# Логи
sudo journalctl -u cloudflared -f

# Рестарт
sudo systemctl restart cloudflared

# Удалить туннель (если хочешь пересоздать)
cloudflared tunnel delete coursebot
```

---

## Переезд на VPS

Когда переедешь на VPS, Cloudflare Tunnel можно **сохранить** —
он работает откуда угодно. Просто:
1. На VPS установи `cloudflared`.
2. Скопируй `~/.cloudflared/` со старого сервера на новый.
3. `sudo systemctl start cloudflared` — работает.

Или отказаться от туннеля и повесить обычный nginx с Let's Encrypt.
Оба варианта одинаково валидны.
