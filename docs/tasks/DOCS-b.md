# DOCS-b — DOCS: CSP в build-файлах = E2 `csp_final` (course-bot D-2)

## 1. Паспорт
- id: DOCS-b. Репо: **DOCS-course-bot**. Ветка DOCS: `agent/miniapp-csp-e2`.
- Заголовок PR: `[Mini App]: CSP в build-файлах = ERRATA E2 csp_final (course-bot D-2)`
- Режим: Р0 «Сайт», 2 файла. КОДЕР не нужен. Зависит от: нет.
  DOCS-c правит тот же контракт → DOCS-c начинать только после мержа DOCS-b.
- Номер: «course-bot D-2» (в DOCS D-02 — другой дефект).

## 2. Цель
Две build-редакции CSP расходятся с ERRATA E2 (высшая ступень). Привести обе дословно к E2.
`normative/errata-unified.md` не трогаем: он и есть источник.

## 3. Решения Автора (дословно)
- course-bot D-2: «выравнивать CSP в DOCS-course-bot, не здесь. В `apps/miniapp/nginx.conf` остаётся редакция E2.»
- З2: 5А — «В DOCS пишем ровно E2» (font-src / base-uri / form-action / object-src в build-файлы
  не добавлять; `font-src 'self' data:` → запись course-bot D-20, код не трогать).

## 4. Выдержка архитектуры (источник значений)
`architecture/normative/errata-unified.md`, YAML, `E2_csp_default_src.csp_final` (дословно):

    default-src: "'self'"
    script-src: "'self' https://telegram.org"      # официальный telegram-web-app.js (Б14 R372)
    img-src: "'self' https://{s3-domain-ru} data: blob:"   # галереи фото
    connect-src: "'self' https://{s3-domain-ru}"   # API + pre-signed S3 РФ
    style-src: "'self' 'unsafe-inline'"
    frame-ancestors: "https://web.telegram.org https://telegram.org"
    forbidden: [unsafe-eval]
    report-uri: /security/csp-report

Плейсхолдер-шлюз (тот же файл): «CSP не проходит валидацию, пока плейсхолдер не заменён».
«Было» — дословно из зеркала 4cae002 (оно совпадает с DOCS main).

## 5. ЧТО ПРОЧИТАТЬ
КОДЕРа нет. Ctrl+F. `architecture/build/miniapp-frontend-stack.md` (около 6 КБ),
`architecture/build/miniapp-api-contract.yaml` (около 10 КБ). Чтение КОДЕРА: 0 КБ.

## 6. Правки

**Файл 1: `architecture/build/miniapp-frontend-stack.md`**, раздел «CSP-заголовок (E2 ERRATA)».

Правка 1.1 — 7 строк ВНУТРИ блока кода. Строки-ограждения (три обратные кавычки) над
и под блоком НЕ трогать. Было:

    default-src 'self';
    script-src 'self';
    style-src 'self' 'unsafe-inline';
    connect-src 'self' https://api.telegram.org;
    img-src 'self' data: blob: <s3-domain-ru>;
    frame-ancestors https://web.telegram.org https://t.me;
    report-uri /security/csp-report;

Станет:

    default-src 'self';
    script-src 'self' https://telegram.org;
    img-src 'self' https://{s3-domain-ru} data: blob:;
    connect-src 'self' https://{s3-domain-ru};
    style-src 'self' 'unsafe-inline';
    frame-ancestors https://web.telegram.org https://telegram.org;
    report-uri /security/csp-report;

Правка 1.2 — строка сразу под блоком. Было:

    `unsafe-eval` **запрещён**. `<s3-domain-ru>` заменяется на реальный домен после решения Автора (Boot-gate).

Станет:

    `unsafe-eval` **запрещён**. Значения — дословно E2 `csp_final` ([../normative/errata-unified.md](../normative/errata-unified.md)). `{s3-domain-ru}` — плейсхолдер-шлюз: заменяется на реальный домен после решения Автора (Boot-gate); пока не заменён, CSP не проходит валидацию.

**Файл 2: `architecture/build/miniapp-api-contract.yaml`**, самый конец файла (комментарий).

Правка 2.1. Было (8 строк):

    # csp_header:
    #   default-src 'self';
    #   script-src 'self';
    #   style-src 'self' 'unsafe-inline';
    #   connect-src 'self' https://api.telegram.org;
    #   img-src 'self' data: blob: <s3-domain-ru>;
    #   frame-ancestors https://web.telegram.org https://t.me;
    #   report-uri /security/csp-report;

Станет (10 строк; строку «# ---- CSP-заголовок (E2 ERRATA) ----» над ними не трогать):

    # Источник: normative/errata-unified.md → E2_csp_default_src.csp_final (дословно).
    # csp_header:
    #   default-src 'self';
    #   script-src 'self' https://telegram.org;
    #   img-src 'self' https://{s3-domain-ru} data: blob:;
    #   connect-src 'self' https://{s3-domain-ru};
    #   style-src 'self' 'unsafe-inline';
    #   frame-ancestors https://web.telegram.org https://telegram.org;
    #   report-uri /security/csp-report;
    #   unsafe-eval запрещён (INV-B14-CSP-STRICT).

## 7. Контракт: эндпоинты не меняются (правится только комментарий). ## 8. БД: нет.

## 9. Проверки
`tools/checks.sh` зелёный. Ссылка `../normative/errata-unified.md` существует (проверка 9/15 — битые ссылки).

## 10. Шаги Автора (сайт GitHub)
Шаг 1. Ты, браузер: открой
https://github.com/romanticstudent07-stack/DOCS-course-bot/blob/main/architecture/build/miniapp-frontend-stack.md
→ карандаш «Edit this file».
Шаг 2. Там же: Ctrl+F → `script-src 'self';` → выдели 7 строк «было» правки 1.1 (клик в начало
`default-src`, Shift+клик в конец `report-uri /security/csp-report;`) → Ctrl+V «станет».
Затем Ctrl+F → `заменяется на реальный домен` → выдели строку целиком → «станет» правки 1.2.
Шаг 3. «Commit changes» → `frontend-stack: CSP = E2 csp_final (course-bot D-2)` →
«Create a new branch for this commit and start a pull request» → ветка `agent/miniapp-csp-e2`
→ «Propose changes».
Шаг 4. Заголовок — из раздела 1, описание — блок ниже → «Create pull request».

    course-bot D-2 (запись course-bot docs/DEFECTS-ARCHIVE.md; в DOCS свой реестр D-01 – D-31).
    Читались: architecture/normative/errata-unified.md (E2), architecture/build/miniapp-frontend-stack.md,
    architecture/build/miniapp-api-contract.yaml.
    ERRATA: E2 csp_final — значения перенесены дословно; плейсхолдер-шлюз (раздел 6) — {s3-domain-ru} не подставлен.
    Было: script-src 'self', connect-src +api.telegram.org, frame-ancestors +t.me — расходилось с E2.
    Директивы сверх E2 не добавлены (решение Автора 5А).

Шаг 5. Ты, браузер: открой
https://github.com/romanticstudent07-stack/DOCS-course-bot/blob/agent/miniapp-csp-e2/architecture/build/miniapp-api-contract.yaml
→ карандаш → Ctrl+F `# csp_header:` → выдели 8 строк «было» правки 2.1 → Ctrl+V «станет».
Шаг 6. «Commit changes» → `contract: CSP-комментарий = E2 (course-bot D-2)` →
«Commit directly to the agent/miniapp-csp-e2 branch» → «Commit changes».
Шаг 7. `tools/checks.sh` зелёный (красный → «Details» → 60 строк лога → ШТАБ).
Шаг 8. `<адрес PR>.diff` → Ctrl+A, Ctrl+C → в ШТАБ.
Шаг 9. После «ок» ШТАБа: «Merge pull request» → «Create a merge commit» → «Confirm merge» →
«Delete branch» (безопасно: правки в main). Номер PR — в ШТАБ.

## 11. Запреты
Не трогать `normative/**`, раздел «Аутентификация» (TTL — course-bot D-9), пути контракта.
`{s3-domain-ru}` не заменять доменом.

## 12. Критерии готовности
Смержен; в обоих build-файлах 7 директив = E2; `t.me` и `api.telegram.org` в CSP больше нет.

## 13. Оценка: около 0,2 ч, 0 кредитов. ## 14. РЕВЬЮЕР: нет.
