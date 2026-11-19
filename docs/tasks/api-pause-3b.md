# api-pause-3b — проектор v9: старт паузы из requested, без Р14 (канон 02 П.2)
Hash main: edd15c9 · Область: API (проектор) · Пачка pause-3: 3b → 3a (docs/tasks/api-pause-3a.md стартует у Агента после мержа 3b).
Источник: docs/research/pause-3.md@e581539 (§2, §3, §6, §8); тела функций — выводы команд Автора по edd15c9 (projector.py:563-579, 1211-1255, 1297-1372); З2 ШТАБа.

## 1. Паспорт
- id: api-pause-3b · Заголовок PR: «api-pause-3b: проектор v9 — старт паузы из requested, без Р14»
- Ветка: api-pause-3b · Режим: Р1 · Зависит от: api-pause-1a, api-pause-1b, api-pause-2 (все в main)
- Миграция: нет · РЕВЬЮЕР: да (указание ШТАБа)

## 2. Цель
Канон 02 П.2: Автор молчит до даты начала — пауза стартует сама. Проектор должен применять pause_started к заявке в статусе requested (часы начнут писать такое событие в 3a), а позднее «Одобрить» больше не гасит заявку (Р14 отменён). PROJECTOR_VERSION 8 → 9.

## 3. Решения (метка К-6)
- Д1 pause_started переводит в active заявку в статусе requested или approved; проверки те же (start_refusal, бюджет, Этап, 24 ч). [канон 02 П.2; Автор, канон проверен 02 П.2]
- Д2 Р14 карточки api-pause-1a отменён: pause_approved всегда переводит requested → approved, at и start_at не сравниваются. [Автор, канон проверен 02 П.2]
- Д3 Проектор передаёт в start_refusal status = pause_rules.STATUS_APPROVED (статус уже проверен выше) — как API T3 (api-pause-2 Д4). pause_rules.py не меняется; not_approved остаётся в REFUSAL_REASONS (старые события pause_start_failed). [ШТАБ-тех, pause-3 §1–§2]
- Д4 Отказ Р15 гасит заявку из её фактического статуса: в _SET_PAUSE_STATUS (строка 1353) "from" = pause.status вместо жёсткого "approved". Без правки заявка requested с отказом осталась бы requested навсегда (ключ часов pause_start повтора не даст). [решил ШТАБ, К-5, З2 п.1]
- Д5 pause_approved / pause_rejected по заявке в статусе active, ended или cancelled (кнопки Автора после авто-старта или отказа) — пропуск без смены статуса, лог INFO, без WARNING. По коду: _set_pause_status сам WARNING не пишет; при статусе не из allowed_from он вызывает _skip(event_id, kind, "pause: status not allowed") (1225-1227); уровень лога _skip в выводе ШТАБа не виден — поэтому тихая ветка стоит до _skip и от него не зависит. Норма сервера — WARNING 0. [ШТАБ-тех, pause-3 §3; по коду: projector.py:1211-1235]
- Д6 Алерт Автору об авто-старте (канон 02 П.2 «+ алерт Автору») делает бот — T4 bot-pause-1; API не добавляет kind, text_id, outbox. Миграции нет. [Автор, канон 02 П.2; З2 п.3; pause-3 §4, §7]
- Д7 Версия 9: изменилось поведение видов pause_started и pause_approved (по образцу v7, v8). [ШТАБ-тех, pause-3 §2]

## 4. Канон и решения
(а) Использует:
- 02 П.2: «Пауза требует одобрения Автора одним тапом (✅ Одобрить / ✖ Отклонить; Автору ничего вводить не нужно — параметры уже заданы Участником). Но если Автор молчит до наступления даты начала — Бот ставит паузу сам + алерт Автору. Молчание Автора = авто-разрешение (не вредит Участнику).»
- 02 YAML pause.approval: «on_author_silence: auto_approve_at_start_date   # + алерт Автору, не вредит участнику».
- 02 П.8: «Лимит тратится в момент запуска паузы (в т.ч. при авто-разрешении по молчанию Автора …)» — списание бюджета в pause_started и так общее для обоих статусов.
- 02 П.3: пауза начинается с 00:00 по ТЗ участника (start_at — как в api-pause-1a Р3).
(б) Противоречий с DECISIONS.md нет: Р-6а задаёт лимиты, об одобрении молчит.
(в) —
(г) Правок канона нет.

## 5. ЧТО ПРОЧИТАТЬ (Агент)
AGENT-BRIEF.md 17,1; docs/decisions/DECISIONS.md 7,7; эта карточка ≈ 10; apps/api/app/projector.py 73,8 (целиком); apps/api/tests/test_projector_pause.py 15,1.
Файлы с версией (раздел 9, кроме test_projector_pause.py) не читать: правка одной строки по номеру.
Чтение Агента ≈ 124 КБ. docs/architecture/** не открывать.

## 6. Файлы
Изменить: apps/api/app/projector.py; apps/api/tests/test_projector_pause.py; только строки версии — apps/api/tests/test_projector_day_entered.py, test_projector_sleep.py, test_projector_tz.py, test_projector_v3.py, test_projector_restart.py, test_projector_revive.py.
Создать: нет. Удалить: нет.

## 7. Что сделать в projector.py (номера строк — edd15c9)
1. PROJECTOR_VERSION = 9.
2. _START_PAUSE (572-579): «AND status = 'approved'» → «AND status IN ('requested', 'approved')».
3. _apply_pause_started (1297-1372):
   - 1313: «if pause.status != "approved":» → «if pause.status not in ("requested", "approved"):»; пропуск «pause: status not allowed» как есть (повтор при active — пропуск, test_p5).
   - 1335: «status=pause.status,» → «status=pause_rules.STATUS_APPROVED,» (Д3).
   - 1353: «{"id": pause_id, "pid": pid, "from": "approved", "to": "cancelled"},» → «{"id": pause_id, "pid": pid, "from": pause.status, "to": "cancelled"},» (Д4).
   - Бюджет, _CHARGE_PAUSE_BUDGET, флаг, фазу и WARNING Р15 не трогать.
4. Константа рядом с SQL пауз: «_LATE_BUTTON_STATUSES = ("active", "ended", "cancelled")» с комментарием «Д5 api-pause-3b: кнопки Автора после старта или отказа — тихий пропуск».
5. _set_pause_status (1211-1235): добавить последний параметр «quiet_from: Sequence[str] = (),». В ветке 1225 перед _skip:
       if row.status not in allowed_from:
           if row.status in quiet_from:
               logger.info(
                   "projector: %s пропущен: пауза уже %s, event id=%s", kind, row.status, event_id
               )
               return False
           _skip(event_id, kind, "pause: status not allowed")
           return False
   Ветки 1222-1224 и 1232-1234 не трогать. В лог — без pid и payload.
6. _apply_pause_approved (1238-1255): убрать вложенную _to и комментарий Р14; вызов:
       return _set_pause_status(
           conn, event_id, pid, kind, pause_id, ("requested",), lambda _row: "approved",
           quiet_from=_LATE_BUTTON_STATUSES,
       )
7. _apply_pause_rejected: в его вызов _set_pause_status добавить только «quiet_from=_LATE_BUTTON_STATUSES»; allowed_from и to_status не менять. Другие вызовы _set_pause_status не менять.
8. Docstring проектора: версия 9; «pause_approved {pause_id}: requested → approved» (без Р14); «pause_started {pause_id}: requested | approved → active (канон 02 П.2: молчание Автора — авто-старт)»; «кнопки после active / ended / cancelled — INFO, без WARNING»; ссылка на docs/tasks/api-pause-3b.md.

## 8. Контракт (меняет раздел 5 api-pause-1a; для T4 bot-pause-1)
Статусы kind user: requested → approved | rejected | cancelled | active; approved → active | cancelled; active → ended.
- Часы (3a): pause_started {pause_id} — для requested и approved при одних условиях; pause_start_failed с reason not_approved больше не пишется.
- Проектор принимает старые pause_start_failed {reason: "not_approved"} (заявка → cancelled, как сейчас).
- Бот (T4): алерт Автору об авто-старте (канон 02 П.2); кнопки Автора по заявке, ставшей active, — ответ «пауза уже началась» (text_id — заглушка в T4), событие не пишется. Признак авто-старта — active без ключа решения бота. Проверка «now < start_at» из api-pause-1a §5 отменена. Карточку T4 правит ШТАБ отдельно.

## 9. Задетые тесты (правило «Т»)
Версия — только строка, правка 8 → 9 (номера по edd15c9, выводы команд Автора):
- test_projector_day_entered.py:84 «assert PROJECTOR_VERSION == 8  # api-revive-1» → «assert PROJECTOR_VERSION == 9  # api-pause-3b»;
- test_projector_sleep.py:80 «assert PROJECTOR_VERSION == 8» → «assert PROJECTOR_VERSION == 9»;
- test_projector_sleep.py:211 «assert state.projector_version == 8» → «== 9»;
- test_projector_sleep.py:324 «assert state.projector_version == 8» → «== 9» (отступ 8 пробелов сохранить);
- test_projector_tz.py:100 «assert PROJECTOR_VERSION == 8» → «assert PROJECTOR_VERSION == 9»;
- test_projector_v3.py:32 «assert PROJECTOR_VERSION == 8  # api-revive-1» → «assert PROJECTOR_VERSION == 9  # api-pause-3b»;
- test_projector_restart.py:182 «assert state.projector_version == 8» → «== 9»;
- test_projector_revive.py:183 «assert state.projector_version == 8» → «== 9»;
- test_projector_pause.py:174 «assert state.projector_version == 8» → «== 9».
test_projector.py импортирует PROJECTOR_VERSION без числа — не задет.
test_projector_pause.py, кроме строки 174:
- строка 1 docstring: «Проектор v8 (api-pause-1a, раздел 8)» → «Проектор v8–v9 (api-pause-1a раздел 8; api-pause-3b)»;
- test_p3_late_approve_cancelled → test_p3_late_approve_approved: тот же сценарий (pause_approved с at = START), ожидать status "approved", флагов нет; комментарий «Р14 отменён (api-pause-3b Д2)».
Упал тест вне списка — не чинить, «тест X вне списка» в ИТОГ.

## 10. Новые тесты (test_projector_pause.py, фикстуры файла)
- test_p10_started_from_requested: _pause requested; pause_started at STARTED_AT без pause_approved → ProjectorResult(processed=1, skipped=0); строка (active, 2, 0); флаги ["pause_user"]; фаза sleeping; бюджет 11.
- test_p11_requested_refused_cancelled: _active с flags {block_lives}, phase sleeping, lives 0; заявка requested; pause_started → статус cancelled, pause_user нет, бюджет прежний, WARNING «pause_started отклонён: block_lives» (проверяет Д4).
- test_p12_late_buttons_after_auto_start: requested → pause_started → active; затем pause_approved и pause_rejected с at = START + 1 ч → статус active, флаги ["pause_user"], нет WARNING от app.projector (caplog, _warnings), есть INFO «пропущен: пауза уже active». processed + skipped == 2; деление — по коду run_once для return False, записать в PR.
Цель: bash tools/check.sh api. Тесты с БД — только CI.

## 11. Живые проверки
Отдельно 3b не выкатывать: выкат одним образом projector после мержа 3a (PLAN §4). Ожидания — docs/tasks/api-pause-3a.md §11.

## 12. Запреты
AGENT-BRIEF §3. Плюс: pause_rules.py, pause_ops.py, routers/pause.py, day_keys.py, миграции не трогать; новых kind, text_id, outbox нет; текст WARNING Р15 не менять (test_p4); тело _skip не менять; SQL записи participant_state — только в projector.py (test_projector_static).

## 13. Готово, когда
CI зелёный; PROJECTOR_VERSION = 9; pause_started применяется из requested и approved; отказ гасит requested; поздний pause_approved → approved; кнопки после active / ended / cancelled — без смены статуса и без WARNING; в описании PR — отличия от карточки или «нет».

## 14. Оценка
Часы Автора ≈ 0,5. Кредиты ≈ 950 (≈ 600 + 6 файлов версии × 60), стоп 1 400.

## 15. РЕВЬЮЕР
Да (указание ШТАБа: меняется правило старта паузы в единственном писателе participant_state).
