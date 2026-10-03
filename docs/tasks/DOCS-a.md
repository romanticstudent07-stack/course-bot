# DOCS-a — DOCS: Menu Button / BotFather и MinIO → Garage (course-bot D-8, D-3)

## 1. Паспорт
- id: DOCS-a. Репо: **DOCS-course-bot** (не course-bot).
- Ветка DOCS: `agent/bot-botfather-garage` (формат веток DOCS: `.genspark/rules.md`).
- Заголовок PR: `[Bot]: Menu Button через Bot API, BotFather, MinIO → Garage (course-bot D-8, D-3)`
- Режим: Р0 «Сайт» (веб-редактор GitHub), 2 файла. КОДЕР не нужен. Зависит от: нет.
- Номера: в DOCS свой реестр D-01 – D-31 (`architecture/appendix/D-source-defects.md`).
  В PR и коммитах писать только «course-bot D-8», «course-bot D-3».

## 2. Цель
Убрать из зеркала ручную настройку Mini App в BotFather (course-bot D-8) и остатки
MinIO (course-bot D-3). Вход через Cloudflare Tunnel не трогаем: это course-bot D-5, ждёт решения Автора.

## 3. Решения Автора (дословно)
- course-bot D-8, «Предлагаемое решение» (DEFECTS-ARCHIVE.md): «править в DOCS-course-bot
  (`build/DIVISION.md`, `build/build-order.md`): Menu Button — через Bot API из `WEBAPP_URL`;
  `/setdomain` — только для Login Widget; `/newapp` — только для прямой ссылки.»
- course-bot D-3, «Статус»: «MinIO в зеркале (`build/build-order.md`: Итерация 0-А, `minio`,
  `minio-init`, состав `docker-compose.yaml`) — править в DOCS-course-bot.»
- З2: 2А (Р0 «Сайт»), 3А (только MinIO, Cloudflare не трогать), 4А (без версии: `dxflrs/garage`),
  9А (текст «URL Mini App (`WEBAPP_URL` в course-bot)»; `MINIAPP_URL` не переименовывать — course-bot D-21).

## 4. Источник «было»
Зеркало course-bot на 4cae002 совпадает с DOCS main: последний запуск sync-architecture
зелёный, нового PR нет. Все строки «было» ниже взяты дословно из этого зеркала.
Не нашлась строка через Ctrl+F → стоп, сообщить ШТАБу (значит, DOCS менялся).

## 5. ЧТО ПРОЧИТАТЬ
КОДЕРа нет. Автор ищет строки через Ctrl+F. Размеры: `architecture/build/DIVISION.md` 11,7 КБ,
`architecture/build/build-order.md` около 14 КБ (ПРОЕКТИРОВЩИК прочитал целиком). Чтение КОДЕРА: 0 КБ.

## 6. Правки (файл → место → было → станет)
Каждое «было» — строка целиком. Её выделяют и заменяют текстом «станет».

**Файл 1: `architecture/build/DIVISION.md`**

Правка 1.1 — раздел «Принцип разделения», блок **Bot**, первый пункт. Было:

    - Меню-кнопка → открытие Mini App (`WebAppInfo`, `/setmenubutton`).

Станет:

    - Меню-кнопка → открытие Mini App (`WebAppInfo`): бот ставит её сам при старте через Bot API (`setChatMenuButton`) из URL Mini App (`WEBAPP_URL` в course-bot); `/setmenubutton` в BotFather не нужен.

Правка 1.2 — раздел «Что реализуется в боте приоритетно», п.1. Было:

    1. **Menu Button → Mini App URL** (`/setmenubutton` в BotFather).

Станет:

    1. **Menu Button → Mini App URL** (бот ставит через Bot API `setChatMenuButton` из `WEBAPP_URL`; BotFather не нужен).

**Файл 2: `architecture/build/build-order.md`**

Правка 2.1 — «Локальный старт на сервере Автора (IRONCLAD)», пункт «Итерация 0-А». Было:

    - **Итерация 0-А (локальная инфра)** — Postgres 16 / Redis 7 / MinIO (S3-совместимый)

Станет (следующую строку про Cloudflare Tunnel НЕ трогать):

    - **Итерация 0-А (локальная инфра)** — Postgres 16 / Redis 7 / Garage (S3-совместимый, образ `dxflrs/garage`)

Правка 2.2 — «Итерация 0-А», шаг 2. Было:

    2. Telegram Bot регистрация в BotFather: `/newbot`, `/newapp` (домен привяжется после туннеля).

Станет:

    2. Telegram Bot регистрация в BotFather: `/newbot`. `/newapp` — только если нужна прямая ссылка вида `t.me/<бот>/<app>`; `/setdomain` — настройка Telegram Login Widget, для Mini App не нужна.

Правка 2.3 — «Итерация 0-А», шаг 7, ПЕРВАЯ строка (вторую «позже `api`, `bot`.» не трогать). Было:

    7. `infra/docker-compose.dev.yml` — сервисы `db`, `redis`, `minio`, `minio-init`,

Станет:

    7. `infra/docker-compose.dev.yml` — сервисы `db`, `redis`, `garage` (первый бакет создаётся при старте, init-контейнер не нужен),

Правка 2.4 — «Итерация 0-Б», шаг 2. Было:

    2. Telegram Bot регистрация в BotFather: `/newbot`, `/newapp`, `/setmenubutton https://<s3-domain-ru>/`, `/setdomain`.

Станет:

    2. Telegram Bot регистрация в BotFather: `/newbot`. Menu Button бот ставит сам через Bot API из URL Mini App (`WEBAPP_URL` в course-bot) — `/setmenubutton` не нужен; `/newapp` — только для прямой ссылки `t.me/<бот>/<app>`; `/setdomain` — только для Login Widget.

Правка 2.5 — «Состав `docker-compose.yaml` (минимум)», третий пункт. Было:

    - `minio` (S3-mock для синтетики).

Станет:

    - `garage` (S3-совместимое хранилище для синтетики, образ `dxflrs/garage`; версия — в compose репо реализации).

Не трогать: шаги 1, 3 и 8 Итерации 0-А (Cloudflare — course-bot D-5); список переменных (`MINIAPP_URL` — course-bot D-21).

## 7. Контракт: не меняется. ## 8. БД: нет.

## 9. Проверки
CI DOCS `architecture-checks` → job `tools/checks.sh` (15 grep-проверок) должен быть зелёным.
В новых строках нет слов, на которые реагируют проверки (`/place`, `banned_`, старшинство, WIP).

## 10. Шаги Автора (сайт GitHub, вход под своим аккаунтом)
Шаг 1. Ты, браузер: открой
https://github.com/romanticstudent07-stack/DOCS-course-bot/blob/main/architecture/build/DIVISION.md
→ значок карандаша «Edit this file» (откроется редактор).
Шаг 2. Там же: щёлкни в текст → Ctrl+F → вставь «было» из правки 1.1 → Enter. Найденную строку
выдели целиком (клик в начало, Shift+клик в конец) → Ctrl+V текст «станет». Так же — правка 1.2.
Шаг 3. Там же: зелёная кнопка «Commit changes» → Commit message:
`DIVISION: Menu Button через Bot API (course-bot D-8)` → выбери «Create a new branch for this
commit and start a pull request» → имя ветки `agent/bot-botfather-garage` → «Propose changes».
Шаг 4. Откроется «Open a pull request»: заголовок — из раздела 1, описание — блок ниже →
«Create pull request». PR (pull request — заявка влить ветку в main) создан.

    course-bot D-8, D-3 (записи course-bot docs/DEFECTS-ARCHIVE.md; в DOCS свой реестр D-01 – D-31).
    Читались: architecture/build/DIVISION.md, architecture/build/build-order.md.
    ERRATA: не применялись (правка build-файлов; нормативный стек не тронут).
    Menu Button ставит бот через Bot API (setChatMenuButton) из URL Mini App (WEBAPP_URL в course-bot):
    /setmenubutton не нужен; /setdomain — только Login Widget; /newapp — только прямая ссылка.
    MinIO / minio-init → Garage (dxflrs/garage); версия образа — в compose course-bot.
    Не тронуто: Cloudflare Tunnel (course-bot D-5), MINIAPP_URL (course-bot D-21).

Шаг 5. Ты, браузер: открой (файл уже в ветке)
https://github.com/romanticstudent07-stack/DOCS-course-bot/blob/agent/bot-botfather-garage/architecture/build/build-order.md
→ карандаш → правки 2.1–2.5 так же, как в шаге 2. Две строки «2. Telegram Bot регистрация»
различаются концом: ищи «было» целиком.
Шаг 6. «Commit changes» → `build-order: BotFather, MinIO → Garage (course-bot D-8, D-3)` →
«Commit directly to the agent/bot-botfather-garage branch» → «Commit changes».
Шаг 7. В PR внизу: проверка `tools/checks.sh` зелёная. Красная → «Details» → последние 60 строк
лога → в ШТАБ.
Шаг 8. Добавь к адресу PR `.diff` (пример: `.../pull/5.diff`) → Ctrl+A, Ctrl+C → вставь в ШТАБ.
ШТАБ сверяет текст с этой карточкой: DOCS приватный, сам ШТАБ его прочитать не может.
Шаг 9. После «ок» ШТАБа: «Merge pull request» → «Create a merge commit» → «Confirm merge» →
«Delete branch» (это безопасно: правки уже в main). Номер PR — в ШТАБ.

## 11. Запреты
Править только 7 строк выше. Не трогать `architecture/normative/**`, Cloudflare, список переменных.
Не коммитить напрямую в main. Тексты курса — нет.

## 12. Критерии готовности
PR в DOCS смержен; `tools/checks.sh` зелёный; diff = ровно 2 строки в DIVISION.md и 5 в build-order.md.

## 13. Оценка: около 0,3 ч Автора, 0 кредитов. ## 14. РЕВЬЮЕР: нет.
