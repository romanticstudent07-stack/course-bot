# AGENTS.md — DOCS-course-bot

Этот файл читается AI-агентами (Genspark, Claude Code, Cursor, OpenAI Codex).
Формат — [agents.md](https://agents.md/), рекомендации 2026 г.

## Природа репозитория

**DOCS-course-bot — это репозиторий-документация.** В нём не хранится код. Здесь **источник истины** для проекта Telegram-курс-бота: архитектура, нормативный стек, приложения, дефекты источника.

Код реализации живёт в отдельном репозитории **`romanticstudent07-stack/course-bot`** (Mini App + бот + backend). При работе агент над кодом → работать в `course-bot`, читая архитектуру отсюда.

## Ключевые точки входа

1. **[architecture/README.md](architecture/README.md)** — рабочий каталог, реестр 1.10, нормативный стек.
2. **[architecture/normative/README.md](architecture/normative/README.md)** — старшинство патчей И1–И4, Б17, ERRATA, SEAM-PATCH-1.
3. **[architecture/build/DIVISION.md](architecture/build/DIVISION.md)** — что реализуется в Mini App, что в боте, что в backend.
4. **[architecture/normative/OVERRIDES.yaml](architecture/normative/OVERRIDES.yaml)** — машиночитаемые ERRATA-переопределения (E1, E2, E4, FIX1, R477_TARGET, N02). Держать в контексте при любой работе с патчами И1/И2/И3/И4/Б17. См. [OVERRIDES.md](architecture/normative/OVERRIDES.md) для навигации.
4. **[architecture/build/build-order.md](architecture/build/build-order.md)** — порядок первых итераций.
5. **[CONTEXT.md](CONTEXT.md)** — быстрый обзор.
6. **[architecture/CANONICAL-SOURCES.md](architecture/CANONICAL-SOURCES.md)** — правило «верхний файл vs подпапка» для блоков с нарезкой (`10/`, `15/`, `99/`).

## Правила старшинства (критично)

При расхождении между слоями побеждает верхний:

```
корпус v3 → И1 → И2 → И3 → И4 → Б17 → SEAM-PATCH-1 → ERRATA-UNIFIED (высшее)
```
Это **ось старшинства**. Не путать с хронологией присоединения (`… → Б17 → ERRATA-UNIFIED → SEAM-PATCH-1`), которая идёт в другом порядке: SEAM-PATCH-1 подшит последним, но сам объявил себя `below_errata_unified`. Разбор двух осей — в [architecture/normative/README.md](architecture/normative/README.md).

Не переписывать текст блоков корпуса. Правки идут:

- **v2.1 / v3.1** — только убавляющие;
- **И1–И4, Б17, SEAM, ERRATA** — добавляющие / переопределяющие / убавляющие.

## Что запрещено

1. **Не переписывать источник истины** (`architecture/`, `normative/`, `appendix/`) без явного указания Автора.
2. **Не удалять команду `/place` из истории** — она уже удалена поправкой v3.1, но фиксирована в `appendix/A-patch1-global-rules.md` как «P-6 удалён».
3. **Не создавать реализацию для состояний `banned_soft` / `banned_hard`** — они удалены Р477 (И2). Читать через `sleeping + author_pause + owner-review`.
4. **Не помещать секретные значения в код** (`bot_token`, PSP-ключи, `initData secret`) — только через переменные окружения.
5. **Не игнорировать `client_op_id`** при финансовых и state-меняющих операциях (идемпотентность).
6. **Не разрешать `unsafe-eval` в CSP** Mini App (E2 ERRATA).
7. **Не переносить Панель Автора (Блок 17) в Mini App** — по решению в `DIVISION.md`.

## Как валидировать `initData` (единственная критичная процедура безопасности)

Каждый запрос к `/miniapp/v1/**` содержит заголовок `X-Telegram-Init-Data`. Сервер:

1. `secret_key = HMAC-SHA256(key="WebAppData", msg=bot_token)`
2. Собрать `data_check_string`: пары `key=value` из initData (кроме `hash`), отсортированные по ключу, соединённые `\n`.
3. `expected_hash = HMAC-SHA256(key=secret_key, msg=data_check_string)`
4. Сравнить с `hash` из initData.
5. Проверить `auth_date` (TTL 24 ч; для `/refund`, `/erasure_*` — 1 ч).

Никогда не доверять `Telegram.WebApp.initDataUnsafe` — только серверная валидация.

## Стек по умолчанию (пока Автор не выбрал иное)

- **Mini App:** React 18 + Vite + TypeScript + `@telegram-apps/sdk-react` + Zustand + tanstack-query + dexie (IndexedDB).
- **Bot:** Python 3.12 + aiogram 3.
- **Backend:** FastAPI + PostgreSQL 16 + Redis 7 + Alembic.
- **Хостинг:** Yandex Cloud (или Timeweb «Облако 152-ФЗ»).

## Порядок работы агента

1. Открыть `CONTEXT.md`, потом `architecture/build/DIVISION.md`.
2. Найти блок, к которому относится задача.
3. Проверить нормативные наложения через врезки «Переопределено/Уточнено ERRATA-UNIFIED» в шапке файла блока.
4. Реализовать в соответствующем `apps/<layer>/`.
5. При обнаружении расхождения с корпусом — фиксировать в `architecture/appendix/D-source-defects.md`, а не править на месте.
6. Атомарные PR: одна задача — один PR. Заголовок PR = «Блок N: короткое описание».

## Тесты и CI

- CI-чеки — в `architecture/build/ci-checks.yaml` (50+). Пока живут как задел, реализуются по мере поднятия pipeline.
- Тесты Mini App — Vitest + React Testing Library.
- Тесты Bot — pytest + aiogram test framework.
- Тесты Backend — pytest + httpx.

## Как задавать вопросы Автору

Открытые вопросы, которые агент **не** должен решать сам:

- Выбор облачного провайдера (Yandex Cloud vs Timeweb).
- Выбор PSP (YooKassa vs CloudPayments vs Тинькофф Kassa).
- Значение `full_backup_rotation_cycle`.
- Три несовместимости Б17 (см. `normative/README.md`, «Открытые несовместимости»).
- Определение ролей `finance` и `moderator`.

При задачах, задевающих эти пункты, — вежливо вернуть вопрос Автору вместо угадывания.
