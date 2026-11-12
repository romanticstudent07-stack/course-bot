# bot-i3: /card и кнопка «📇 Карточка» (PLAN §5 п.12), З1
ИССЛЕДОВАНИЕ, 12.11.2026, @23bc377 — все пути ниже по этому hash. Правило К. Область — apps/bot. Тексты — заглушки.
Сокращения: P6 = docs/architecture/06-participant-card.md, P8 = 08-working-group.md, OB = apps/bot/bot/outbox.py, AH = access_handlers.py, CF = config.py, APP = app.py, M13 / M14 / M15 = миграции 0013 / 0014 / 0015, RG = build/bot-commands-registry.yaml.

## 1. Как reply и кнопка находят участника (вопрос а)
- Бот о своих постах в группе не хранит ничего: OB `_send_group` вызывает send_message и ответ Telegram (message_id) отбрасывает; после поста — только MARK sent_at. Таблицы «message_id → pid» нет, прав на такую запись у app_bot нет (докстринги OB, M13, M14).
- render.py — чистый рендер без БД и сети, к вопросу не относится.
- Заявки доступа — другое: AH зовёт access.find_by_message(conn, reply.message_id), это заявки Р-2 по tg_user_id. access.py не читал — не проверено.
- В самом посте есть подпись Р-15 «Участник #NNNNNN (ID N) → написать», ссылка tg://user?id=N (OB `_group_who`, номер zfill(6)). Точный шаблон GROUP_WHO и порядок who / body в GROUP_REFLECTION — не проверено (texts.py не читал).
- Вывод: хранилище и миграция не нужны.
  - Кнопка: идентификатор в callback_data. Канон P8 §8.6 и Fail-safe: «Callback строго привязан к participant_id». Образец — «acc:g:<id>» (AH). Предложение: «card:<short_no>» — номер уже виден в посте, pid в сообщения не выносим. Решает ШТАБ (К-5).
  - Reply, по порядку: (1) callback_data кнопки 📇 в reply.reply_markup (посты после bot-i3-2); (2) номер после «#» в подписи; (3) иначе «не найден». Перед этим reply.from_user.id == bot.id, как в AH.
  - Риск пути (2): body рефлексии пишет участник и может вписать чужую подпись; экранирование (OB `_esc`) не спасает. Снижение — брать номер только из части текста до body; зависит от шаблона. Старые посты без кнопки идут только путём (2).
  - Ссылка tg://user?id как источник: в каком виде она приходит боту в reply — не проверено живьём; не опираться.
- Ловушка: в теме форума любое сообщение формально reply на первое сообщение темы (id = thread_id); AH `command_precheck` считает это «reply нет». /card делает так же.

## 2. Права app_bot (вопрос б)
| Поле (P6 §6.4) | Источник | Право | Итог |
|---|---|---|---|
| Кто: часовой пояс | participant_state.tz | M13 | есть |
| Кто: ссылка, № | tg_user_registry: tg_user_id, short_no | 0009, 0011 (по докстрингам OB, M13) | есть |
| Вес старт → текущий | measurements_log, kind body: weight_kg, occasion, created_at | M14 | есть |
| Зона старт → последняя | measurements_log, kind checkup: checkup_zone | M14 | есть |
| Этап, модуль.день | participant_state: stage_no, module_no, day_no | M13 | есть |
| Статус | lifecycle_phase, status_flags | M13 | есть; слова — В1 |
| Жизни: осталось | participant_state.lives | M13 | есть |
| Жизни: журнал списаний | журнал событий | нет | В2 |
| Оплаты | таблицы нет (Р-1; Л8 отложен) | — | «нет данных» |
| Паузы | не построены (Р-6а) | — | «нет данных» |
| Счётчик возвратов | источник не найден — не проверено | — | «нет данных» |
| Дата регистрации | tg_user_registry.created_at | M13 | есть |
| Аудит | privacy_audit_log: INSERT 4 колонок + USAGE seq | M13 | есть; SELECT и RETURNING нет |
- measurements_log (M14): app_bot SELECT (pid, kind, occasion, checkup_zone, weight_kg, created_at). Не выданы: id, stage_no, checkup_answers, checkup_score, checkup_config_version, client_op_id.
- onboarding_form (M15): у app_bot прав нет — «пола и самочувствия в карточке нет»; по P6 §6.4 они не нужны.
- Блокера «0016» для состава P6 §6.4 нет. 0016 нужна, только если: (1) owner должен видеть балл — GRANT SELECT (checkup_score) ON TABLE measurements_log TO app_bot; (2) нужен журнал списаний — GRANT на журнал событий, список колонок не проверено (схему не читал).
- STATE@hash кончается 04.11 (alembic 0012): выкачены ли 0013–0015 на сервер — не проверено; нужно для живых проверок.

## 3. Что видит owner (вопрос в)
- P6 §6.4: «Чек-Ап-зона (старт → последняя, с пометкой улучшение/ухудшение)». Балла в P6 нет; M14 балл боту не выдаёт. Видит ли owner балл по 05 и I3 §C.7 — не проверено: в список окна не входили. Порядок зон (что лучше из green / yellow / red) — тоже 05, не проверено; без него пометку «улучшение / ухудшение» не делать.
- Р-16: ФИО, телефона, email, города нет — в P6 §6.4@hash уже убрано. Пол и самочувствие в карточку не входят (M15).
- Р-15: «Кто» — та же подпись, что в постах (переиспользовать OB `_group_who`); имя и username не берём.
- Р-1: «Оплаты» — «нет данных». Р-3: фото в карточке нет. Р-6: настроек нет. Р-6а: «Паузы» — «нет данных».
- «Нет данных» вместо падения — P6 Fail-safe, Л5; нет строки participant_state → «нет данных» (M13).
- Вес: одна строка body → старт есть, текущий «нет данных» [предложение, ШТАБ-тех].
- Вне пачки (P6 §6.4–6.7): кнопка «📊 Полная Карта изменений», командные кнопки под карточкой, «одна карточка на участника, автоудаление 24 ч» (§6.5; iter3-2 §5 D-48). Бот не хранит message_id карточек — заменять старую нечем.

## 4. Порядок работы /card (для карточек)
1. Фильтр: чат = WORK_GROUP_ID и автор в ACCESS_ADMIN_IDS; иначе игнор + лог без id (P8 Fail-safe; AH). Тема вызова — любая тема группы [предложение, ШТАБ-тех: P6 Fail-safe ограничивает место показа, не место команды].
2. Идентификатор: аргумент «#NNNNNN» → reply (§1) → нет ничего: просьба уточнить (P6 Fail-safe).
3. pid по short_no с tombstoned_at IS NULL (SQL из M13); нет строки → «не найден», аудита нет.
4. Чтение: participant_state (M13), measurements_log (M14).
5. Аудит: INSERT privacy_audit_log (actor_id текстом, 'owner', 'view', pid) без RETURNING (M13). Ошибка → карточку не слать, заглушка «позже» (ШТАБ; P6 Fail-safe).
6. Отправка в тему «Карточки» (CARDS_TOPIC_ID как message_thread_id), HTML, подстановки через html.escape.
Логи — без tg_user_id, pid, short_no и текста карточки (OB, AH).

## 5. Регистрация команды и callback (вопрос г)
- APP `build_dispatcher`: include_router(build_router), затем при access_enabled — build_access_router. Новый build_card_router(config, connect) подключать до роутера доступа (докстринг APP), при card_enabled; иначе один WARNING с именами переменных.
- CF: поле cards_topic_id (CARDS_TOPIC_ID через `_parse_int`); card_enabled = заданы BOT_DATABASE_URL, WORK_GROUP_ID, CARDS_TOPIC_ID, ACCESS_ADMIN_IDS.
- Команда: Command("card") + F.chat.type.in_({"group", "supergroup"}) — как /access_grant (AH). Callback: F.data.startswith("card:") — как «acc:» (AH); чужой → callback.answer() без текста + лог.
- handlers.py — только /start в личке; /card его не трогает.
- allowed_updates = dp.resolve_used_update_types() (APP): callback_query подхватится сам.
- connect(dsn) пробрасывается в роутеры и подменяется в тестах (APP, AH).
- Кнопка: OB `_send_group` получает reply_markup, `_deliver_group` передаёт его для обоих маршрутов GROUP_ROUTES (reflection_submitted → «Рефлексии», ladder_day2_alert → «Отчёты») — ровно две темы пачки.
- Вне apps/bot: compose передаёт боту переменные явно (докстринг CF) → строка CARDS_TOPIC_ID в infra/docker-compose.dev.yml и .env.example — для ШТАБА; файлы не читал.
- RG: /card — role [owner, moderator], audit_layer privacy, surface work_group_reply. Делаем owner (ШТАБ).

## 6. Нарезка (вопрос д)
Две карточки, обе РЕВЬЮЕР да (ПДн, аудит).
- bot-i3-1: /card по #NNNNNN и reply. Создать bot/card.py (SQL, текст, разбор идентификатора, префикс callback), bot/card_handlers.py, tests/test_card.py; изменить config.py, app.py, texts.py. Задетые тесты: test_bot.py — не ожидается (make_config без переменных → card выключен; `_feed` собирает через build_dispatcher); тесты полного списка полей config — не проверено.
- bot-i3-2: кнопка и callback. Изменить outbox.py, card_handlers.py, texts.py, тесты. Меняет вызов send_message в группе → правило Т: найти тесты bot-group-1, сверяющие аргументы send_message; имена файлов apps/bot/tests не проверено.
Порядок: i3-1 → i3-2 (callback использует card.py). Живая проверка — после выката 0013 и 0014.
Чтение окна КАРТОЧКИ: база 67,7 + bot-i3.md ≈ 13 + DECISIONS 7,3 + CANON-CHECK 4,7 + P6 9,5 + config 7,0 + app 7,0 + AH 10,1 + OB 28,0 + texts 5,0 + test_bot 4,5 = 163,8 КБ. P8, M13, M14 не нужны — выдержки здесь. Сверху нужны access.py и тесты outbox (размеры неизвестны); не влезут в 170 → два окна: i3-1 без OB, i3-2 без AH.

## 7. Надо дочитать (решает ШТАБ)
1. apps/bot/bot/texts.py — шаблоны GROUP_WHO, GROUP_REFLECTION (риск §1), место заглушек.
2. apps/bot/bot/access.py — is_admin_context, connect, CALLBACK_PREFIX, fmt_msk: что переиспользовать.
3. Список apps/bot/tests и тесты bot-group-1 — «Задетые тесты» i3-2.
4. docs/architecture/05-checkup.md и normative/I3-wave-c.md §C.7 — балл для owner, порядок зон.
5. Схема журнала событий и privacy_audit_log — В2 и обязательность participant_id.

## 8. Кандидаты DEFECTS
- M14, докстринг: балл боту не выдан с основанием «балл участнику не показываем», а карточку смотрит owner.
- RG: /card role moderator — роль не определена (шапка P6).

## 9. Вопросы Автору (К-4)
В1. Статус участника в карточке. Канон: проверено P6 §6.4 и шапка P6 — противоречит сам себе: §6.4 требует слова «активен / пауза / блок / ждёт оплаты / спящий / архив», шапка: «Входящий долг из Б10 (проекция состояния в карточный status) не закрыт». А) показывать служебный код фазы как в БД — быстро и честно, но не словами; Б) строку статуса не показывать, пока нет таблицы перевода. Мнение: А.
В2. Журнал списаний жизней. Канон: проверено P6 §6.4 — «Жизни: осталось + журнал списаний»; противоречит коду: M13 даёт боту только число жизней. А) сейчас только «осталось N», журнал — отдельной задачей с миграцией 0016; Б) сначала 0016, потом карточка целиком. Мнение: А — пачка не ждёт.

## 10. Прочитано (≈ 212,4 КБ)
Обязательные, 194,5: DESIGNER 21,5 — окно, 3 запроса; PACK 10,9 — формат; STATE 18,2 — кончается 04.11; AGENT-BRIEF 17,1 — запреты, логи; DECISIONS 7,3 — Р-15, Р-16; CANON-CHECK 4,7 — К-4; iter3-2 12,9 — Л2, Л3, Л5, Л6; P6 9,5 — §6.2, §6.4, Fail-safe; P8 11,5 — §8.2, §8.6; RG 7,3 — /card; M13 4,7 — права и SQL; config 7,0 — темы, whitelist; app 7,0 — сборка роутеров; AH 10,1 — образец; render 12,5 — без БД; handlers 4,3 — /start; OB 28,0 — message_id не хранится.
По необходимости: M14 9,0 — в M13 прав на measurements_log нет; M15 4,4 — то же для onboarding_form; test_bot.py 4,5 — как тесты собирают роутеры.
