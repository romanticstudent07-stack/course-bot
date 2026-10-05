# projector-3 — сервис projector в docker-compose.dev.yml (7-й контейнер)

## 1. Паспорт
- id: projector-3 · PR: «projector-3: сервис projector в docker-compose.dev.yml» · ветка: feat/projector-3-compose
- Режим: Р0+ · зависит от: projector-2 (app/projector.py в образе api). Миграции нет. Начинать после мержа projector-2.
- Заменяет часть docs/tasks/projector.md (удалён в PR docs/tasks-projector). Дальше — miniapp-csp.
- Первый файл пакета — docs/STATE.md (строки от ШТАБа; строку «Память… 1664 МБ» ШТАБ даёт с 1792 МБ).

## 2. Цель
Проектор работает постоянно отдельным контейнером рядом с api. Сумма лимитов памяти 1664 → 1792 МБ (≤ 2 ГБ).

## 3. Решения Автора (дословно)
- STATE: «Память: сумма лимитов ≤ 2 ГБ».
- Карточка projector, раздел 7: «Compose: сервис projector — образ api, command python -m app.projector run, тот же
  env_file, depends_on db (healthy), restart unless-stopped, mem_limit 128m (сумма 1664 → 1792 МБ ≤ 2 ГБ),
  healthcheck: disable: true (HEALTHCHECK Dockerfile api стучится на /healthz — у проектора его нет).»
- ШТАБ (04.10): лимит — в стиле файла: ${MEM_LIMIT_PROJECTOR:-128M} + переменная в .env.example.

## 4. Выдержки (a4c5e29)
- compose: у сервисов лимит — deploy.resources.limits.memory: ${MEM_LIMIT_<СЕРВИС>:-…}; networks: [course-bot_net];
  container_name course-bot_<имя>; порты — только 127.0.0.1; name: course-bot.
- apps/api/Dockerfile: HEALTHCHECK curl http://127.0.0.1:8080/healthz; CMD uvicorn — у проектора HTTP нет.
- .env.example: «Суммарно ≤ 2 GB (решение Автора 25.09.2026; было 1.5 GB). Сейчас сумма лимитов 1664 МБ.»;
  MEM_LIMIT_API … MEM_LIMIT_MINIAPP=128M.
- projector-2: run — цикл 1 с; сбой БД → WARNING, пауза 5 с, повтор (контейнер не падает).

## 5. ЧТО ПРОЧИТАТЬ (размеры по a4c5e29)
docs/process/CODER.md 11,1 КБ; AGENT-BRIEF.md 11,2; docs/STATE.md ≈ 10; эта карточка ≈ 5;
infra/docker-compose.dev.yml 7,5; .env.example 8,4. **Чтение КОДЕРА ≈ 53 КБ.**
Не читать: apps/api/** (факты в разделе 4), Dockerfile, docs/DEFECTS-*.md.

## 6. Файлы (2 + STATE)
Изменить: infra/docker-compose.dev.yml (сервис projector); .env.example (MEM_LIMIT_PROJECTOR, сумма 1792 МБ).

## 7. Контракт
Сервис projector (после api; комментарий над ним — E1: единственный писатель participant_state; образ api):
    projector:
      build: { context: ../apps/api }   # тот же образ, что у api (как в сервисе api этого файла)
      container_name: course-bot_projector
      command: ["python", "-m", "app.projector", "run"]
      env_file: [../.env]              # как у api
      environment: { TZ: ${TZ} }
      depends_on: { db: { condition: service_healthy } }
      restart: unless-stopped
      healthcheck: { disable: true }   # HEALTHCHECK Dockerfile api стучится на /healthz — у проектора его нет
      networks: [course-bot_net]
      deploy: { resources: { limits: { memory: ${MEM_LIMIT_PROJECTOR:-128M} } } }
- build, env_file и путь — скопировать ровно как у сервиса api в этом файле (отличается — брать как у api, записать в PR).
- Портов нет (HTTP у проектора нет). Формат YAML — блочный, как в файле (фигурные скобки выше — только для краткости карточки).
- .env.example: MEM_LIMIT_PROJECTOR=128M после MEM_LIMIT_MINIAPP; «Сейчас сумма лимитов 1664 МБ» → «1792 МБ».

## 8. БД: нет.

## 9. Тесты
Кода нет. Цели check.sh: api (быстро; eol). CI: docker-сборки 7/7. Локально: docker compose -f infra/docker-compose.dev.yml config -q (если docker есть в Codespaces; нет — пропустить, записать в PR).

## 10. Живые проверки (после мержа; СЕРВЕРНЫЙ)
1. pull → в .env сервера добавить MEM_LIMIT_PROJECTOR=128M (или оставить умолчание) → up -d --build projector.
2. 7/7 Up (добавился projector), 4 healthy → logs projector --since 10m без ERROR.
3. Автор: закрыть и открыть Mini App → повторный first-launch → 201 тот же pid; SELECT count(*) FROM participant_events →
   по-прежнему N; SELECT lifecycle_phase, count(*) FROM participant_state GROUP BY 1 → onboarding | N (без pid).
4. docker stats --no-stream course-bot_projector → память заметно ниже 128 МБ.

## 11. Запреты
AGENT-BRIEF §3. Плюс: другие сервисы compose не менять; портов проектору не давать; .env не трогать (только .env.example);
apps/** не менять; docs/DEFECTS-*.md не читать и не править.

## 12. Готово, когда
CI 7/7; сервер 1–4. После — ШТАБ даёт карточку DOCS (D-16 + D-21) после miniapp-csp.

## 13. Оценка
Часы Автора ~0,5; запросов КОДЕРА 1–2; кредиты 0 (Р0+).

## 14. РЕВЬЮЕР: нет
Только запуск уже проверенного кода отдельным контейнером; initData, 18+, согласий, rate-limit, ролей/GRANT, оплаты нет.
