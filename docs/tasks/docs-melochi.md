# docs-melochi — устаревшие тексты: config.py бота, AGENT-BRIEF, даты MinIO, клонирование

## 1. Паспорт
- id: docs-melochi · режим: Р0 (Автор правит на сайте GitHub, КОДЕРА нет) · зависит от: нет.
- Только комментарии и документация: код, значения .env.example и compose не меняются.
- 3 PR по правилу Р0 (1–3 файла):
  - PR-а, ветка `docs/melochi-a`, заголовок `docs: config.py бота и AGENT-BRIEF (env_file, 0006, expected_tables, exec)` —
    `apps/bot/bot/config.py`, `AGENT-BRIEF.md`.
  - PR-б, ветка `docs/melochi-b`, заголовок `docs: MinIO — точные даты; клонирование по SSH` —
    `AGENTS.md`, `infra/README.md`, `README.md`.
  - PR-в, ветка `docs/melochi-c`, заголовок `docs: MinIO — точные даты в .env.example и SERVER-IRONCLAD` —
    `.env.example` (только строка комментария), `infra/SERVER-IRONCLAD.md`.

## 2. Цель
Убрать устаревшие и неверные факты: env_file у бота, миграции и блокеры в AGENT-BRIEF, ошибочную
дату MinIO «сентябрь 2026» (5 мест), разный способ клонирования в README и infra/README.

## 3. Решения Автора (14.10, пачка miniapp-fix)
- MinIO (проверено ШТАБом): «В октябре 2025 MinIO перестал выпускать бесплатные Docker-образы и
  бинарники community-версии (только исходники; issue minio/minio #21647). 25.04.2026 репозиторий
  minio/minio архивирован.» Утверждение «maintenance mode с декабря 2025» — убрать (не проверено).
- Клонирование — Б: в обоих файлах SSH с deploy-ключом + заметка «пока репо публичный (до 0-Б),
  можно и HTTPS»; в infra/README.md одна строка «если сервер клонирован по HTTPS — сменить remote на SSH».
- AGENT-BRIEF, разделы 6 и 9 — только факты из STATE@2782ac3.

## 4. Выдержки
- STATE@2782ac3: «alembic 0006_app_roles, 13 таблиц»; «env_file нет ни у одного сервиса»;
  «B-1, B-2 и B-3 закрыты (B-3 — роли/GRANT БД, D-13, 14.10)».
- CODER.md@2782ac3: «Миграция добавляет или удаляет таблицы → в пакет apps/api/tests/expected_tables.txt
  целиком»; «Новый файл *.sh → chmod +x <файл> (check.sh проверит)»; check.sh — «+ проверки eol и exec».

## 5. ЧТО ПРОЧИТАТЬ
Ничего: в каждом файле найти строку «Было» через Ctrl+F и заменить на «Стало» (раздел 7).
Строки в блоках ниже — с отступом 4 пробела только для показа; в файле отступ как в «Было».

## 6. Файлы
Изменить: apps/bot/bot/config.py, AGENT-BRIEF.md, AGENTS.md, infra/README.md, README.md,
.env.example, infra/SERVER-IRONCLAD.md. Создать и удалить: нет.

## 7. Правки «было → стало»
PR-а, `apps/bot/bot/config.py` (docstring, строка 3). Было:
    Секреты и адреса — только из окружения (compose: env_file ../.env). Хардкодов нет.
Стало (2 строки):
    Секреты и адреса — только из окружения: compose передаёт боту переменные явно
    (environment в infra/docker-compose.dev.yml; env_file у бота нет с #71). Хардкодов нет.
PR-а, `AGENT-BRIEF.md`:
1) Строка 3. Было `Версия 2 · 27.09.2026.` Стало `Версия 2.1 · ДД.ММ.2026.` (дата дня правки).
2) Раздел 6. Было:
    - Миграции: `0001_init`, `0002_tg_user_registry`. Таблиц в public (без alembic_version): 9.
   Стало:
    - Миграции: от `0001_init` до `0006_app_roles` (последняя — в `docs/STATE.md`).
      Таблиц в public (без alembic_version): 13; полный список — `apps/api/tests/expected_tables.txt`.
3) Раздел 9, последняя строка. Было:
    Блокеры до любого внешнего доступа: B-1 rate-limit, B-2 согласия до создания pid, B-3 роли/GRANT БД.
   Стало:
    Блокеры B-1 (rate-limit), B-2 (согласия до создания pid) и B-3 (роли/GRANT БД) закрыты
    (B-3 — 14.10.2026; подробности — `docs/STATE.md`).
4) Раздел 11: после строки `- Скрипт отклонил пакет → не обходить, описать ошибку Автору.` вставить:
    - Миграция добавляет или удаляет таблицы → в том же PR `apps/api/tests/expected_tables.txt`
      с полным новым списком таблиц (по нему CI сверяет БД; ci.yml не трогать).
    - Новый `*.sh` → `chmod +x <файл>` до коммита: `tools/check.sh` проверяет бит exec и окончания строк LF.
PR-б, `AGENTS.md`, запрет 11. Было:
    11. **Не возвращаться к MinIO** — Docker-образы удалены в сентябре 2026,
        репо архивирован. Используем Garage (`dxflrs/garage`) как S3 в dev.
Стало:
    11. **Не возвращаться к MinIO** — с октября 2025 бесплатных Docker-образов и бинарников
        community-версии нет (только исходники; issue minio/minio #21647), 25.04.2026 репозиторий
        minio/minio архивирован. Используем Garage (`dxflrs/garage`) как S3 в dev.
PR-б, `infra/README.md`:
1) Шапка. Было:
    (MinIO удалил официальные Docker-образы в сентябре 2026). Переезд на
   Стало:
    (в октябре 2025 MinIO перестал выпускать бесплатные Docker-образы и бинарники
    community-версии — только исходники, issue minio/minio #21647; 25.04.2026 репозиторий
    minio/minio архивирован). Переезд на
2) Шаг 4, в блоке команд. Было:
    # Репозиторий ПРИВАТНЫЙ — клон по HTTPS не сработает.
    # Клонируем через deploy-ключ с SSH-алиасом (настройка алиаса — в ~/.ssh/config).
   Стало:
    # Клонируем через deploy-ключ с SSH-алиасом (настройка алиаса — в ~/.ssh/config).
    # Пока репо публичный (до 0-Б), можно и HTTPS:
    #   git clone https://github.com/romanticstudent07-stack/course-bot.git
3) Шаг 4, текст под блоком. Было:
    Репозиторий приватный, поэтому клон возможен только по SSH с deploy-ключом.
   Стало:
    Основной способ — SSH с deploy-ключом: он работает и после 0-Б, когда репо станет приватным.
    Пока репо публичный (до 0-Б), можно клонировать и по HTTPS. Если сервер клонирован по HTTPS —
    на 0-Б сменить remote: `git remote set-url origin git@github-coursebot:romanticstudent07-stack/course-bot.git`.
PR-б, `README.md`, раздел «Клонирование». Было:
    git clone https://github.com/romanticstudent07-stack/course-bot.git
Стало:
    # Основной способ — SSH с deploy-ключом (алиас в ~/.ssh/config, см. infra/README.md, шаг 4).
    git clone git@github-coursebot:romanticstudent07-stack/course-bot.git
    # Пока репо публичный (до 0-Б), можно и HTTPS:
    # git clone https://github.com/romanticstudent07-stack/course-bot.git
PR-в, `.env.example` — ТОЛЬКО эта строка комментария. Было:
    # MinIO удалил официальные Docker-образы в сентябре 2026, заменён на Garage.
Стало:
    # MinIO: с октября 2025 бесплатных Docker-образов нет (только исходники), 25.04.2026 репо архивирован; заменён на Garage.
PR-в, `infra/SERVER-IRONCLAD.md`:
1) Раздел «S3-совместимое хранилище». Было:
    Заменил MinIO (MinIO удалил официальные Docker-образы в сентябре 2026,
    проект в maintenance mode с декабря 2025).
   Стало:
    Заменил MinIO (в октябре 2025 MinIO перестал выпускать бесплатные Docker-образы
    и бинарники community-версии — только исходники, issue minio/minio #21647;
    25.04.2026 репозиторий minio/minio архивирован).
2) Раздел «Стоп-факторы». Было:
    - **MinIO deprecated** — не пробовать вернуть, репо архивирован Apr 2026,
      Docker-образы удалены Sep 2026. Мы на Garage.
   Стало:
    - **MinIO deprecated** — не пробовать вернуть: бесплатных Docker-образов нет с октября 2025,
      репозиторий архивирован 25.04.2026. Мы на Garage.

## 8. БД
Нет.

## 9. Тесты
check.sh не нужен (сайт). CI 7/7 на каждом PR (job bot — после правки docstring config.py).

## 10. Живые проверки (после мержа каждого PR)
- СЕРВЕРНЫЙ: только `cd ~/course-bot && git pull origin main`. Пересборок нет: config.py — только
  docstring, остальное — документы. .env на сервере не трогать.
- После PR-в: строки не-комментариев в .env.example не изменились (ожидание `0`):
      git diff HEAD@{1} HEAD -- .env.example | grep -E '^[+-]' | grep -vE '^(\+\+\+|---)' | grep -vE '^[+-]#' | wc -l

## 11. Запреты
- AGENT-BRIEF.md, раздел 3. Не трогать docs/architecture/**, .github/**, .env.
- В .env.example — только одна строка комментария; переменные и значения не менять.
- Реальные адреса, IP, ID и алиасы Автора (кроме шаблона `github-coursebot`, уже в репо) не вписывать.
- Даты MinIO — только из раздела 3; других фактов не добавлять.

## 12. Критерии готовности
- 3 PR смержены, CI 7/7 у каждого; «сентябрь 2026» и «maintenance mode с декабря 2025» в 5 местах
  исправлены; README и infra/README клонируют одинаково (SSH + заметка HTTPS); проверка из раздела 10 = 0.

## 13. Оценка
Автор ~0,7 ч (сайт, 7 файлов в 3 PR); кредиты 0.

## 14. РЕВЬЮЕР
Нет: только тексты, безопасность не затронута.

## Как править на сайте (Автор)
Шаг 1. Ты, GitHub: открой файл → карандаш (Edit) → Ctrl+F «Было» → замени на «Стало».
Шаг 2. Commit changes → «Create a new branch» → имя ветки из раздела 1 → Propose changes.
Шаг 3. Второй и третий файл того же PR: переключи ветку на эту же → правь → Commit прямо в неё.
Шаг 4. Create pull request; не мержить, пока ШТАБ не сверит.
