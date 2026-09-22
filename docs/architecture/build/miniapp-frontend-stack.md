---
file: build/miniapp-frontend-stack.md
block: "—"
title: "Стек Mini App-клиента"
status: рекомендация (утверждается Автором)
doc_version: "скелет v0"
---

# Стек Mini App-клиента

Рекомендуемый стек, соответствующий требованиям ERRATA E2 (CSP) и SEAM-1 (first-launch — точка создания `pid`). Итог ресёрча 2025–2026.

## Фронт

- **React 18+ / TypeScript 5+ / Vite** — стандартная связка Mini App-разработки, поддерживается всеми свежими SDK.
- **@telegram-apps/sdk-react** — актуальный официальный SDK (заменяет старый `@twa-dev/sdk`). См. [docs.telegram-mini-apps.com](https://docs.telegram-mini-apps.com/).
- **create-mini-app** CLI — скелет проекта одной командой: `npx @telegram-apps/create-mini-app`.
- Роутинг — **React Router v6+** или **TanStack Router**.
- Store — **Zustand** (лёгкий, подходит для Mini App). Redux Toolkit — если появятся сложные саги на клиенте.
- Форма — **react-hook-form + zod**. Валидация zod-схем совпадает с JSON-Schema из [config-schemas/](config-schemas/).
- HTTP-клиент — **fetch + tanstack-query** (для кэша и retry). Для оффлайна — IndexedDB (aim: **idb** или **dexie**).

## Telegram Web App SDK — ключевые API

- `WebApp.initData` (raw string) + `WebApp.initDataUnsafe` (parsed) — передавать на бэкенд **строку `initData`** (заголовок `X-Telegram-Init-Data`), не `initDataUnsafe`.
- `WebApp.BottomButton` (ранее `MainButton`, Bot API 10.1) — основная нижняя кнопка.
- `WebApp.BackButton` — верхняя кнопка «назад».
- `WebApp.HapticFeedback.notificationOccurred('success'|'warning'|'error')` — тактильные ответы.
- `WebApp.close()` — закрыть Mini App (после успешной оплаты / завершения онбординга).
- `WebApp.sendData(json)` — отправить данные в бот (до 4096 байт). У нас используется редко — основной канал общения через backend API.
- `WebApp.themeParams` — учитываем светлую/тёмную тему Telegram автоматически.

## Аутентификация

Каждый запрос к `/miniapp/v1/**` идёт с заголовком `X-Telegram-Init-Data: <raw initData string>`. Сервер:

1. Разбирает `initData` на пары ключ-значение.
2. Строит **data-check-string** — все пары кроме `hash`, отсортированные по ключу, соединённые `\n`.
3. Ключ HMAC: `secret_key = HMAC-SHA256(key="WebAppData", msg=bot_token)`.
4. Считает `expected_hash = HMAC-SHA256(key=secret_key, msg=data_check_string)`, сравнивает с `hash`.
5. Проверяет `auth_date` (TTL 24 часа стандарт, но можно ужесточить до 1 часа для чувствительных операций — рекомендация [Askerov](https://www.linkedin.com/pulse/telegram-mini-apps-tma-under-hood-architecture-tech-stack-askerov-jw8pe)).
6. Разбирает `user` (JSON) → `tg_user_id`, ищет в `tg_user_registry` → `pid`. Если нет — first-launch, идёт в SEAM-1.

**Никогда не доверять клиенту** — предупреждение в [Telegram docs](https://core.telegram.org/bots/webapps).

## CSP-заголовок (E2 ERRATA)

Отдаётся с каждым ответом Mini App-хостинга:

```
default-src 'self';
script-src 'self';
style-src 'self' 'unsafe-inline';
connect-src 'self' https://api.telegram.org;
img-src 'self' data: blob: <s3-domain-ru>;
frame-ancestors https://web.telegram.org https://t.me;
report-uri /security/csp-report;
```

`unsafe-eval` **запрещён**. `<s3-domain-ru>` заменяется на реальный домен после решения Автора (Boot-gate).

## Оффлайн и идемпотентность (И4)

- IndexedDB через **dexie** — кэш конфига текстов, черновиков рефлексий и очереди записи.
- Каждое действие пользователя → **`client_op_id: uuid v4`** генерируется на клиенте и хранится 24 часа в IndexedDB. Backend отклоняет повтор с тем же `client_op_id` (`money_ops_idempotent`, `buttons_idempotent`).
- Тихая переавторизация: при `401` — вызов `Telegram.WebApp.close()` + всплывающая инструкция «переоткрыть кнопкой меню».

## Стек в РФ (152-ФЗ)

- Хостинг фронта — Yandex Cloud Object Storage + CDN, либо Timeweb Cloud «Облако 152-ФЗ». Оба указаны в И4.
- Домен фронта — в зоне `.ru` или `.online` с российским регистратором.

## Пример структуры каталога Mini App

```
apps/miniapp/
├── src/
│   ├── main.tsx
│   ├── App.tsx
│   ├── routes/
│   │   ├── onboarding/
│   │   ├── day/
│   │   ├── me/
│   │   ├── content/
│   │   └── payment/
│   ├── api/                  # tanstack-query + fetch
│   ├── store/                # zustand
│   ├── lib/telegram-webapp.ts
│   ├── lib/idb.ts
│   └── lib/csp.ts
├── public/
│   └── index.html
├── vite.config.ts
├── tsconfig.json
└── package.json
```
