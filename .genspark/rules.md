# .genspark/rules.md — правила для Genspark Code Agent

## Активация git-хуков перед работой (одноразово)

Сразу после клона репо в sandbox Genspark выполни:

```bash
git config core.hooksPath .githooks
chmod +x .githooks/pre-commit
```

Без этого локальный хук `.githooks/pre-commit` не работает,
и защита от случайного коммита в `docs/architecture/**` и `.env` неактивна.

## Обязательный порядок чтения перед началом любой задачи

1. `CONTEXT.md`
2. `AGENTS.md`
3. `docs/architecture/AGENTS.source.md` (наследуемые правила из DOCS-course-bot)
4. `docs/architecture/CANONICAL-SOURCES.md`
5. `docs/architecture/normative/README.md`
6. `docs/architecture/normative/OVERRIDES.yaml`
7. `docs/architecture/build/DIVISION.md`
8. `docs/architecture/build/build-order.md`
9. `infra/SERVER-IRONCLAD.md`

Не начинать реализацию, пока не прочитаны все девять.

## Жёсткие запреты

- **НЕ править `docs/architecture/**`** — это read-only зеркало из DOCS-course-bot.
- **НЕ создавать код в состояниях `banned_soft`/`banned_hard`** — их не существует.
- **НЕ помещать секреты в код** (`BOT_TOKEN`, PSP-ключи, `initData secret`).
- **НЕ переносить Панель Автора (Блок 17) в Mini App** — только в боте.
- **НЕ пушить в `main` напрямую** — только через PR.
- **НЕ угадывать значения открытых решений Автора** —
  задавать вопрос в конце PR-описания.
- **НЕ встраивать платёжные экраны внутрь Mini App** — оплата пока только
  на внешней ссылке YooKassa / на карту, вне Telegram.

## Открытые решения Автора (агент их не решает)

1. Облачный провайдер prod (Yandex Cloud vs Timeweb).
2. Значение `full_backup_rotation_cycle`.
3. Три несовместимости Б17.
4. Роли `finance` и `moderator`.

## Формат PR

- Одна задача — один PR.
- Заголовок PR: «Блок N: короткое описание».
- В описании PR обязательно указать:
  - какие файлы `docs/architecture/**` прочитаны;
  - какие правила ERRATA/OVERRIDES применены;
  - какие вопросы к Автору остались (если есть).

## Валидация initData (шпаргалка)

```
secret_key = HMAC-SHA256(key="WebAppData", msg=BOT_TOKEN)
data_check_string = сортированные пары key=value (без hash), через "\n"
expected_hash = HMAC-SHA256(key=secret_key, msg=data_check_string)
```

TTL `auth_date`: 24 часа. Для `/refund` и `/erasure_*` — 1 час.

Никогда не доверять `initDataUnsafe` на клиенте.

## Разработка на локальном сервере

Сейчас backend разрабатывается и тестируется на локальном Linux-сервере Автора
(IRONCLAD). Бот — на long polling, публичный webhook не ставится (D-4).
Вход в Mini App: dev — Tailscale serve (только tailnet, только Автор),
прод / внешние тестировщики — позже через российский VPS (решение Автора).
Cloudflare Tunnel не используется. Все URL, порты и хосты берутся из `.env`
(см. `.env.example`), никогда не хардкодятся в коде.

Внутри compose-сети хосты для api/bot:
- Postgres: `db:5432`
- Redis: `redis:6379`
- Garage (S3 API): `garage:3900`

С хоста (для psql, DBeaver, curl):
- Postgres: `127.0.0.1:5435`
- Redis: `127.0.0.1:6382`
- Garage (S3 API): `127.0.0.1:9000` (`127.0.0.1:9001` — `s3_web`, не админка)

Тесты запускаются локально: `pytest`, `vitest`, `docker compose up`.
Перед PR все тесты должны пройти.
