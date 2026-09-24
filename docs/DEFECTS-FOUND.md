# DEFECTS-FOUND.md — расхождения архитектуры с реальностью

Сюда агент пишет расхождения, найденные при реализации.

**НЕ править `docs/architecture/**`** — это read-only зеркало.
Все правки архитектуры делаются в репо DOCS-course-bot.

## Формат записи

## D-N. Краткое название

- **Файл архитектуры (зеркало):** `docs/architecture/…`
- **Файл реализации:** `apps/…`
- **Суть расхождения:** описание что не сходится.
- **Предлагаемое решение:** что предлагает агент.
- **Ждём решения Автора:** да/нет.

---

## D-1. Блок 15: доставка медиа

- **Файл архитектуры (зеркало):** `docs/architecture/build/DIVISION.md`,
  `docs/architecture/15-content-antipiracy.md` (и подпапка `15/`).
- **Файл реализации:** пока не создан.
- **Суть расхождения:** DIVISION.md говорит, что Mini App отдаёт медиа
  через pre-signed URL. Блок 15 (антипираттство) утверждает,
  что видео и материалы курса живут только во внешнем публичном
  Telegram-канале, бот не хостит медиа и не отдаёт `file_id`.
  Схемы «pre-signed URL» и «внешний Telegram-канал» противоречат друг другу.
- **Предлагаемое решение:** Автору определить, какой источник медиа —
  S3 pre-signed URL для собственного хостинга или внешний Telegram-канал.
- **Ждём решения Автора:** да.

## D-2. CSP: три разные редакции в зеркале

- **Файл архитектуры (зеркало):** `normative/errata-unified.md` (E2 `csp_final`),
  `build/miniapp-frontend-stack.md`, `build/miniapp-api-contract.yaml` (комментарий в конце).
- **Файл реализации:** `apps/miniapp/nginx.conf`.
- **Суть расхождения:** E2 разрешает `script-src 'self' https://telegram.org`
  и `frame-ancestors https://web.telegram.org https://telegram.org`. В build-файлах
  указаны `script-src 'self'`, `connect-src 'self' https://api.telegram.org`
  и `frame-ancestors https://web.telegram.org https://t.me`.
- **Решение агента:** взята редакция E2 (у ERRATA высшее старшинство). Домен
  `{s3-domain-ru}` не подставлен: это плейсхолдер-шлюз, решение Автора.
- **Решение Автора:** выравнивать CSP в DOCS-course-bot, не здесь.
  В `apps/miniapp/nginx.conf` остаётся редакция E2.
- **Ждём решения Автора:** нет.

## D-3. Остатки MinIO и версия Garage в документах

- **Файл архитектуры (зеркало):** `build/build-order.md` (Итерация 0-А: «MinIO», `minio-init`).
- **Файлы вне зеркала:** `.genspark/rules.md` (хосты `minio:9000`),
  `infra/SERVER-IRONCLAD.md` (`dxflrs/garage:v2.1.0`, а в compose и README — `v2.3.0`).
- **Суть расхождения:** MinIO устарел, код использует Garage (`http://garage:3900`).
- **Решение агента:** в коде только Garage.
- **Статус:** вне зеркала исправлено — `.genspark/rules.md` (хосты MinIO → Garage
  `garage:3900` / `127.0.0.1:9000`) и `infra/SERVER-IRONCLAD.md` (`v2.1.0` → `v2.3.0`)
  в PR «docs: dev-вход через Tailscale, --env-file, остатки MinIO».
  MinIO в зеркале (`build/build-order.md`: Итерация 0-А, `minio`, `minio-init`,
  состав `docker-compose.yaml`) — править в DOCS-course-bot.
- **Ждём решения Автора:** нет (правка зеркала — в DOCS-course-bot).

## D-4. Кто принимает Telegram webhook

- **Файл архитектуры (зеркало):** `build/DIVISION.md` (backend: «Обработчик Telegram Webhook»).
- **Файлы реализации:** `apps/bot/bot/app.py`, `infra/README.md` (шаг 8: `setWebhook` → `/webhook/telegram`).
- **Суть расхождения:** по DIVISION апдейты принимает backend, но диспетчер
  aiogram живёт в `apps/bot`. Контракт передачи апдейтов api → bot не описан.
- **Решение агента:** в Итерации 0-А бот работает на long polling (входящий порт
  не нужен). Если webhook зарегистрирован, бот его не удаляет, а пишет ошибку в лог.
- **Решено (Автор):** long polling до отдельной итерации webhook. `setWebhook`
  в `infra/README.md` помечен «НЕ выполнять», добавлена команда `deleteWebhook`.
- **Ждём решения Автора:** нет.

## D-5. Публичный вход: Cloudflare Tunnel неприменим

- **Файл архитектуры (зеркало):** `build/build-order.md` (Итерация 0-А: «публичный
  HTTPS через Cloudflare Tunnel», шаг 1 «`cloudflared` установлен», шаг 3
  «именованный туннель», ссылка на `infra/CLOUDFLARE-TUNNEL.md`).
- **Файлы реализации:** `infra/README.md`, `infra/CLOUDFLARE-TUNNEL.md`,
  `infra/SERVER-IRONCLAD.md`.
- **Суть расхождения:** зеркало предполагает Cloudflare Tunnel как вход. Факты
  (проверены Автором на IRONCLAD 24.09.2026):
  - Cloudflare Tunnel из РФ нестабилен: ~2200 обрывов за месяц;
  - на сервере работает служба `cloudflared` чужого проекта maxmover —
    `cloudflared service install` для course-bot с ней конфликтует; её не трогать;
  - dev-вход — Tailscale serve (только tailnet, только Автор);
  - прод / внешние тестировщики — позже: российский VPS как вход, туннель
    дом→VPS через autossh или WireGuard (не Tailscale: из РФ блокируются его
    админка и логин).
- **Сделано здесь:** `infra/README.md` переписан под Tailscale serve;
  `infra/CLOUDFLARE-TUNNEL.md` сохранён как архив с предупреждением «НЕ применять
  на IRONCLAD».
- **Предлагаемое решение:** в DOCS-course-bot поправить `build/build-order.md`
  (вход Итерации 0-А и ссылку на `infra/CLOUDFLARE-TUNNEL.md`).
- **Ждём решения Автора:** да — провайдер VPS.

## D-6. Ограничения Telegram в РФ

- **Файл архитектуры (зеркало):** `build/build-order.md` (Итерация 0-Б, хостинг),
  `99-legal.md` / `99/` (152-ФЗ).
- **Файлы реализации:** пока нет (инфраструктурный риск).
- **Суть расхождения:** с февраля 2026 ограничения Telegram в РФ нарастают.
  Архитектура не учитывает риски:
  - участникам может понадобиться VPN, чтобы открыть бота и Mini App;
  - боту на РФ-VPS могут ограничить доступ к `api.telegram.org`
    (long polling и отправка сообщений перестанут работать).
- **Предлагаемое решение:** нужна позиция Автора: где хостить бота (доступ
  к `api.telegram.org`) и где хранить данные участников (152-ФЗ — в РФ).
  Агент вариантов не выбирает.
- **Ждём решения Автора:** да.

## D-7. initData без проверки подписи

- **Файл архитектуры (зеркало):** `build/miniapp-api-contract.yaml`
  (`securitySchemes.TelegramInitData`), `build/miniapp-security-checklist.md`,
  `build/build-order.md` (Итерация 1: «Валидация `initData` на сервере»).
- **Файл реализации:** `apps/api/app/telegram_init_data.py`.
- **Суть расхождения:** в Итерации 0-А это заглушка: заголовок
  `X-Telegram-Init-Data` обязателен (без него — `401 TG_INIT_MISSING`), но
  HMAC-подпись и `auth_date` НЕ проверяются (`verified=False`). Пока вход только
  через Tailscale serve (tailnet, один Автор), риск ограничен.
- **Предлагаемое решение:** реализовать проверку подписи и TTL в Итерации 1
  ДО любого внешнего доступа (Tailscale Funnel, VPS). План есть — AGENTS.md,
  «Как валидировать initData».
- **Ждём решения Автора:** нет (план есть).

## D-8. BotFather: `/setmenubutton`, `/setdomain`, `/newapp` не нужны для Mini App

- **Файл архитектуры (зеркало):** `build/DIVISION.md` (Bot: «Меню-кнопка → открытие
  Mini App (`WebAppInfo`, `/setmenubutton`)»; приоритеты бота, п.1: «Menu Button →
  Mini App URL (`/setmenubutton` в BotFather)»), `build/build-order.md`
  (Итерация 0-А, шаг 2: `/newbot`, `/newapp` «домен привяжется после туннеля»;
  Итерация 0-Б, шаг 2: `/newbot`, `/newapp`, `/setmenubutton https://<s3-domain-ru>/`, `/setdomain`).
- **Файлы реализации:** `apps/bot/bot/app.py` (Menu Button ставится ботом через
  `set_chat_menu_button` из `WEBAPP_URL`), `infra/README.md` (шаги 1 и 8).
- **Суть расхождения:** зеркало описывает настройку Mini App руками в BotFather.
  Факты (проверены Автором на IRONCLAD):
  - Menu Button бот ставит сам при старте из `WEBAPP_URL` — `/setmenubutton` не нужен;
  - `/setdomain` — настройка Telegram Login Widget, к Mini App отношения не имеет;
  - `/newapp` нужен только для прямой ссылки вида `t.me/<бот>/<app>`.
- **Сделано здесь:** `infra/README.md`, шаги 1 и 8, переписаны под эти факты.
- **Предлагаемое решение:** править в DOCS-course-bot (`build/DIVISION.md`,
  `build/build-order.md`): Menu Button — через Bot API из `WEBAPP_URL`;
  `/setdomain` — только для Login Widget; `/newapp` — только для прямой ссылки.
- **Ждём решения Автора:** нет.

<!-- следующие записи (D-9, ...) добавляет агент по мере обнаружения -->
