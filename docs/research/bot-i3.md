# bot-i3: /card и кнопка «📇 Карточка» (PLAN §5 п.12), З2
ИССЛЕДОВАНИЕ, 12.11.2026, @23bc377 — все пути по этому hash. Правило К. Область — apps/bot. Тексты — заглушки.
Сокращения: P6 = docs/architecture/06-participant-card.md, P8 = 08-working-group.md, P5 = 05 (Чек-Ап), OB = apps/bot/bot/outbox.py, AH = access_handlers.py, CF = config.py, APP = app.py, TX = texts.py, M13 / M14 / M15 = миграции 0013 / 0014 / 0015, RG = build/bot-commands-registry.yaml. Метки: [ШТАБ] = решил ШТАБ, К-5; [Автор] = К-6.

## 1. Как reply и кнопка находят участника
- Бот о своих постах в группе ничего не хранит: OB `_send_group` шлёт send_message и message_id отбрасывает; дальше только MARK sent_at. Таблицы «message_id → pid» нет. render.py — чистый рендер, к вопросу не относится.
- Шаблоны, по коду TX:
  - GROUP_WHO = «Участник #{num} (ID {tg_id}) → {link}»; {num} — 6 цифр или «—».
  - GROUP_REFLECTION = «[заглушка] Рефлексия · этап {s} · модуль {m} · день {d} · {time}\n{who}\n\n{body}».
  - GROUP_DAY2_ALERT = «[заглушка] День 2: пришёл, но не отправил.\n{who}».
  - Итог: {who} стоит до {body}, body отделён пустой строкой.
- Хранилище и миграция не нужны.
- Кнопка [ШТАБ]: callback_data «card:<short_no цифрами>»; pid в сообщения не выносим. Канон P8 §8.6: «Callback строго привязан к participant_id» — привязка через номер. Нажатие принимается только в WORK_GROUP_ID и от ACCESS_ADMIN_IDS; иначе callback.answer() без текста + лог без id.
- Окну КАРТОЧКИ: проверить UNIQUE short_no по миграциям 0002 / 0011 или models.py.
- {num} = «—»: кнопку под постом не ставить [предложение, ШТАБ-тех].
- Reply, по порядку: reply.from_user.id == bot.id (как AH) → (1) callback_data «card:» в reply.reply_markup → (2) [ШТАБ] «#» + цифры только в тексте до первой пустой строки → (3) «не найден».
- Body пишет участник, но он после пустой строки: подделка подписи в путь (2) не попадает. На ссылку tg://user?id не опираться.
- Ловушка: в теме форума сообщение формально reply на первое сообщение темы; AH `command_precheck` считает это «reply нет» — /card так же.

## 2. Права app_bot
- tg_user_registry: pid, tg_user_id, tombstoned_at (0009); short_no (0011); created_at (M13) — по докстрингам OB, M13.
- participant_state (M13): tz, stage_no, module_no, day_no, lifecycle_phase, status_flags, lives.
- measurements_log (M14): SELECT (pid, kind, occasion, checkup_zone, weight_kg, created_at). Не выданы: id, stage_no, checkup_answers, checkup_score, checkup_config_version, client_op_id.
- onboarding_form (M15): прав нет; по P6 §6.4 пол и самочувствие в карточку не входят.
- privacy_audit_log (M13): INSERT (actor_id, actor_role, action, participant_id) + USAGE последовательности; SELECT и RETURNING нет.
- Итог: на все поля P6 §6.4, для которых есть данные, прав хватает; блокера для пачки нет. Балл в карточке не показываем (§3) — GRANT на checkup_score не нужен. 0016 — только журнал списаний (§7).
- Сервер: alembic 0015 выкачен, main сервера 7547732 — по отчёту сервера 11.11.

## 3. Что видит owner (P6 §6.4, порядок секций как в каноне)
- Кто: подпись Р-15 как в постах (TX GROUP_WHO, GROUP_WRITE) + часовой пояс. ФИО, телефона, email, города, имени и username нет (Р-16, Р-15).
- Вес [ШТАБ]: как apps/api/app/routers/me.py (build_card): старт = первая строка kind body, текущий = последняя; один замер — оба значения одинаковые. Строк нет → «нет данных».
- Чек-Ап: только зона, балла нет. Канон P6 §6.4: «Чек-Ап-зона (старт → последняя, с пометкой улучшение/ухудшение)». Старт = первая строка kind checkup, последняя = последняя.
- Пометка, канон P5 §5.3 (зелёная 0–9, жёлтая 10–22, красная 23–45): сдвиг к зелёной — «улучшение», к красной — «ухудшение», та же зона — «без изменений»; один замер — пометки нет. Тексты пометок — заглушки. Коды зон в БД сверить по CHECK в M14.
- Этап, модуль.день: participant_state.
- Статус [Автор]: §9 В1.
- Жизни [Автор]: «осталось N» + строка-заглушка про журнал, §9 В2.
- Оплаты (Р-1), паузы (Р-6а), счётчик возвратов (источник не найден — не проверено): «нет данных».
- Дата регистрации: tg_user_registry.created_at.
- Фото нет (Р-3), настроек нет (Р-6).
- Строки participant_state нет → её поля «нет данных» (P6 Fail-safe, Л5; M13).
- Вне пачки (P6 §6.4–6.7): кнопка «📊 Полная Карта изменений», командные кнопки под карточкой, «одна карточка на участника, автоудаление 24 ч» (§6.5; iter3-2 §5 D-48). Бот не хранит message_id карточек — заменять старую нечем.

## 4. Порядок работы /card и нажатия 📇
1. Фильтр [ШТАБ]: /card — из любой темы WORK_GROUP_ID, автор в ACCESS_ADMIN_IDS; иначе игнор + лог без id (P8 Fail-safe; AH). Нажатие — §1.
2. Идентификатор: аргумент «#NNNNNN» → reply (§1) → ничего нет: «уточните идентификатор» (P6 Fail-safe).
3. pid по short_no, tombstoned_at IS NULL (SQL из M13); строки нет → «не найден», аудита нет.
4. Чтение: participant_state, measurements_log.
5. Аудит до отправки: INSERT privacy_audit_log (actor_id текстом, 'owner', 'view', pid), без RETURNING (M13). Ошибка → карточку не слать, заглушка «позже» [ШТАБ; P6 Fail-safe].
6. Карточка — только в тему «Карточки» (CARDS_TOPIC_ID), HTML, подстановки через html.escape. Канон P6 Fail-safe: «только в теме „Карточки“, только whitelist».
7. «Уточните идентификатор», «не найден», «позже» — ответом в тему вызова, без ПДн [ШТАБ]; для нажатия — текстом callback.answer [предложение, ШТАБ-тех].
Логи — без tg_user_id, pid, short_no и текста карточки (OB, AH).

## 5. Регистрация
- APP `build_dispatcher`: build_router, затем при access_enabled — build_access_router. Новый build_card_router(config, connect) — до роутера доступа (докстринг APP), при card_enabled; иначе один WARNING с именами переменных.
- CF: cards_topic_id (CARDS_TOPIC_ID через `_parse_int`); card_enabled = заданы BOT_DATABASE_URL, WORK_GROUP_ID, CARDS_TOPIC_ID, ACCESS_ADMIN_IDS.
- Команда: Command("card") + F.chat.type.in_({"group", "supergroup"}), как /access_grant в AH. Callback: F.data.startswith("card:"), как «acc:» в AH.
- handlers.py — только /start в личке; не трогаем. allowed_updates = dp.resolve_used_update_types() (APP): callback_query подхватится сам. connect(dsn) подменяется в тестах (APP, AH).
- Кнопка: OB `_send_group` получает reply_markup; `_deliver_group` передаёт его для обоих маршрутов GROUP_ROUTES (reflection_submitted → «Рефлексии», ladder_day2_alert → «Отчёты и активность»).
- CARDS_TOPIC_ID вне apps/bot [ШТАБ]: строки в infra/docker-compose.dev.yml и .env.example — Р0 Автора по команде ШТАБа перед выкатом (PLAN §6, урок 01.11). В карточки Агента эти файлы не входят; в «Запреты» — прямо. В «Живые проверки» — предусловие: тема «Карточки» создана, CARDS_TOPIC_ID задан в .env сервера.
- RG: /card — role [owner, moderator], audit_layer privacy, surface work_group_reply. Делаем owner [ШТАБ].

## 6. Нарезка [ШТАБ: две карточки, i3-1 → i3-2, обе РЕВЬЮЕР да]
- bot-i3-1: /card по #NNNNNN и reply. Создать bot/card.py (SQL, текст карточки, разбор идентификатора, префикс и сборка кнопки), bot/card_handlers.py, tests/test_card.py; изменить config.py, app.py, texts.py.
- bot-i3-2: кнопка под постами: outbox.py, texts.py, тесты outbox.
- Предложение [ШТАБ-тех]: обработчик нажатия «card:» сделать в i3-1 (тест — синтетическим callback), в i3-2 оставить только кнопку. Иначе окну i3-2 нужны card.py и card_handlers.py, а места нет.
- Подпись «Кто» в i3-1 собирать в card.py из TX (окно i3-1 OB не читает) [предложение, ШТАБ-тех].
- Окно i3-1, КБ: база 67,7 (DESIGNER 21,5; PACK 10,9; STATE 18,2; AGENT-BRIEF 17,1) + bot-i3.md ≈ 13 + DECISIONS 7,3 + CANON-CHECK 4,7 + P6 9,5 + config 7,0 + app 7,0 + AH 10,1 + bot/access.py 15,2 + texts 5,0 + tests/test_bot.py 4,6 + M13 4,7 + M14 9,0 = 164,8.
  - tests/test_access.py (21,8) в 170 не входит ни в каком составе с AH и access.py; образец сборки — test_bot.py (`_feed` через build_dispatcher). Решает ШТАБ.
  - Задетые тесты: test_bot.py — не ожидается (make_config без переменных → card выключен); тесты полного списка полей config — не проверено.
- Окно i3-2, КБ: база 67,7 + bot-i3.md ≈ 13 + DECISIONS 7,3 + CANON-CHECK 4,7 + OB 28,0 + tests/test_outbox_group.py 14,2 + tests/test_outbox.py 26,0 + texts 5,0 = 165,9.
  - bot/card.py (появится в i3-1, размер неизвестен) сверх 4,1 КБ не влезет: ШТАБ даёт выдержку — имя и сигнатуру сборки кнопки.
  - Задетые тесты: искать в test_outbox_group.py и test_outbox.py проверки аргументов send_message.
- P8 окнам не нужен — выдержки здесь.

## 7. Задача 0016 (вне пачки bot-i3) [Автор]
Журнал списаний жизней — отдельная задача с миграцией 0016: представление (VIEW) только со строками списаний и только с нужными полями, не payload целиком; app_bot — SELECT только на это VIEW, на participant_events ничего; РЕВЬЮЕР да.
не проверено: имя kind списания и поля его payload; задевает ли VIEW apps/api/tests/expected_tables.txt.
Туда же: схема журнала событий и privacy_audit_log (обязательность participant_id).

## 8. Надо дочитать и кандидаты DEFECTS
- Дочитать (окно i3-1, по необходимости): apps/api/app/routers/me.py (build_card) — образец «старт / текущий»; размер неизвестен.
- DEFECTS, решит ШТАБ: (1) M14, докстринг: балл боту не выдан с основанием «балл участнику не показываем», а карточку смотрит owner; (2) RG: /card role moderator — роль не определена (шапка P6).

## 9. Решения Автора 12.11 [К-6: Автор]
- В1. Статус — словарь в коде бота из двух слов: active → «Заглушка: активен», sleeping → «Заглушка: спящий». Любой другой код lifecycle_phase — как есть: «статус: <код>» через html.escape. «Нет данных» для статуса не писать: код есть, нет перевода. status_flags в карточку не выводить. Долг Б10 (шапка P6) остаётся открытым.
- В2. Вариант А с поправкой: «Жизни: осталось N» и строка «Заглушка: журнал списаний — позже» (не «нет данных»: списания в журнале есть, бот их не видит). Журнал — §7.
Вопросов Автору нет.

## 10. Прочитано (≈ 217,4 КБ; повторно — только PACK по старту З2)
- З1, обязательные 194,5: DESIGNER, PACK, STATE, AGENT-BRIEF, DECISIONS, CANON-CHECK, iter3-2, P6, P8, RG, M13, config, app, AH, render, handlers, OB.
- З1, по необходимости: M14 9,0 и M15 4,4 — в M13 прав на эти таблицы нет; test_bot.py 4,5 — как тесты собирают роутеры.
- З2: texts.py 5,0 — цитаты шаблонов §1.
- Не читал: P5 (§5.3 — со слов ШТАБа), me.py, access.py, тесты outbox и access (размеры — со слов ШТАБа).
