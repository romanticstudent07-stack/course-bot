# iter2-api-2b — отправка отчёта дня (П-31, идемпотентность) + kind day_report_submitted

## 1. Паспорт
- id: iter2-api-2b. PR: «iter2-api-2b: POST day/report/submit + kind day_report_submitted».
- Ветка: feat/iter2-api-2b. Режим: Р0+. Начинать после мержа iter2-api-2a. Миграций нет.

## 2. Цель
Участник отправляет отчёт дня. Зачёт фиксируется только после подтверждённой записи в БД (П-31).
Повтор с тем же X-Client-Op-Id даёт тот же ответ. Проектор обнуляет missed_streak по текущему дню.

## 3. Решения Автора (дословно)
- «В15 — А» (повтор с тем же X-Client-Op-Id → 200 тем же телом); «В18 — А» (missed_streak = 0 после любого отправленного отчёта).
- «В22 — А (ключ day_done в idempotency_keys; проверки «догнал» нет; риск — в api-3)».
- «В5 — обычные дни + очередь 10–60 мин» (очередь показа — не эта задача).
- Источник контракта — docs/research/iter2-api.md §3, §6.

## 4. Выдержки
- 03-day-mechanics.md, шапка: «Инвариант зачёта дня П-31 (`day_counting: on_confirmed_db_write`) действует в исходной редакции.»
- §3.19, yaml: «day_counting: instant_regardless # очередь влияет ТОЛЬКО на показ»; «life_impact: none».
- По research §2: §3.9 — время сдачи по серверу; §3.10 — повтор игнорируется; §3.16 — «всё не выполнено»: жизнь цела, день не засчитан.
- miniapp-api-contract.yaml, ClientOpId: «UUID v4 клиента для идемпотентности (buttons_idempotent, money_ops_idempotent)».
- РЕВЬЮЕР #95: «проектор считает «пришёл» и «+1 ч» только по текущему day_started_at».

## 5. ЧТО ПРОЧИТАТЬ (КОДЕР)
AGENT-BRIEF.md 15,0; apps/api/app/projector.py 11,3 (после 2a); apps/api/app/routers/day.py, app/participant_lock.py,
app/day_keys.py, app/day_content.py (из api-1/2a); apps/api/app/errors.py (формат 422; КБ — ШТАБ);
tests/test_day_marks.py (образец; КБ — ШТАБ). Чтение КОДЕРА ≈ 26 КБ + файлы iter2-api-1/2a.

## 6. Файлы
Создать:
- apps/api/app/day_report.py — вердикт и params_hash, чистые функции;
- tests/test_day_report_unit.py, tests/test_day_report_submit.py, tests/test_projector_day_report.py.
Изменить:
- app/routers/day.py — POST /day/report/submit;
- app/projector.py — kind day_report_submitted.
Итого 6 файлов, ≈ 500 строк.

## 7. Контракт
POST /miniapp/v1/day/report/submit:
- Заголовок X-Client-Op-Id: uuid, обязателен; нет или не uuid → 422 (через существующий обработчик).
- Тело {marks: [{block_id ^[a-z0-9_]{1,32}$, value: done | not_done}]}; лишние поля (pid, day_started_at) игнорируются.

Порядок — одна транзакция:
1. pid = active_pid_locked (initData → tg_user_registry, замок, tombstoned) → None → 404 PARTICIPANT_NOT_FOUND.
2. Есть ключ day_report:{pid}:{op_id}:
   - params_hash тот же → 200 {verdict: result_ref, queued: true} (В15);
   - другой → 409 IDEMPOTENCY_CONFLICT.
3. Позиция и day_started_at из participant_state (та же транзакция); позиции нет → 409 DAY_NOT_STARTED.
4. Набор block_id ≠ блоки дня (лишний, недостающий, повтор) → 422 MARKS_INCOMPLETE.
5. Есть ключ day_done по текущему day_started_at → 409 DAY_ALREADY_SUBMITTED.
6. UPSERT day_marks — как PUT в 2a (at не меняется).
7. Вердикт — day_report.verdict.
8. INSERT idempotency_keys: day_done (ttl '3650 days', result_ref = verdict) и day_report (ttl '1 hour', result_ref = verdict, params_hash).
9. INSERT participant_events kind day_report_submitted,
   payload {day_started_at: dsa, verdict, stage_no, module_no, day_no}, actor participant.
10. Явный commit → 200 {verdict, queued: true}. Ответ строится только после успешного commit.

- Любая ошибка БД, в том числе на commit → откат, 503 SERVICE_UNAVAILABLE. Ложного 200 нет (П-31).
- Время — now() сервера, время клиента не принимается.

day_report.py:
- verdict: all_not_done — все not_done; passed — все critical = done и done среди некритических ≥ min_optional; иначе not_passed.
- params_hash = sha256 канонического JSON отсортированного списка [block_id, value].

## 8. БД и проектор
- Миграций нет.
- kind day_report_submitted:
  - UPDATE participant_state SET missed_streak = 0, updated_at = now(), projector_version
    WHERE pid = :pid AND day_started_at = (payload->>'day_started_at')::timestamptz;
  - любой вердикт (В18); 0 строк (старый день) → WARNING (id, kind), пропуск.
- Без ON CONFLICT; status_flags, lifecycle_phase, lives в SQL не упоминаются.
- Отставание проектора: отчёт до применения day_entered → позиции нет → 409 DAY_NOT_STARTED, клиент повторит.
  Ложного успеха нет. Риск устаревшего дня — в api-3 (В22 = А).

## 9. Тесты
test_day_report_unit:
- все ветки вердикта, включая min_optional = 0 и «все not_done»;
- params_hash не зависит от порядка marks.

test_day_report_submit:
- 422: без заголовка, не uuid, неполный набор, повтор block_id, чужой block_id;
- 200 passed / not_passed / all_not_done: записаны ключи day_done и day_report, одно событие, отметки;
- повтор того же op_id и тела → тот же 200, второго события нет;
- тот же op_id, другое тело → 409;
- новый op_id после сдачи → 409 DAY_ALREADY_SUBMITTED;
- без позиции → 409; tombstoned → 404, ничего не записано;
- «pid и day_started_at из тела игнорируются»;
- П-31: commit бросает OperationalError (monkeypatch) → 503, в БД нет ключей, события и отметок;
- два параллельных submit с разными op_id → один 200, другой 409;
- lives не изменились (Ш1);
- GET после submit → status submitted.

test_projector_day_report:
- missed_streak обнуляется только при совпадении day_started_at; старый день → пропуск;
- status_flags = '{block_lives}' и lives не меняются.

tools/check.sh — быстрые (unit); с БД — CI.

## 10. Сервер (после мержа)
- Миграций нет. Пересобрать и перезапустить api и projector ВМЕСТЕ (Ш5).
- Проверки:
  - /healthz 200; POST /miniapp/v1/day/report/submit без initData → 401;
  - projector once → пропущено 0, в логе нет WARNING;
  - число таблиц не изменилось (фильтр table_name <> 'alembic_version').
- Флаг входа — по отдельному заданию ШТАБа (не в этой задаче).

## 11. Запреты
- AGENT-BRIEF §3. API не пишет participant_state.
- Без миграций и GRANT. UPDATE и DELETE idempotency_keys нет.
- Тексты — только заглушки.

## Вне задачи
- Жизни не меняются ни при каком вердикте: life_op — api-3 (Ш1).
- Очередь показа 10–60 мин (В5), «пришёл» и «+1 ч», выдача следующего дня и перевыдача (В10) — api-3.
- DOCS PR в CT (тела day/*, «повтор = тот же 200», D-25, D-26) — отдельно после карточек (Ш6).

## 12. Готовность
- CI 7/7; РЕВЬЮЕР — 0 блокирующих.
- Тест П-31 зелёный. Живые проверки ✅.

## 13. Оценка
Автор ≈ 0,8 ч (+ РЕВЬЮЕР); кредиты 0.

## 14. РЕВЬЮЕР
Да — П-31, идемпотентность, initData → pid (Ш7).
