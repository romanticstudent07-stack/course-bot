# Исследование: Итерация 3 «Чек-Ап и Карточка» (пачка iter3)

Окно ИССЛЕДОВАНИЕ, З1, 30.10.2026, @49dd033. Карточек нет.
Пути (канон — в docs/architecture/): DEC = docs/decisions/DECISIONS.md; BO = build/build-order.md;
SC = build/miniapp-screens.md; CT = build/miniapp-api-contract.yaml; TI = build/db-tables-index.md;
RG = build/bot-commands-registry.yaml; CM = build/commands-mapping.md; P5 = 05-checkup.md;
P6 = 06-participant-card.md; I3 = normative/I3-wave-c.md; AB = AGENT-BRIEF.md;
MO = apps/api/app/db/models.py; LS = apps/miniapp/src/components/LaterSteps.tsx;
ET = apps/api/tests/expected_tables.txt; M01…M10 = apps/api/migrations/versions/*-00NN_*.py.

## 1. Что требует И3

| Что | Требование | Канон |
|---|---|---|
| me.card /me | данные, замеры, позиция, жизни; GET /me/card без согласий и юр.данных | SC «Карточка»; CT; P6 §6.4 |
| me.consents | «Мои согласия C0–C6», без фото; GET и POST /consents | SC; CT; DEC Р-3 |
| me.change-map | антропометрия, самочувствие, функциональные; слоя «фото» нет; GET /me/change-map | SC; CT; P5 §5.8; Р-3 |
| /card | owner, без hard-confirm, audit privacy, work_group_reply | BO «Итерация 3»; RG data |
| /card fail-safe | whitelist; нет идентификатора → уточнить; нет такого → «не найден»; только тема «Карточки»; аудит кто/когда/чью | P6 Fail-safe |
| Генерация | свежая из БД, не хранится | P6 §6.1; BO |
| privacy_audit_log | каждый доступ Автора/Помощника к ПДн | TI; BO |
| Чек-Ап | 15 вопросов 0–3, макс. 45, подсчёт на сервере; хранить 15 ответов, балл, зону, дату; продолжение, «Вопрос N из 15», «Исправить»; тест 9/10/22/23 | P5 §5.1–5.5 |
| Чек-Ап (норматив) | участнику — только зона; checkup.scored; конфиг версионируется; красная зона — гейт Legal | I3 C.7, C.8 |
| API | GET /checkup/config, POST /checkup/submit (X-Client-Op-Id) | CT |
| Роли | moderator и finance не разграничивать — owner | BO «Открытые несовместимости» п.2 |

Не делаем: me.settings-notifications (Р-6); фото, C5, /photo/submit (Р-3); оплату и «Оплаты»
в карточке (Р-1); pre-signed экспорт (Р-5). me.legal-data и /export не входят в BO «Итерация 3»,
поэтому вне пачки (решит ШТАБ).

## 2. Что есть в коде (как сейчас)

- consent_events — append-only, пишет только first-launch, CHECK created_via = 'mini_app_first_launch' (MO).
  GET /miniapp/v1/consents — только чтение, по kind решает последнее событие
  (apps/api/app/routers/consents.py). POST /consents нет.
- LS: offer → email → city → checkup → rules → finished. checkup и rules — текст и кнопка, вопросов нет.
  Анкета на сервер не уходит (черновик step/email/city, 24 ч). Согласия — строка на finished.
  ФИО, телефона, замеров нет.
- Mini App: маршрут только /day (apps/miniapp/src/navigation/routes.tsx).
- participant_state: lives 0..3, stage/module/day_no, day_started_at, missed_streak, tz (M07);
  lifecycle_phase, status_flags (M01). Пишет только проектор, app_api читает (M06).
- tg_user_registry.short_no — identity (MO).
- privacy_audit_log (M01): actor_id, actor_role, action, participant_id, occurred_at, metadata;
  GRANT только SELECT для audit_reader. Писателя нет.
- app_bot (M09): outbox, outbox_dlq, tg_user_registry (pid, tg_user_id, tombstoned_at), text_registry;
  participant_state и short_no бот не видит.
- Бот: ACCESS_ADMIN_IDS «временно до Б17», WORK_GROUP_ID, BOT_DATABASE_URL (apps/bot/bot/config.py). /card нет.
- Таблиц 16 (ET), последняя миграция 0010_access_grants. Таблиц Чек-Апа, замеров, whitelist_admin_ids нет.

## 3. Блокеры, противоречия, DEFECTS

- Б-1. Данных Карточки нет: P6 §6.4 «ФИО, возраст, регион, телефон, вес, зона» против AB §7
  (дату рождения не храним) и LS (анкета не уходит). → В1, D-44.
- Б-2. Нет писателя privacy_audit_log; бот не видит participant_state и short_no. Миграция прав, РЕВЬЮЕР. → В6, D-43.
- Б-3. /card @username: username не храним (MO, access_grants). → В3, D-46.
- Б-4. P5 §5.4 «балл + зона» и CT «5 зон» против I3 C.7 (только зона, 3 зоны). По К-2 прав I3; правка DOCS. → D-45.
- Б-5. I3 C.7 требует checkup_config_versions и гейт Legal, а Панель — в И6. → В2.
- Б-6. Отзыв согласий: в CT есть POST /consents; мешают CHECK created_via и остаток D-22;
  последствия отзыва C0/C1 — не проверено. → В4.
- Б-7. Карта изменений (Блок 14): повторных опросов пока нет. → В5.
- Б-8. RG /card даёт moderator, BO п.2 — только owner. Делаем owner, вопрос не нужен.
- Б-9. P6 §6.5: одна карточка в теме, автоудаление через 24 ч. Решит ШТАБ; предлагаю не в И3 (D-48).

Кандидаты (дублей в docs/DEFECTS-FOUND.md нет; новые — с D-43):
- D-43. privacy_audit_log без писателя (M01) → GRANT в миграции И3. Автор: нет.
- D-44. P6 §6.4 требует данных, которых продукт не собирает (возраст, ФИО, телефон, вес; оплаты — Р-1;
  паузы — Р-6а; счётчик возвратов). Автор: да (В1).
- D-45. CT «5 зон» и P5 §5.4 «балл» против I3 C.7. Автор: нет.
- D-46. /card @username без хранения username. Автор: да (В3).
- D-47. CT не приведён к Р-1/3/5/6 (/photo/submit, /payment/*, /refund/request,
  /notifications/settings, C5). Перед записью сверить docs/decisions/DOCS-CANON.md. Автор: нет.
- D-48. P6 §6.5 не делается в И3. Автор: нет.
- Дополнение D-22: отзыв потребует расширить CHECK consent_events_created_via.

## 4. Нарезка на пачки

Миграции по одной, начиная после 0010. Новая таблица → GRANT в той же миграции + ET.

| # | Пачка | Область | Что | Зависит | Режим, оценка | РЕВЬЮЕР |
|---|---|---|---|---|---|---|
| 0 | iter3-docs | docs | D-43…D-48, дополнение D-22; правки DOCS (P5 §5.4, CT зоны) | — | Р0, 0 | нет |
| 1 | iter3-db-1 | БД | 0011: app_bot INSERT privacy_audit_log + USAGE seq; членство participant_state_reader; SELECT short_no. Таблиц нет | В6 | Р0+, 1–1,5 ч | да |
| 2 | iter3-db-2 | БД | 0012: результаты Чек-Апа (15 ответов, балл, зона, версия конфига, дата, client_op_id) + GRANT app_api + ET | 1, В2 | Р0+, 1,5 ч | да |
| 3 | iter3-db-3 | БД | 0013: анкета по В1 + GRANT + ET | 2, В1 | Р0+, 1,5 ч | да (ПДн) |
| 4 | iter3-api-1 | API | конфиг Чек-Апа (JSON) + GET config + POST submit (подсчёт, зона, 9/10/22/23, повтор → тот же 200) | 2 | Р0+ или Агент ≈ 500 | нет |
| 5 | iter3-api-2 | API | GET /me/card, /me/change-map; запись анкеты при В1 = А | 3, 4 | Р0+ или Агент ≈ 550 | да, если анкета |
| 6 | iter3-miniapp-1 | Mini App | Чек-Ап онбординга вместо заглушки в LS + анкета | 4 (5) | Р0+, 2 ч | нет |
| 7 | iter3-miniapp-2 | Mini App | /me, /me/consents, /me/change-map, переход с /day | 5 | Р0+, 2 ч | нет |
| 8 | iter3-bot-1 | bot | /card #short_no: whitelist, тема, аудит в той же транзакции до отправки, «не найден», «нет данных» | 1 | Агент ≈ 600 или Р0+ | да |

Порядок: 0 → 1 → 2 → 4 → 6 → 3 → 5 → 7; пачка 8 — сразу после 1.

## 5. Чтение окон КАРТОЧКИ (КБ, лимит 170)

База ≈ 89: DESIGNER 15,4; STATE ≈ 20; AB 17,1; README 8,7; DEC 8,5; CANON-CHECK 4; этот файл ≈ 14.
- 0: DEFECTS-FOUND 23, P5 7,6, CT 16,6 → ≈ 136.
- 1: M01 9,6, M06 5,6, M09 5,0, MO 14,6 → ≈ 124.
- 2: M10 7,5, MO 14,6, ET 0,6, P5 7,6, выдержка I3 C.7 3 → ≈ 122.
- 3: файл 0012, MO 14,6, ET 0,6, P6 9,7 → ≈ 122.
- 4: main.py 4,1, participants.py 4,8, day_keys.py 4,7, CT 16,6, P5 7,6 → ≈ 127 (day.py 39 не давать).
- 5: consents.py 6,1, MO 14,6, CT 16,6, P6 9,7 → ≈ 136.
- 6: LS 13,6, drafts.ts 13,7, client.ts 10,0, OnboardingFlow.test.ts 21,0 → ≈ 147.
- 7: App.tsx 6,8, routes.tsx 0,4, client.ts 10,0, SC 5,4, DayPage.tsx 17,4 → ≈ 129.
- 8: config.py 5,9, app.py 6,7, access_handlers.py 10,4, render.py 12,8, P6 9,7, RG 7,5 → ≈ 142.

## 6. Вопросы Автору

В1. Что показывать в блоках «Кто» и «Было → стало»?
Канон: проверено P6 §6.4, SC onb.form, AB §7 — противоречит: P6 «возраст, ФИО, регион, телефон, вес»;
решение «дату рождения не храним»; анкета из SC в коде на сервер не уходит (LS).
- А — анкета на сервер (ФИО, телефон, город → пояс, стартовый вес), возраст не показывать. Минус: больше ПДн, РЕВЬЮЕР, юрист.
- Б — в И3 без анкеты: short_no, ссылка tg://user, пояс, позиция, жизни, Чек-Ап. Минус: блок «Кто» почти пуст.
- Мнение: А; вместо возраста показывать «18+ подтверждено».

В2. Где хранить конфиг Чек-Апа до Панели (И6)?
Канон: проверено I3 C.7, P5 §5.3, DEC Р-7, BO «Итерация 6» — о временном варианте молчит.
- А — JSON в репо с номером версии, номер пишется в результат. Минус: смена конфига = выкат.
- Б — таблица checkup_config_versions сразу. Минус: миграция и публикация без Панели.
- Мнение: А; тексты — заглушки до 0-Б.

В3. Как искать участника в /card: по @username?
Канон: проверено P6 §6.2, BO «Итерация 3», MO (access_grants) — противоречит: канон требует /card @username, а username мы не храним.
- А — только /card #000123 (позже кнопка 📇). Б — хранить username (ПДн, надо обновлять).
- Мнение: А.

В4. «Мои согласия»: только просмотр или с отзывом?
Канон: проверено SC me.consents, CT POST /consents, I3 C.12 — противоречит: CT даёт отзыв,
I3 C.12 переносит панель с отзывом в И4.
- А — в И3 только просмотр. Б — отзыв сейчас (миграция CHECK, замок D-22, текст последствий — юрист).
- Мнение: А.

В5. Что показывать на Карте изменений в И3?
Канон: проверено SC me.change-map, P5 §5.8 — молчит о показе до повторных опросов.
- А — Чек-Ап (старт → последний) + стартовые замеры; остальное «нет данных». Б — экран только после Этапа 1.
- Мнение: А.

В6. Как бот получает данные Карточки?
Канон: проверено P6 §6.1, CM /card, BO «Уровень 3» — молчит о том, какой процесс читает данные.
- А — бот читает БД сам под app_bot (права — пачка 1). Минус: шире права бота.
- Б — внутренний эндпоинт API для бота. Минус: нужна аутентификация бот → API.
- Мнение: А.

Решит ШТАБ: whitelist /card = ACCESS_ADMIN_IDS до Б17; тема «Карточки» — переменная окружения;
action 'view', actor_role 'owner'; запись аудита не удалась → карточку не отправлять (P6 Fail-safe);
участник, открывший свою карточку, в privacy_audit_log не пишется (TI); живые проверки — А1 (участник) и А2 (owner).

## 7. Строки для STATE (ШТАБ)
- «И3: исследование docs/research/iter3.md (PR без мержа); открыты В1–В6; кандидаты D-43…D-48, дополнение D-22.»
- «iter3 З1: сверх списка — 11 файлов кода (лимит 3), причина — п.2 указаний.»

## 8. Прочитано
Обязательные: DESIGNER, STATE, AB, process/README, DEC, CANON-CHECK, research/iter2.md, BO, SC, P6, P5,
TI, CT, 17-author-panel, RG, CM. По необходимости: 99-legal, I3 (C.7, C.8, C.12), DEFECTS-FOUND
(последняя D-42), деревья apps/* через GitHub API. Сверх списка: MO, LS, M01, M06, M07, M09,
routers/consents.py, ET, apps/bot/bot/config.py, routes.tsx, docs/process/CODER.md.
Не открывал: 14-data-durability, M10, docs/decisions/DOCS-CANON.md.
