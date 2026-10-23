# api-access-1 — гейт first-launch по access_grants + status «no_access»

Пачка Р-2, карточка (в1) из 4. Начинать ПОСЛЕ мержа db-access-1. Параллельно с bot-access-1.
ВЫКАТ — только вместе с bot-access-1 или после него: иначе новые люди не войдут никак.

## 1. Цель
- Mini App не создаёт участника (pid), пока Автор не выдал доступ.
- POST first-launch без доступа → 403 ACCESS_NOT_GRANTED.
- GET status → 200 {"status":"no_access"}.
- Существующих участников гейт не трогает.

## 2. Решения (К-6)
- «Тот, кому доступ не выдан, … участником не становится» [STATE Р-2; R-2026-10-1 Р-2 п.8].
- 403 ACCESS_NOT_GRANTED на first-launch; status — 200 no_access, без 403 [Автор 23.10, ответ 6;
  D-22 а) — status без 403].
- Запрет «403 для неизвестного tg_user_id» (docstring, D-9 п.2) относился к R327; Р-2 его перекрывает
  [Автор 23.10, ответ 6].
- Гейт только на создание pid; активный участник проходит без проверки [Автор 23.10, ответ 5].
- Проверка — в транзакции first-launch, после возраста и согласий, до get_or_create [ШТАБ 23.10].
- Читать только колонку status явным select (у app_api права только на tg_user_id, status) [ШТАБ, по коду: db-access-1 §7].
- Тексты — заглушки [STATE: тексты курса — заглушки до 0-Б].

## 3. Ветка, коммит, PR
Ветка: feat/api-access-1. Коммит: «feat(api): гейт доступа first-launch + status no_access (api-access-1)».
PR: «api-access-1: first-launch без доступа → 403, status no_access (Р-2)».

## 4. Что прочитать (≈ 130 КБ)
AGENT-BRIEF.md 17,1 · docs/STATE.md 20,6 · эта карточка ≈ 8 · apps/api/app/routers/onboarding.py 20,3 ·
apps/api/app/participants.py (find_active_participant, get_or_create_participant) ·
apps/api/app/db/models.py 11,2 (AccessGrant из db-access-1) · apps/api/tests/conftest.py 6,0 ·
apps/api/tests/test_first_launch.py 24,7 ·
apps/api/tests/test_db_roles_0009.py 13,8 (только как переключать роль в тесте) ·
тест status — найти одной командой
    grep -l "onboarding/status" apps/api/tests/*.py
и прочитать найденный файл.

## 5. Файлы
- apps/api/app/routers/onboarding.py — гейт, status, docstring;
- apps/api/tests/conftest.py — фикстура доступа (раздел 8);
- apps/api/tests/test_first_launch.py и файл теста status — новые тесты;
- другие apps/api/tests/*.py — только добавить выдачу доступа, где тест с БД вызывает first-launch
  с user_id ≠ TEST_USER_ID (раздел 8); каждый такой файл перечислить в описании PR;
- docs/DEFECTS-FOUND.md (1 запись), docs/STATE.md (раздел 11).

## 6. Логика
Запрос — ТОЛЬКО так, явно по колонке (у app_api нет прав на остальные колонки):
    def _has_access(session, tg_user_id: int) -> bool:
        status = session.execute(
            select(AccessGrant.status).where(AccessGrant.tg_user_id == tg_user_id)
        ).scalar_one_or_none()
        return status == ACCESS_STATUS_GRANTED
Запрещено:
- select(AccessGrant) и session.get(AccessGrant, …) — читают все колонки → ошибка прав;
- FOR UPDATE / FOR SHARE — прав нет, а доступ только выдаётся, не отзывается.

POST first-launch. Порядок из docstring (1e-1, раздел 7) сохраняется; в шаг 5 добавляется 5а:
    5) ОДНА транзакция:
       5а) find_active_participant(tg_user_id) нет И _has_access(...) ложь
           → откат, 403 ACCESS_NOT_GRANTED; ничего не записано
       5б) дальше как было: тексты согласий → get_or_create → consent_events → participant_events → commit
- Активный участник (returning / reconsent) проходит 5а без проверки флажка.
- Строка tombstoned — не активный участник, поэтому нужен granted.
- Ответ: _error(403, "ACCESS_NOT_GRANTED", "Доступ не открыт.") — тело как у остальных ошибок, без pid.
- Лог отказа: «first-launch: reason=access_not_granted» — БЕЗ tg_user_id, как у отказа по возрасту.

GET /onboarding/status:
- активная строка есть → как было (returning / reconsent);
- строки нет или tombstoned → _has_access: да → {"status":"new"}, нет → {"status":"no_access"};
- OnboardingStatus.status: Literal["returning","reconsent","new","no_access"];
- лог: «status: tg_user_id=<id> status=no_access» — формат как у остальных статусов;
- 403 status не отдаёт.

Docstring onboarding.py:
- в «Вне контракта» добавить 403 ACCESS_NOT_GRANTED и status no_access (Р-2, D-?);
- строку «403 для неизвестного tg_user_id НЕ отдаётся (решение Автора; D-9 п.2)» заменить на
  «Р-2 (STATE): без доступа (access_grants.status ≠ granted) pid не создаётся → 403
  ACCESS_NOT_GRANTED; прежний запрет D-9 п.2 (R327) перекрыт»;
- в порядке шагов отразить шаг 5а.

## 7. Чего НЕ делать
- Не менять проверки возраста и согласий: они идут до БД; тесты «без БД» остаются зелёными.
- Не писать в access_grants: у app_api нет прав, писатель — бот.
- Не трогать apps/miniapp (это карточка miniapp-access-1) и docs/architecture/**.

## 8. Тесты
После гейта все тесты с БД, которые вызывают first-launch, получат 403. Чинить так:
- conftest.py: helper grant_access(engine_or_url, tg_user_id) — INSERT access_grants (status 'granted',
  created_via 'bot_promo') под владельцем, ON CONFLICT DO NOTHING;
- после очистки БД перед тестом вызывать grant_access для TEST_USER_ID — встроить в ту фикстуру с БД,
  которая уже чистит таблицы;
- остальные id найти командой
      grep -n "user_id=" apps/api/tests/*.py
  и в тестах с БД, вызывающих first-launch, вызвать grant_access явно;
- если очистка не включает access_grants — добавить её.

Новые тесты (с БД):
- нет строки access_grants → 403 ACCESS_NOT_GRANTED; строк tg_user_registry и consent_events 0;
- status pending → 403; denied → 403; granted → 201 и pid;
- активный участник, строку access_grants удалить владельцем → повтор first-launch → 201 тот же pid;
- tombstoned участник без granted → 403;
- status: нет участника и доступа → {"status":"no_access"}; granted → {"status":"new"};
  активный участник без строки доступа → returning;
- ЗАПРОС ПОД app_api (П2): переключиться на app_api тем же способом, что в test_db_roles_0009.py, и выполнить
  ровно запрос _has_access → без ошибки прав, возвращает 'granted'. Плюс контрольная проверка:
  select(AccessGrant) под app_api → ошибка прав (тест доказывает, что явный select нужен);
- лог отказа содержит reason=access_not_granted и не содержит tg_user_id.
Существующие тесты «без БД» (403 по возрасту, 422 по согласиям) проходят без правок.
Быстрые тесты: bash tools/check.sh api.

## 9. DEFECTS-FOUND (1 запись, «D-?»)
- D-? build/miniapp-api-contract.yaml не знает 403 ACCESS_NOT_GRANTED (first-launch) и status no_access
  (Р-2). Правка DOCS вместе с D-22.

## 10. Порядок мержа и выката
Мерж — после db-access-1. Выкат api — только в одном задании с bot-access-1 или после него.

## 11. Строки STATE (внести в PR)
В «Решения, перекрывающие канон», дописать к Р-2:
- Р-2 (дополнение 23.10, api-access-1): first-launch при отсутствии активного участника и
  access_grants.status ≠ granted → 403 ACCESS_NOT_GRANTED, pid не создаётся; GET /onboarding/status →
  200 {"status":"no_access"}. Перекрывает запрет «403 для неизвестного tg_user_id» (D-9 п.2, R327).
  Существующих участников гейт не трогает.
В «Сейчас» / «Очередь»:
- api-access-1 (Р-2, в1): гейт first-launch; выкат только с bot-access-1 или после него.

## 12. Сервер (после 25.10, задание ШТАБа)
- С аккаунта тестового участника Mini App открывается как раньше (returning).
- Новый аккаунт без доступа → в логе api «status … no_access».
- Полная проверка — в bot-access-1, раздел 13.

## 13. Кредиты, CI
- Оценка кредитов: 400–700.
- CI НЕ ЖДАТЬ: после push сразу ИТОГ и конец; gh run watch и опрос проверок запрещены.

## 14. РЕВЬЮЕР
Да (доступ к онбордингу). Проверить:
- нет пути создать pid без granted, в том числе после tombstone;
- tg_user_id берётся только из initData;
- возраст и согласия проверяются до БД;
- в логе нет tg_user_id;
- запрос читает только status.
РЕВЬЮЕР — после 25.10 (новые кредиты), до выката.
