---
file: build/miniapp-security-checklist.md
title: "Production-checklist безопасности Telegram Mini App"
status: скелет (наполняется при первой реализации)
doc_version: "checklist v1"
policy: "Обязательный проход при каждом релизе Mini App. Связан с ERRATA E2, SEAM-1, И4."
---

# miniapp-security-checklist.md — production-checklist безопасности Mini App

Каждый пункт — блокер прод-запуска, если не выполнен.

## 1. Валидация initData

- Никогда не доверять `initDataUnsafe`.
- На backend передавать **исходную строку `initData` целиком**.
- Валидация — только на сервере, до создания сессии/PID/любых прав.
- Пакеты-эталоны: `@tma.js/init-data-node` (Node) или `init-data-golang` (Go); аналог на
  Python на выбор.

## 2. Свежесть initData

Telegram передаёт `auth_date` (Unix timestamp создания).
Проект должен:

- проверять, что `auth_date` не старше окна;
- окно задавать конфигом (`miniapp.init_data.max_age_seconds`, ориентир — 3600);
- при просрочке — требовать повторного запуска Mini App.

Без этой политики украденный initData можно использовать бесконечно.

## 3. Age-gate и создание PID (SEAM-1)

Первый запуск Mini App обязан идти строго в порядке:

1. `age_gate` (hard check — ввод даты рождения);
2. `legal_consents` (C1–C6, разрешённые);
3. `payment`;
4. `pid_creation` (участник материализуется в БД).

Инвариант — `INV-AGE-GATE-BEFORE-PID` (ADD3 ERRATA).

Создание записи `tg_user_registry` вне обработчика Mini App **запрещено** — стережётся CI-чеком
`age_gate_before_pid`.

## 4. CSP Mini App

- `default-src 'self'` + явный белый список доменов;
- `unsafe-eval` запрещён;
- `frame-ancestors` — только домены Telegram;
- `report-uri` `/security/csp-report` — принимать CSP violation reports.

Плейсхолдер `{s3-domain-ru}` в CSP блокирует прод (E2 ERRATA, Boot-gate раздел 6).

## 5. Клиентский стек

- `@telegram-apps/sdk` (v3+) — актуальный SDK для инициализации, viewport, back button.
- Для стабильного нижнего UI использовать `viewportStableHeight`, не `viewportHeight`.
- Тему брать из real-time theme data Telegram (не хардкодить цвета).

## 6. Загрузка файлов из Mini App

Если Mini App отдаёт файлы через web-клиент Telegram:

- заголовок `Content-Disposition: attachment; filename="…"`;
- `Access-Control-Allow-Origin: https://web.telegram.org`;
- имя файла проходит sanitize (защита от path traversal).

## 7. Bot API — совместимость

Bot API 10.1 (июнь 2026) добавил `chat_join_request_query_id` в `WebAppInitData`.
Валидатор initData должен быть строгим по безопасности, но **устойчивым** к появлению
новых необязательных полей.

## 8. Admin-команды (Б17)

- Все 35 admin-команд — только из whitelist владельцев (Owner).
- Необратимые команды — двухшаг + `hard_confirm_phrase` (E3 ERRATA).
- Команды через Mini App командной палитрой — только для Owner-роли.

## 9. Что блокирует прод-запуск

- `initData` не валидируется на сервере — блокер.
- Не проверяется свежесть `auth_date` — блокер.
- CSP не оформлен или содержит плейсхолдер `{s3-domain-ru}` — блокер (E2 ERRATA).
- В `miniapp-api-contract.yaml` есть `TODO` на security-эндпоинтах — блокер.
- Ни одна из 3-х несовместимостей Б17 не решена Автором — блокер (см. `normative/README.md`).

## Связанные файлы

- [DIVISION.md](DIVISION.md) — разделение реализации.
- [build-order.md](build-order.md) — порядок сборки.
- [miniapp-api-contract.yaml](miniapp-api-contract.yaml) — OpenAPI 3.1 контракт.
- [ci-checks.yaml](ci-checks.yaml) — CI-чеки.
- [../normative/errata-unified.md](../normative/errata-unified.md) — E2 CSP, E3 hard-confirm.
- [../normative/seam-patch-1-onboarding.md](../normative/seam-patch-1-onboarding.md) — SEAM-1.
