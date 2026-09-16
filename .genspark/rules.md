# .genspark/rules.md — правила для Genspark Code Agent

## Обязательный порядок чтения перед началом любой задачи

1. `CONTEXT.md`
2. `AGENTS.md`
3. `docs/architecture/AGENTS.md` (наследуемые правила)
4. `docs/architecture/CANONICAL-SOURCES.md`
5. `docs/architecture/normative/README.md`
6. `docs/architecture/normative/OVERRIDES.yaml`
7. `docs/architecture/build/DIVISION.md`
8. `docs/architecture/build/build-order.md`

Не начинать реализацию, пока не прочитаны все восемь.

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

Сейчас backend разрабатывается и тестируется на локальном Linux-сервере Автора.
Публичный HTTPS-webhook — через Cloudflare Tunnel. Все URL, порты и хосты
берутся из `.env` (см. `.env.example`), никогда не хардкодятся в коде.

Тесты запускаются локально: `pytest`, `vitest`, `docker compose up`.
Перед PR все тесты должны пройти.
