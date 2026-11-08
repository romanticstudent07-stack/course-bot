# projector-i3-2 — проектор: kind tz_set (пояс из анкеты), PROJECTOR_VERSION 4

## 1. Паспорт
- id: projector-i3-2 · ветка: projector/i3-2-tz-set · режим: Р0+ (КОДЕР) · РЕВЬЮЕР: нет (раздел 14).
- Заголовок PR: «projector: kind tz_set → participant_state.tz до первого дня, версия 4 (projector-i3-2)».
- Зависит от: нет (миграций нет). Порядок (утверждено ШТАБом 07.11): cities-1 ‖ projector-i3-2 (два окна КОДЕРА параллельно) → api-i3-2 (Агент, после мержа обеих). Выкат — одним заданием серверу, проектор РАНЬШЕ api-i3-2.

## 2. Цель
Проектор применяет событие tz_set из анкеты: пишет participant_state.tz, если участник ещё не начал первый день; иначе — WARNING и пропуск. PROJECTOR_VERSION 3 → 4.

## 3. Решения (метки К-6)
- Р-16 [Автор, DECISIONS]: «город → только tz (IANA), сам город не храним».
- Ш-1 [ШТАБ-тех 07.11, К-5]: kind tz_set; PROJECTOR_VERSION 3 → 4; WHERE day_no IS NULL; 0 строк → WARNING и пропуск; проверка tz 1–64 и ZoneInfo.
- [errata E1, INV-1]: API в participant_state не пишет никогда; SQL записи — только app/projector.py.
- П-4 [ПРОЕКТИРОВЩИК, К-5]: до ZoneInfo — шаблон ^[A-Za-z][A-Za-z0-9_+-]*(/[A-Za-z0-9_+-]+){0,2}$ (ZoneInfo открывает файл по имени). Набор из 11 поясов проектор не сверяет — это делает API.

## 4. Выдержки
- 04 yaml: «timezone: applies_next_day»; 14 §14.11: смена пояса — со следующего дня. До первого дня «следующего дня» нет → пояс сразу; смена пояса на курсе — отдельная задача.
- По коду projector.py: неизвестный kind → WARNING «unknown kind», checkpoint сдвигается (поэтому выкат раньше api); битое событие — SAVEPOINT, пачка идёт дальше; WARNING без pid и значений (тесты day_entered).
- По коду 0007: tz text NOT NULL DEFAULT 'Europe/Moscow', CHECK <> ''. Права app_projector на UPDATE participant_state уже есть — новых GRANT нет.
- kind в БД: в 0001 таблицы participant_events нет (она в 0005, не открывал). CHECK на список kind нет — по коду: tests/test_life_ops.py::test_pending_event_skipped вставляет kind 'test_pending' и проходит в CI. Миграция не нужна.

## 5. ЧТО ПРОЧИТАТЬ (КОДЕР)
apps/api/app/projector.py 32,3 КБ; tests/test_projector_day_entered.py 8,4 (образец); tests/test_projector_v3.py 16,9; tests/test_projector.py 9,6; tests/test_projector_static.py 2,4; вывод grep Автора (§ Задетые). Чтение КОДЕРА ≈ 70 КБ.

## 6. Файлы
- Изменить: apps/api/app/projector.py; apps/api/tests/test_projector_day_entered.py; apps/api/tests/test_projector_v3.py; apps/api/tests/test_projector.py; плюс файлы из вывода grep, если найдутся.
- Создать: apps/api/tests/test_projector_tz.py.

## 7. Изменения projector.py
- Докстринг: «Виды событий (PROJECTOR_VERSION 4, projector-i3-2)» и строка про tz_set (§2, §4).
- PROJECTOR_VERSION = 4; EVENT_KIND_TZ_SET = "tz_set"; MAX_TZ_LEN = 64.
- tz_from_payload(payload) -> str | None: dict или JSON-строка (как position_from_payload); tz — str, длина 1–64, шаблон П-4, ZoneInfo(tz) без исключения (ZoneInfoNotFoundError, ValueError, OSError → None). Лишние ключи игнорируются.
- Ветка в _apply_event: None → WARNING «bad payload» тем же форматом (id=, kind=), пропуск. Иначе UPDATE participant_state SET tz = :tz, projector_version = :v, updated_at — так же, как в соседних ветках, WHERE pid = :pid AND day_no IS NULL RETURNING pid. 0 строк → WARNING «tz_set: day started or no state» (id=, kind=), пропуск.
- В логах нет pid и значения tz. Другие виды событий и порядок обработки не трогать.

## 8. БД
Миграций нет; expected_tables.txt не меняется.

## 9. Тесты — apps/api/tests/test_projector_tz.py
Без БД (check.sh api):
1. tz_from_payload: «Europe/Moscow», «Asia/Yekaterinburg», JSON-строка → строка; нет ключа, '', 65 символов, 123, «Mars/Olympus», «../etc/passwd», «/etc/localtime», «Europe/Moscow » (пробел), «not json» → None.
2. PROJECTOR_VERSION == 4; EVENT_KIND_TZ_SET == "tz_set".
С БД (только CI):
3. Онбординг + tz_set → tz записан, projector_version 4, lifecycle_phase и status_flags прежние, ProjectorResult(processed=1, skipped=0).
4. Два tz_set подряд до дня → действует последний.
5. День начат (day_entered применён) → tz_set пропущен, tz прежний, checkpoint = id события, WARNING с kind=tz_set без pid и tz.
6. Нет строки состояния → пропуск, строка не создана, checkpoint сдвинут.
7. Битый payload → пропуск; следующее событие в той же пачке применено.

## 10. Живые проверки (СЕРВЕРНЫЙ; команды даёт ШТАБ)
Выкат проектора до api-i3-2; лог проектора без ошибок. После выката api — в логе нет «unknown kind» с tz_set. Бэкап не нужен.

## 11. Запреты
AGENT-BRIEF §3. SQL записи в participant_state — только в projector.py; другие ветки не менять; pid и tz не логировать; новых зависимостей нет.

## 12. Критерии готовности
Тесты 1–7 и тесты из «Задетых» зелёные (1–2 в check.sh, все в CI); test_projector_static зелёный.

## 13. Оценка
Автор ≈ 0,5 ч; кредиты 0 (Р0+).

## 14. РЕВЬЮЕР
Нет: initData, согласий, GRANT и ПДн задача не трогает (tz без pid в логах).

## Задетые тесты
Найдено по коду @8f72973:
- test_projector_day_entered.py::test_position_from_payload — «assert PROJECTOR_VERSION == 3  # life-ops-a» → «== 4  # projector-i3-2».
- test_projector_v3.py::test_version_is_3 — «== 3» → «== 4», имя → test_version_is_4.
- test_projector_v3.py::test_report_with_next_fields_advances_day — «projector_version == 3» → «== PROJECTOR_VERSION» (видел в З1; строку сверить по grep).
- test_projector.py::test_first_consent_builds_onboarding — «== 3» → «== PROJECTOR_VERSION» (видел в З1; сверить по grep).
Номера версии нет: test_projector_day_report.py, test_life_ops.py, test_clocks_1.py, test_day_test_enter.py; прочие сверки в test_projector_day_entered.py — через PROJECTOR_VERSION.
Общие списки kind: test_life_ops.py::test_kinds_match_projector сверяет только life_op и day_closed — не задет.
Не открывал: test_life_ops_race.py, test_notify_*.py, остальные test_day_*.py, test_db_*.py. Шаг 0 Автора до КОДЕРА (Codespaces): grep -rn "projector_version\|PROJECTOR_VERSION" apps/api/tests — вывод вставить КОДЕРУ; каждое «== 3» → «== PROJECTOR_VERSION».

## Канон и решения
(а) 04 yaml timezone; 14 §14.11; errata E1 / INV-1.
(б) 14 §14.11 ведёт историю поясов в tz_change_log, у нас история — события tz_set в participant_events (append-only). Кандидат в DEFECTS (решает ШТАБ).
(в) Правок канона нет.
