---
file: normative/I3-wave-c.md
patch: I3-WAVE-C
title: "И3 — Волна C: Refund + Photo + Чек-Ап + Красная зона"
status: закрыт
precedence: 3
doc_version: "consolidated v3.7-i3"
parent_doc_version: "consolidated v3.6-i2"
depends_on: [I1-WAVE-A, I2-WAVE-B]
contains: [meta, refund_saga, refund_details_retention, legal_refund Д-25…Д-28, photo_ingest_saga, photo_erasure, export_worker, checkup_config, red_zone_templates, red_flags_protocol, fz323_terminology_blacklist, revert_contract, legal_pack_i3, capability additions, hard_confirm additions, ci_checks_i3, deferred_from_i3, audit_additions_i3, RISK-L-11…15, legal clarifications, fail-safe, yaml]
---

# ПАТЧ И3 — ВОЛНА C: REFUND + PHOTO + ЧЕК-АП + КРАСНАЯ ЗОНА

> **Канонический источник старшинства** — [README.md](README.md), раздел «Две оси: порядок присоединения ≠ ступень старшинства». Цепочка ниже в этом файле — порядок **присоединения**, а не ступень старшинства. Ступень старшинства: `корпус v3 → И1 → И2 → И3 → И4 → Б17 → SEAM-PATCH-1 → ERRATA-UNIFIED (высшая)`.

> **Переопределено/дополнено ERRATA-UNIFIED.** Реестр фраз hard-confirm, на который И3 опирается в `revert_contract` и refund saga, сохранён нормативно (E3): двухшаг и фраза — слои, а не альтернативы. Уточнение уведомления третьих сторон (`sh21_third_party_notification`) усилено ADD3; формулировка для участника о собственном сроке хранения PSP (до 5 лет по 115-ФЗ) добавлена A3 ERRATA — статус текста `pre-legal-review`, блокирует прод. Boot-gate по `full_backup_rotation_cycle` (ADD5, NOTE2) связан с отсрочками стирания И3: при подстановке брать более строгую границу A4 с учётом WAL. Три несовместимости патча Б17 с И3 (`/erasure_finalize_before_cooling_off` против отсрочки 14 дн., автоэскалация в Red Zone за 60 сек, роли `finance`/`moderator`) единым ERRATA-слоем **не рассмотрены** и остаются решением Автора; до него действуют более строгие требования И3. См. [errata-unified.md](errata-unified.md), [B17-admin-panel-patch.md](B17-admin-panel-patch.md), [seam-patch-1-onboarding.md](seam-patch-1-onboarding.md).

Третье звено нормативного стека: `корпус v3 → И1 → И2 → **И3** → И4 → Б17 → ERRATA-UNIFIED → SEAM-PATCH-1`. Патч применяется поверх `consolidated v3.6-i2` и присваивает корпусу версию `consolidated v3.7-i3`. Зависимости объявлены явно: без И1 (правовой фундамент, инварианты I-1…I-6, реестр согласий, `role_capability_matrix`) и без И2 (`participant_state` как read-only проекция, outbox/DLQ, три семантики паузы, `publish_epoch`) записи этого патча не читаются.

Волна C переводит из прозы в контракты четыре защитных контура — возврат денег, приём фотографий, Чек-Ап и Красную зону. У всех четырёх общий признак: цена ошибки здесь либо денежная, либо связанная с персональными данными и безопасностью участника, поэтому каждый контур оформлен как сага с шагами, ключами идемпотентности и явной политикой отката, а не как обработчик одного события. Второй сквозной приём патча — гейты: без согласия C5 фото не принимается, без одобрения Legal текст красной зоны не публикуется, без ко-подписи владельца заморозка по фроду не превращается в стирание.

## C.1. Refund Saga (Б16) — полная реализация

Возврат — многошаговая сага с координатором `refund_orchestrator` и одним ключом на весь возврат: `refund:{payment_id}`. Шагов пять, нумерация с нуля, у каждого шага собственный ключ идемпотентности вида `refund:{payment_id}:step_N`.

Шаг 0 — предполётная заморозка. До любого обращения к платёжному провайдеру участник атомарно, через событие `refund.preflight_freeze`, получает `visibility = out_of_scope` и `modifier = freeze_refund`. Смысл шага в том, что участник не должен продолжать движение по курсу, пока идёт расчёт возврата, и не должен видеть промежуточных состояний. Если шаг 0 не удался, сага не начинается вообще: состояние остаётся нетронутым.

Шаг 1 — фиксация намерения: событие `refund.pending` с суммой и причиной. Внешне для участника ничего не меняется, потому что заморозка уже стоит с шага 0.

Шаг 2 — вызов PSP с таймаутом 60 секунд, три попытки с экспоненциальной задержкой 5/15/45 секунд. Ключевое решение: по таймауту сага не откатывается и не считается провальной — она остаётся в `refund_pending`, а добор делает sweeper на следующем цикле. Отказ провайдера переводит в `refund_declined`, и доступ при этом не возвращается — он на этом шаге и не отбирался.

Шаг 3 — единственный шаг, который меняет мир участника: уведомление об откате (`revert_notice` в Б14, по R257 и R258/R259 — без мутации данных) плюс компенсирующий шаг в Б13 на отзыв доступа к купленному контенту, затем `refund.completed`. Отдельно описан самый неприятный сценарий: деньги вернулись, а отзыв доступа не удался. Это `refund_partial` — он уходит в очередь `pending_ops_review` и поднимает алерт в админ-топик и обоим владельцам. Автоматического «дожима» здесь нет намеренно, потому что дальше расходятся деньги и права доступа.

Шаг 4 — снятие заморозки, но только при успешном закрытии саги. При `refund_partial` флаги `out_of_scope` и `freeze_refund` остаются висеть до ручного разрешения владельцем.

Откат финализированного возврата не поддерживается. Компенсация — ручной перевыпуск: владелец создаёт новый заказ, участник платит заново, возникает новый `payment_id` и новая сага, а связь с прошлым платежом хранится как `previous_payment_id` в примечаниях. Фраза жёсткого подтверждения `ОТКАТИТЬ ВОЗВРАТ` введена ещё в И2. Тем же принципом «никакого наследования состояния» решён повторный checkout после отказа: новая карта оплаты с новым `payment_id`, а от прошлой попытки остаётся только ссылка с причиной отказа.

Два сквозных ограничителя. Первый: неоплата в срок ведёт в `sleeping`, и сага возврата никогда не переводит участника в `banned_*` — состояний с таким именем после Р477 (И2) не существует, чек уже стоит. Второй: `/finance_summary [period]` отдаёт только агрегаты (`confirmed`, `proof_submitted`, `refunded`) в режиме read-only. Плюс Ш14: окно сверки платежа переехало в само событие полем `n_hours_reconciliation_window`, чтобы число не оседало в шаблоне сообщения.

Надёжность возврата дополнена сверкой с провайдером: `refund_reconciliation_watcher` раз в час опрашивает статусы возвратов за последние 7 дней и при расхождении алертит и замораживает новые возвраты по этому `payment_id`.

## C.2. Retention реквизитов возврата

Банковские реквизиты (IBAN, имя, БИК) живут в отдельной таблице `refund_details`, физически отделённой от PII-профиля, и хранятся три года — это налоговое требование (НК РФ ст. 23 п. 1 подп. 8), а не продуктовое решение. Из этого следует главная развилка стирания: по запросу на удаление стирание профиля откладывается на 14 дней для финализации расчётов, а после профиль стирается, но `refund_details` остаются — вместо `pid` в них подставляется `system_ref`. Всё пишется в `privacy_audit`.

Порядок приоритетов уточнён отдельной записью аудита: сначала период охлаждения на исходный запрос стирания (24–72 часа), затем — только если есть активный возврат — отсрочка 14 дней; при отсутствии активного возврата стирание идёт сразу.

## C.3. Правовой контур возврата (Д-25…Д-28)

Четыре записи, все со статусом `pre-legal-review`, то есть по шлюзу И1 они блокируют prod-launch до вычитки юристом.

Д-25 фиксирует три возможных инициатора возврата несовершеннолетнему: сам участник, законный представитель по заявлению или оператор по своей инициативе при `underage_detected`. Проверка представителя — нотариальное подтверждение либо верифицированный скан документа. Формулировка оператора отдельно уточнена в правовых пояснениях: оператор «устраняет нарушение условий приёма участника (возраст)», а не «отменяет договор в одностороннем порядке» — разница здесь юридическая, а не стилистическая.

Д-26 задаёт сетку возврата по ЗоЗПП: до начала этапа — 100% (ст. 32 плюс оферта), в ходе этапа — pro rata по формуле `amount * (remaining_days / total_stage_days) − actual_expenses` (ст. 32), при некачественной услуге — 100% (ст. 29). Предельный срок ответа — 10 дней (ст. 31).

Д-27 описывает отзыв согласия C2 посреди этапа: немедленная авто-пауза с `reason_code=consent_withdrawn`, запуск саги возврата по пути ст. 32, удержание фактически понесённых расходов и уведомление участника с расшифровкой.

Д-28 вводит презумпцию приёмки: после оказания услуги бот отправляет электронный акт, и если мотивированного отказа нет три дня, услуга считается принятой; всё в append-only журнале `service_acceptance_log`. Две существенные оговорки: презумпция не отменяет ст. 32 ЗоЗПП (право отказаться от продолжения услуги сохраняется) и не применяется к несовершеннолетним — там требуется письменное подтверждение законного представителя.

## C.4. Photo Ingest Saga (Б15) — полная реализация

Приём фото — сага из восьми шагов с ключом `photo_ingest:{client_op_id}` и жёстким гейтом на входе: без согласия C5 (`photo_consent`, R318) эндпоинт отвечает 403, то есть файл не попадает даже в staging.

Дальше недоверенный файл проходит четыре фильтра, прежде чем стать объектом системы. Шаг 1 — pre-signed PUT в staging-бакет по ссылке с TTL 5 минут. Шаг 2 — проверка magic bytes: первые 16 байт сверяются с заявленным MIME, при расхождении файл отклоняется, staging чистится, пишется событие безопасности. Шаг 3 — белый список MIME (`jpeg`, `heic`, `png`, `webp`), причём `image/svg+xml` заблокирован жёстко, поскольку SVG — контейнер для скриптов, а `tiff`, `bmp`, `gif` отклоняются с сообщением участнику. Шаг 4 — снятие всего EXIF, включая GPS, модель камеры и таймстемпы; результат обязательно перепроверяется повторным разбором изображения, и при обнаружении остатков метаданных файл отклоняется с записью в `security_audit`.

Шаги 5–8 — нормализация и фиксация: перевод в progressive JPEG не длиннее 2048 px по большей стороне с качеством 85; вычисление sha256 и перенос в целевой путь `pii/photos/RU/{pid_bucket}/{pid}/{event_id}/{side}.jpg` с SSE-KMS, версионированием и тегом региона, с записью `blob_ref`; удаление из staging (при неудаче — оставить сборщику мусора); событие `photo.ingest_completed` через outbox.

Хвосты закрыты двумя механизмами. Сборка мусора: lifecycle-правило гасит объекты staging старше 24 часов, метрика `staging_orphan_rate` алертит при превышении 1%. Retention: через 12 месяцев после последней активности участника `photo_retention_worker` вешает тег `to_delete`, а фактическое удаление делает lifecycle-политика. Локализация усилена до отказа: префикс ключа `pii/photos/RU/`, обязательный тег региона, кросс-региональная репликация — `HARD_ERROR`, проверка политики бакета в CI, плюс одноразовый воркер `legacy_region_tag_backfill` для старых объектов.

## C.5. Стирание фото и подписанные ссылки

R334 отвечает на вопрос, который обычно и ломает «право на забвение» в объектных хранилищах, — версии. `erasure_blob_refs(pid)` отдаёт список ключей вместе со всеми `version_id`, и по каждому вызывается `DeleteObjectVersion`; факт стирания уходит в `erasure_blacklist` из И1/Д-18, а при восстановлении из бэкапа стирание переприменяется до открытия сервиса.

Отсюда следует разделение режимов Object Lock (R335): на бакетах с фото блокировка отключена принудительно, иначе стирание физически невозможно, а на бакетах журналов аудита стоит `COMPLIANCE` (WORM). Обе политики проверяются до деплоя.

Подписанные ссылки: чтение фото — 5 минут, экспорт — 15 минут, загрузка — pre-signed PUT, на чтении `Referrer-Policy: no-referrer`.

## C.6. Экспорт (DSAR + бот) — единый worker

Один воркер обслуживает продуктовый экспорт из бота (`/export {kind}`), запрос из Mini App (`POST /export/request`) и правовой DSAR — это сознательное решение против расхождения форматов между «выгрузкой для себя» и «ответом субъекту данных».

Формат по умолчанию — JSON плюс XLSX с текстовой типизацией; CSV выдаётся только по явному требованию, потому что CSV не несёт типов и провоцирует инъекции формул. Защита для CSV описана: ведущие символы `=`, `+`, `-`, `@`, табуляция и возврат каретки экранируются префиксом `'`.

Фото в выгрузке обезличиваются по имени (`photo_{event_id_short8}.jpg`), а соответствие полному `event_id`, исходному виду и sha256 лежит в manifest.json с общей контрольной суммой. Доставка: файлы до 10 МБ — через `sendDocument`, крупные — подписанной ссылкой на 15 минут с `Content-Disposition: attachment`. Каждая выгрузка пишет `data_export_event` в слой `privacy_audit`.

R299 разделяет два канала, которые легко спутать: самостоятельная выгрузка участником (152-ФЗ ст. 14, доступ субъекта) и выгрузка оператором по конкретному `pid` — только владельцем, через бота, с обязательной причиной (152-ФЗ ст. 20, ответ оператора); для нерезидентов сюда же мапится GDPR Art. 15.

Ш21 добавляет то, о чём при стирании обычно забывают, — уведомление третьих сторон, которым данные уже передавались. Актуальный список: PSP (для отмены рекуррентных списаний) и уведомления Telegram, про которые в исходнике сказано, что наших ПДн они не хранят. Уведомление PSP идёт вызовом `/notify_erasure {payment_ref}` в режиме best-effort с логированием. Правовое основание: GDPR Art. 19 для нерезидентов, 152-ФЗ ст. 20 для резидентов. Формулировка уточнена отдельно: PSP уведомляется, а не обязывается удалить, и участнику это сообщается прямо — у провайдера собственный retention (115-ФЗ, 5 лет).

## C.7. Чек-Ап (Б5) — полная реализация

Конфигурация Чек-Апа версионируется append-only в `checkup_config_versions`, где вместе с порогами и зонами хранится `legal_review_status`. Владение разделено: пороги правит владелец, тексты жёлтой и зелёной зон — владелец с UX-ревью, а тексты красной зоны требуют одобрения Legal **до** публикации.

Публикация идёт командой `/publish_checkup_config {version_id}` и цепляется к механизму `publish_epoch` из И2 (Р489): инкремент эпохи, рассылка в админ-топик, действующие участники доигрывают текущую эпоху на старом конфиге, новые старты берут новый. CI-чек запрещает публиковать версию, в которой хоть один текст красной зоны ждёт юридической вычитки.

Скоринг считает бот и публикует событие `checkup.scored(pid, epoch, zone, aggregate, signal_ids[])`. Участник видит только зону, не сырой балл (R306/R307), а зона в событии фиксируется на момент вычисления и позже не переинтерпретируется — это защита от «переоценки прошлого» при смене порогов. Зон три: зелёная (юридическая вычитка не требуется), жёлтая (рекомендуется), красная (обязательна, с гейтом `verified_by_legal_block`).

Периодичность задаётся перечислением: на каждом этапе, на каждом N-м этапе или по ручному запуску владельцем. Определение этапа расширено: массив опросов, где у каждого элемента есть вид (обычный или чек-ап) и опциональная ссылка на конфиг, плюс перечисление способов завершения этапа — по времени, по задаче, открытый. Открытый опрос этапа запускается внутренним действием Б14 по событию `stage_completed`.

Отдельный механизм — правка базовой линии: `/override_baseline {pid} {field} {new_value} {reason}`, только владелец, причина обязательна и попадает в `privacy_audit`. Разделены две базы: физическая (значение онбординга, неизменяемое) и эффективная (текущее значение после правок); каждая правка пишется в `baseline_override_log` и инвалидирует кэш событием `baseline_override` в Б10.

Дополнение аудита разводит два типа изменения конфигурации, которые нельзя применять одинаково: изменения, критичные для безопасности, применяются задним числом немедленно, с жёстким подтверждением `ПРИМЕНИТЬ ЗАДНИМ ЧИСЛОМ` и записью в приватностный аудит, а обычная калибровка — только вперёд.

## C.8. Красная зона (Д-09, Д-10)

Шаблон красной зоны не может существовать без четырёх обязательных элементов: пометки `verified_by: legal_block`, фиксированного заголовка «Это не медицинский совет», тела со статусом `approved` и кнопки «Пересмотр решения Автором», создающей обращение с тегом `red_zone_review`. Каждый показ пишется в append-only `red_zone_show_log` вместе со снимком агрегата и эпохой, хранение — бессрочное.

Отдельным правилом запрещено автоматическое связывание двух разных механизмов: красная зона — это аномалия Чек-Апа, а Red Flags — лемма-скрининг сообщений; эскалация из одного в другое возможна только вручную владельцем.

## C.9. Протокол Red Flags (Д-11)

Сканер работает по любому пользовательскому тексту (рефлексии, обращения в поддержку, ввод из Mini App), использует лемма-матчер с весами и версионируемый источник лемм из `legal_pack`. Цель по задержке — не более 60 секунд от приёма сообщения, и он вынесен в отдельный сервис так, чтобы его падение не блокировало основной поток.

При срабатывании в течение 60 секунд происходит четыре вещи: участник переводится в `sleeping` через `author_pause` с причиной `red_flag`, отправляется одобренный юристом текст экстренной помощи, поднимается алерт обоим владельцам, и всё это фиксируется в append-only `red_flag_event` с перечнем сработавших лемм и весом. Срок реакции владельца — 24 часа; при ложном срабатывании — снятие паузы и отметка `false_positive`, при подтверждении — эскалация по правовому протоколу.

Требования к самому тексту заданы жёстко и с двух сторон. Он обязан содержать круглосуточный телефон доверия, чат-линии психологической помощи, короткую инструкцию что делать, прямое раскрытие факта, что бот поставлен на паузу, и подсказку о самостоятельном действии. Ему запрещены медицинские советы, диагнозы и упоминания лекарств, а также обещания вида «мы Вам ответим», «ждите», «скоро» — то есть всё, что заставляет человека в остром состоянии пассивно ожидать ответа. Текст помечен `pre-legal-review`, и отдельным пунктом зафиксировано, что Legal начинает его готовить с самого старта И3, чтобы к интеграции кода в И4 он был одобрен. Доля ложных срабатываний измеряется метрикой `red_flags_false_positive_rate` и раз в месяц пересматривается Legal для калибровки лемм.

Рядом стоит терминологический запрет по ФЗ-323 (Д-12): версионируемый список диагнозов по МКБ-10, названий лекарств и врачебных назначений, которым проверяются все исходящие тексты Чек-Апа, красной зоны, Red Flags и рефлексий; попадание в список блокирует релиз.

## C.10. Revert (Б13) — без мутации данных

Откат этапа — это событие `revert_notice(pid, from_stage, to_stage, at)`, которое меняет только видимую границу материала. Данные не мутируются, все `stage_completed` остаются в журнале событий, участник получает уведомление через Б9 (текст переносится в И4), а для возврата денег тот же откат вызывается компенсирующим шагом из шага 3 саги возврата.

## C.11. Дополнения Legal Pack (Д-20, Д-21, F1)

Д-20 фиксирует требования к облаку: SSE-KMS для фото обязателен, шифрование уровня приложения рекомендовано, крипто-шреддинг рекомендован при масштабе свыше тысячи участников или при наличии бюджета.

Д-21 разделяет судьбу рефлексий по наличию согласия C6: без него текст исключается из корпуса к концу жизненного цикла и не используется в аналитике (запрет реализован фильтром представления), с ним допустимы только внутренние агрегаты, а выдача сырого текста наружу и передача третьим лицам запрещены.

F1 описывает обезличивание при системном или платёжном фроде: до правового дедлайна участник переводится в `frozen=true` на 14 суток (Д-19 из И1), апелляция идёт через поддержку с меткой `fraud_appeal`, а превращение заморозки в стирание требует ко-подписи владельца с фразой `УТВЕРДИТЬ ФРОД`. Основание — ст. 6 ч. 1 п. 7 152-ФЗ, защита интересов оператора.

## C.12. Права, подтверждения, CI и переносы

Матрица прав получает десять записей: владелец инициирует возврат без жёсткого подтверждения, но ручной перевыпуск — только с ним; публикация конфигурации Чек-Апа закрыта гейтом одобрения Legal; правка базовой линии требует причины и пишется в приватностный аудит; реакции на пересмотр красной зоны и на Red Flags имеют SLA 24 часа. Роль `finance` может инициировать возврат, но не может делать ручной перевыпуск. Модератор видит зону Чек-Апа только в агрегате и не видит сырой балл.

Новых фраз жёсткого подтверждения три: `ПРИМЕНИТЬ ПОРОГИ`, `ИЗМЕНИТЬ БАЗУ`, `УТВЕРДИТЬ ФРОД` (плюс `ПРИМЕНИТЬ ЗАДНИМ ЧИСЛОМ` из дополнений аудита).

CI-чеков восемь, и они закрывают именно те места, где ошибка не видна на глаз: идемпотентность каждого шага саги возврата, проверка magic bytes до обработки (тест на SVG в одежде JPEG), отсутствие Object Lock на бакетах фото, запрет кросс-региональной репликации, предрелизное сканирование по чёрному списку ФЗ-323, гейт юридической вычитки текстов красной зоны, экранирование CSV и сохранность `refund_details` при стирании участника.

В И4 переносится всё, что относится к текстам и клиентской части: сообщения саги возврата и ручного перевыпуска, ошибки загрузки фото, тексты зон, экстренный текст Red Flags, акт приёмки по Д-28, расшифровка по Д-27; из Mini App — инициация возврата, загрузка фото с прогрессом, панель «Мои согласия» вместе с кнопкой отзыва C5, интерфейс правки базовой линии, показ модального окна красной зоны и кнопка выгрузки «Мои данные»; из тем и рассылок — трансляция публикаций в админ-топик и маршрутизация алертов Red Flags и красной зоны.

Реестр рисков продолжен пятью записями: утечка ПДн через свободный текст причины при правке базы (детектор ПДн и сканирование по чёрному списку, реализация в И4), участники старой эпохи на устаревшем конфиге со связанным багом (закрыто разделением типов изменения конфигурации), осиротевшие файлы staging при аварийном завершении саги (сборка мусора и метрика), ночные срабатывания Red Flags против SLA 24 часа (высокая критичность — закрывается круглосуточной линией и прямым раскрытием паузы в тексте) и медленное снятие EXIF под нагрузкой (наблюдение за p95 и переезд на libvips при превышении 30 секунд).

## 🛡 И3 — Fail-safe

Деньги: ни один шаг возврата не выполняется дважды — ключ на сагу и ключ на каждый шаг. Таймаут PSP не эскалируется в откат: сага остаётся в `refund_pending` и добирается sweeper-ом, то есть по умолчанию система предпочитает задержку двойному действию. Часовая сверка с провайдером ловит расхождения и замораживает новые возвраты по спорному платежу. Частичный отказ (деньги ушли, доступ не отозван) не разрешается автоматически никогда: заморозка держится, задача встаёт в очередь владельца, алерт идёт в два адреса. Финализированный возврат не откатывается — только ручной перевыпуск с новым `payment_id`.

Данные: недоверенный файл отсекается до входа в систему тремя независимыми проверками (magic bytes, белый список, жёсткий запрет SVG), EXIF снимается с обязательной верификацией результата, то есть отсутствие метаданных подтверждается, а не предполагается. Staging самоочищается по lifecycle даже при падении саги, доля сирот измеряется. Локализация не полагается на код приложения: репликация за пределы RU запрещена политикой бакета и проверяется в CI. Стирание учитывает все версии объектов и переприменяется после восстановления из бэкапа. Object Lock разведён по назначению бакетов, иначе стирание и WORM-аудит взаимно исключали бы друг друга.

Безопасность участника: сканер Red Flags изолирован — его падение не блокирует основной поток, но и его срабатывание не зависит от готовности остальной системы. Текст экстренной помощи ограничен с двух сторон: обязателен круглосуточный контакт и раскрытие факта паузы, запрещены медицинские советы и любые формулировки, побуждающие пассивно ждать ответа. Красная зона не публикуется без одобрения Legal — это конфигурационный гейт, а не договорённость. Автоматическое перетекание красной зоны в Red Flags запрещено правилом.

Правовой контур: записи Д-25…Д-28, F1 и уточнения по Ш21 помечены `pre-legal-review`, что по И1 удерживает prod-launch до вычитки. Презумпция приёмки самоограничена дважды — ст. 32 ЗоЗПП и исключением для несовершеннолетних. Реквизиты возврата отделены от профиля, чтобы налоговое хранение трёх лет не превращалось в отказ от стирания профиля, а порядок «охлаждение → отсрочка расчётов → стирание» задан явно.

Состояния: возврат не может создать «бан» — Р477 удалил `banned_*`, и чек из И2 покрывает этот путь.

## ⚠ Открытые стыки (перенесены как есть, не исправлены)

Согласие `C5` здесь — фото (`R318`), а в юрблоке `C5` — трансграничная передача; коллизия нумерации, унаследованная от И1, получает второе подтверждение, и рядом появляется `C6` (рефлексии в Д-21) — единый реестр C0–C6 обязателен. Отзыв C5 упомянут только как кнопка в переносе на И4: серверная семантика отзыва (что происходит с уже загруженными фото) не описана нигде.

Авто-пауза в Д-27 и в Red Flags ставится как `author_pause`, но в И2 `author_pause` определена как ручное действие владельца, а `reason_code`/`reason` требуют расширения перечисления, иначе срабатывает чек `no_free_text_shadow_reason`. При этом правило `no_auto_escalation_to_red_flags` объявляет ручную эскалацию единственной, тогда как сам протокол Red Flags действует автоматически — противоречие внутри одного файла.

Публикация конфигурации Чек-Апа описана дважды и по-разному: `publish_flow` говорит «действующие доигрывают на старом конфиге» (только вперёд), а `audit_additions_i3.config_change_kind_split` вводит немедленное применение задним числом для критичных к безопасности изменений. Второе не вычеркивает первое.

Роль `finance` используется в правах и в `/finance_summary`, но не определена ни в глоссарии, ни в матрице И1; роль `moderator` получает доступ к зоне Чек-Апа без указания правового основания. Состояния `refund_pending`, `refund_declined`, `refund_partial` и флаг `frozen` вводятся без контракта и отсутствуют в FSM из И2. Артефакт `F2` упомянут как эталон критичности, но не определён.

Полный перечень дефектов исходника — в [../appendix/D-source-defects.md](../appendix/D-source-defects.md) (реестр D-01…D-31), раздел «И3 — Волна C». Ранее этот перечень был долгом в `_WIP-architecture-split.md`; тот файл историчен и как источник не используется.

## YAML — ПАТЧ И3, Волна C

```yaml
# =============================================================
# ПАТЧ И3 — ВОЛНА C: REFUND + PHOTO + ЧЕК-АП + КРАСНАЯ ЗОНА
# Версия документа: consolidated-v3.6-i2 → v3.7-i3
# Дата: 2026-07-24
# =============================================================

meta:
  patch_id: I3-WAVE-C
  parent_doc_version: consolidated-v3.6-i2
  new_doc_version: consolidated-v3.7-i3
  applied_at: "2026-07-24"
  depends_on: [I1-WAVE-A, I2-WAVE-B]

# -------------------------------------------------------------
# REFUND SAGA (Б16) — ПОЛНАЯ РЕАЛИЗАЦИЯ
# -------------------------------------------------------------

refund_saga:
  overview:
    kind: multi_step_saga
    coordinator: refund_orchestrator
    one_shot_key: "refund:{payment_id}"
    steps: 5

  step_0_preflight_freeze:
    action: |
      Atomically set on participant_state (via event):
        visibility = out_of_scope
        modifier = freeze_refund
      Event: refund.preflight_freeze
    idempotency_key: "refund:{payment_id}:step_0"
    on_failure: abort saga; state unchanged
    covers: [Р496]

  step_1_refund_pending:
    action: |
      INSERT event refund.pending(pid, payment_id, amount, reason)
      participant sees no external change yet (freeze already set)
    idempotency_key: "refund:{payment_id}:step_1"
    covers: [Р421 core]

  step_2_psp_call:
    action: call PSP API /refund
    timeout: 60s
    retry_policy:
      attempts: 3
      backoff: exponential [5s, 15s, 45s]
      on_timeout: leave in refund_pending; sweeper retries next cycle
    on_psp_declined: transition to refund_declined; NO revert of access
    idempotency_key: "refund:{payment_id}:step_2"
    covers: [Р421 psp path]

  step_3_revert_access_and_notice:
    action: |
      - emit revert_notice(pid, stage_id, at) → Б14 (R257, R258/R259: no data mutation)
      - emit compensating step to Б13: revoke access to purchased content
      - emit refund.completed
    on_partial_failure:  # PSP OK, but revert failed
      transition: refund_partial
      route: pending_ops_review (owner queue)
      alert: admin_topic + both owners
    covers: [Р439, Р441, R257 refund_notice, Р442]

  step_4_unfreeze_or_review:
    action: |
      IF refund.completed:
        clear visibility=out_of_scope
        clear modifier=freeze_refund
      IF refund_partial:
        KEEP freeze flags until manual resolution by owner
    covers: [Р496 unfreeze]

  rollback_policy:
    finalized_refund_rollback: not_supported
    compensation: manual_reissue
    manual_reissue_flow:
      - owner creates new order manually
      - participant pays fresh
      - new payment_id, new saga
      - link to previous_payment_id in notes
    hard_confirm_phrase: "ОТКАТИТЬ ВОЗВРАТ"  # уже в И2
    covers: [Р465, Р467]

  new_card_after_decline:
    contract: |
      Повторный checkout после declined = new payment card with new payment_id.
      UI shows link "предыдущая попытка отклонена, причина X"
      No state inheritance from previous attempt.
    covers: [Р457, Р458]

  saga_no_banned_states:
    rule: "неоплата в срок → sleeping. Refund saga никогда не переводит в banned_*"
    ci_check: covered by И2 R477 guard
    covers: [Р477 refund scope]

  finance_summary:
    command: /finance_summary [period]
    access: owner, finance role
    output: read_only aggregates {confirmed, proof_submitted, refunded}
    audit_layer: operational
    covers: [Р491]

  sh14_payment_confirmation_window:
    field_in_event: n_hours_reconciliation_window
    payload_include: [pid, payment_id, stage_name, expected_amount, n_hours]
    covers: [Ш14]

refund_details_retention:
  storage:
    table: refund_details
    columns: [payment_id, iban, name, bank_bik, created_at, source_pid]
    retention: 3_years  # НК РФ ст.23 п.1 подп.8
    separate_from_pii_profile: true
  erasure_interaction:
    on_participant_erasure_request:
      profile_erasure_deferred_by: 14d  # финализация расчётов
      after_14d_or_completion: profile erased, refund_details kept (pid replaced with system_ref)
    audit_layer: privacy_audit
  covers: [Р478]

# -------------------------------------------------------------
# LEGAL REFUND (Д-25…Д-28)
# -------------------------------------------------------------

legal_refund:
  D_25_minor_refund_initiators:
    contract: |
      Возврат несовершеннолетнему инициируют три роли:
        - сам участник (если сохранил доступ)
        - законный представитель (по заявлению)
        - оператор (по инициативе, при обнаружении underage_detected)
      Ствол саги: refund_stitch_block_16_legal
    guardian_verification: notarized_confirmation OR government_ID_scan_verified
    legal_status: pre-legal-review
    covers: [Д-25]

  D_26_refund_rules_zozpp:
    rules:
      before_stage_start:
        refund_percent: 100
        legal_basis: "ст.32 ЗоЗПП + оферта"
      during_stage:
        refund_percent: pro_rata
        formula: "amount * (remaining_days / total_stage_days) − actual_expenses"
        legal_basis: "ст.32 ЗоЗПП"
      quality_defect:
        refund_percent: 100
        legal_basis: "ст.29 ЗоЗПП (некачественная услуга)"
      max_response_time: 10d  # ст.31 ЗоЗПП
    legal_status: pre-legal-review
    covers: [Д-26]

  D_27_c2_withdrawal_midstream:
    trigger: consent_C2_revoke_event during active stage
    actions:
      - immediate auto_pause (author_pause with reason_code=consent_withdrawn)
      - initiate refund saga (ст.32 ЗоЗПП path)
      - retain actual_expenses (ФПР), refund the rest
      - notify participant with breakdown
    legal_status: pre-legal-review
    covers: [Д-27]

  D_28_service_delivery_presumption:
    contract: |
      После оказания услуги бот отправляет электронный акт.
      Если участник не отправил мотивированный отказ в 3 дня → услуга считается принятой.
      Append-only log: service_acceptance_log(pid, stage_id, sent_at, response_at, response_kind).
      НЕ ОТМЕНЯЕТ ст.32 ЗоЗПП: право отказа от продолжения услуги сохраняется независимо.
    legal_status: pre-legal-review
    covers: [Д-28]

# -------------------------------------------------------------
# PHOTO INGEST SAGA (Б15) — ПОЛНАЯ РЕАЛИЗАЦИЯ
# -------------------------------------------------------------

photo_ingest_saga:
  overview:
    kind: multi_step_saga
    one_shot_key: "photo_ingest:{client_op_id}"
    steps: 8
    gate:
      required_consent: C5 (photo_consent, R318)
      pre_check: "endpoint 403 if C5 not granted"

  step_1_upload_to_staging:
    action: pre-signed PUT to staging-bucket
    signed_url_ttl: 5min
    staging_path: "staging/{pid_bucket}/{pid}/{client_op_id}.raw"
    covers: [R349 upload]

  step_2_magic_bytes_check:
    action: read first 16 bytes; verify magic against declared MIME
    on_mismatch: reject; delete staging; log security event
    covers: [R384 hardening]

  step_3_mime_whitelist:
    allowed_mime: [image/jpeg, image/heic, image/png, image/webp]
    hard_blocked_mime: [image/svg+xml]
    rejected_with_message: [image/tiff, image/bmp, image/gif]
    covers: [R384]

  step_4_exif_strip:
    action: strip ALL EXIF metadata (GPS, camera, timestamps)
    library: piexif or exiftool subprocess
    verify: post-strip has no EXIF blocks
    covers: [R349 exif]

  step_5_convert_progressive_jpeg:
    action: convert to JPEG progressive, ≤2048px longer side, quality 85
    library: Pillow or libvips
    covers: [R350]

  step_6_hash_and_move:
    action: |
      compute sha256 of processed image
      target_path: "pii/photos/RU/{pid_bucket}/{pid}/{event_id}/{side}.jpg"
      S3 put with SSE-KMS + versioning + region_tag=RU tag
      record blob_ref(event_id, pid, sha256, key, version_id)
    covers: [R331, R351, Д-20]

  step_7_delete_staging:
    action: DELETE from staging-bucket
    on_failure: leave for GC (24h lifecycle)
    covers: [R349 staging cleanup]

  step_8_emit_ingest_completed:
    event: photo.ingest_completed(pid, event_id, blob_ref)
    outbox: yes
    covers: [R295 materializer path]

  gc_and_retention:
    staging_gc:
      lifecycle_rule: expire objects older than 24h
      alarm_on_orphans_over_1pct: yes  # metric: staging_orphan_rate
    photo_retention:
      trigger: participant_last_activity + 12 months
      worker: photo_retention_worker
      action: tag "to_delete" → lifecycle policy deletion
    covers: [R319, R337, R379]

  region_localization_enforcement:
    layout_key_prefix: "pii/photos/RU/"
    region_tag: RU (mandatory)
    cross_region_replication: HARD_ERROR
    ci_check: bucket policy denies replication outside RU
    migration_worker: legacy_region_tag_backfill (one-shot)
    covers: [R352, R353, R383]

photo_erasure:
  R334_delete_all_versions:
    contract: |
      erasure_blob_refs(pid) returns list of {key, version_id[]}
      For each: S3 DeleteObjectVersion for every version
      Write to erasure_blacklist (from И1/Д-18)
      On restore from backup: reapply erasure before service open
    ci_check: erasure endpoint returns list matching event_id set
    covers: [R231, R232, R233, R334]

  R335_object_lock_scope:
    photo_buckets: Object_Lock=DISABLED (mandatory for erasure)
    audit_log_buckets: Object_Lock=COMPLIANCE (WORM)
    ci_check_pre_deploy: bucket policies verified
    covers: [R335]

  signed_url_service:
    photo_url_ttl: 5min
    export_url_ttl: 15min
    upload_url_kind: pre-signed PUT
    referrer_policy_on_read: no-referrer
    covers: [R333]

# -------------------------------------------------------------
# ЭКСПОРТ (DSAR + BOT) — ЕДИНЫЙ WORKER
# -------------------------------------------------------------

export_worker:
  triggers:
    bot_command: /export {kind}
    mini_app: POST /export/request
    covers: [R297, R300, R345]

  export_kind_enum: [json, xlsx, csv, photos, full]

  format_defaults:
    priority: json + xlsx_text_typed
    csv: only_on_explicit_request  # R374/R375

  csv_injection_defense:
    prefix_dangerous_leading_chars: ["=", "+", "-", "@", "\t", "\r"]
    prefix_char: "'"
    covers: [R374]

  photo_naming_and_manifest:
    photo_filename: "photo_{event_id_short8}.jpg"
    manifest_json:
      fields: [event_id_full, obfuscated_name, sha256, original_kind]
      hash_verification: sha256 per file + top-level checksum
    covers: [R376, R377]

  delivery:
    small_files: sendDocument (≤10MB)
    large_files: signed-URL TTL 15min + Content-Disposition attachment
    covers: [R369]

  privacy_audit_write:
    event: data_export_event(pid, actor, kind, size_bytes, at)
    layer: privacy_audit
    covers: [R298 audit scope]

  legal_channels:
    R299_dual_channel:
      participant_self_export: mini_app_or_bot (152-ФЗ ст.14 subject access)
      operator_export_for_pid: owner_via_bot_with_reason (152-ФЗ ст.20 operator response)
      gdpr_compat: Art.15 (if applicable to non-resident participant)
    covers: [R299]

  sh21_third_party_notification:
    contract: |
      На erasure участника — уведомить третьи стороны, которым мы передали ПДн.
      Third parties current: PSP (для отмены рекуррентных списаний), нотификации TG (не хранят наши ПДн).
      Уведомление PSP: /notify_erasure {payment_ref}, best-effort с log.
    legal_basis: "GDPR Art.19 (для нерезидентов); 152-ФЗ ст.20 (для резидентов)"
    covers: [Ш21]

# -------------------------------------------------------------
# ЧЕК-АП (Б5) — ПОЛНАЯ РЕАЛИЗАЦИЯ
# -------------------------------------------------------------

checkup_config:
  storage:
    table: checkup_config_versions
    columns: [id, version, publish_epoch, zones, thresholds, texts_ref, legal_review_status, created_at]
    versioning: append_only

  ownership:
    thresholds: owner (editable)
    texts_red_zone: requires legal_review_status=approved BEFORE publish
    texts_yellow_green: owner (with UX review)
    covers: [R305, Р241]

  publish_flow:
    action: /publish_checkup_config {version_id}
    effect:
      - publish_epoch increment (Р489 mechanism from И2)
      - broadcast to admin_topic
      - existing participants: complete current epoch on old config
      - new starts: use new config
    ci_check: "cannot publish config with any red zone text pending legal review"
    covers: [Р489 hookup]

  auto_scored_by_bot:
    contract: |
      Bot computes aggregate score from measurements.
      Emits event checkup.scored(pid, epoch, zone, aggregate, signal_ids[])
      Participant sees ZONE only, not raw score (R306/R307).
    covers: [R306, R307, R308]

  zones:
    green: {text_ref: checkup_zone_green_text, legal_review: not_required}
    yellow: {text_ref: checkup_zone_yellow_text, legal_review: recommended}
    red: {text_ref: checkup_zone_red_text, legal_review: required, gate: verified_by_legal_block}
    covers: [R236, Р241]

  repeat_policy_enum:
    every_stage: {schedule: at each stage_completed}
    every_N: {schedule: at every Nth stage, configurable}
    on_demand: {schedule: manual owner trigger}
    covers: [R279, R284]

  stage_definition_extensions:
    surveys_array:
      each_element:
        kind: enum[regular, checkup]
        config_ref: nullable  # only for checkup
    completion_kind_enum: [time_based, task_based, open_ended]
    covers: [R234, R235, R237, R324]

  open_stage_survey:
    trigger: internal Б14 action from stage_completed event
    covers: [R234 open_stage_survey]

  baseline_override:
    command: /override_baseline {pid} {field} {new_value} {reason}
    actor: owner_only
    reason_required: true (free text; audit-logged)
    physical_baseline: onboarding_value_immutable
    effective_baseline: current_value_after_overrides
    override_log:
      table: baseline_override_log
      columns: [pid, field, old, new, reason, actor, at]
      layer: privacy_audit
      cache_invalidation: emit baseline_override event → Б10
    covers: [R358, Р488]

# -------------------------------------------------------------
# КРАСНАЯ ЗОНА (Д-09, Д-10) — ЗАЩИЩЁННЫЕ ТЕКСТЫ
# -------------------------------------------------------------

red_zone_templates:
  template_contract:
    required_fields:
      verified_by: legal_block  # mandatory Д-09
      header_text: "Это не медицинский совет"  # fixed, editable only via legal review
      body_ref: text_key with legal_status=approved
      appeal_button:
        label: "Пересмотр решения Автором"
        action: create_support_ticket(tag=red_zone_review)
    covers: [Д-09, Д-10]

  show_log:
    table: red_zone_show_log
    columns: [pid, template_id, at, checkup_epoch, aggregate_snapshot]
    append_only: true
    retention: forever
    covers: [Д-09 append_only]

  no_auto_escalation_to_red_flags:
    rule: "red zone == Чек-Ап аномалия; Red Flags == лемма-скрининг. НЕ смешивать автоматически."
    manual_escalation_only_via_owner: true

# -------------------------------------------------------------
# RED FLAGS ПРОТОКОЛ (Д-11)
# -------------------------------------------------------------

red_flags_protocol:
  scanner:
    scope: any user-generated message (reflections, support, mini_app inputs)
    algorithm: lemma_matcher with weighted scoring
    lemma_source: legal_pack.red_flags_lemmas (versioned)
    latency_target: ≤60s from message ingest
    isolation: separate microservice; failure does NOT block main flow

  on_trigger:
    within_60s:
      - transition participant: → sleeping (via author_pause, reason=red_flag)
      - send message: red_flags_emergency_text (Legal-approved)
      - alert admin_topic (both owners)
      - append-only log: red_flag_event(pid, message_id, matched_lemmas, weight, at)
    sla_owner_response: 24h
    on_owner_review:
      false_positive: /unpause_author + log false_positive
      confirmed: escalation path per Legal protocol

  emergency_contacts_text:
    text_key: red_flags_emergency_text
    legal_status: pre-legal-review  # F2 равен по критичности
    contents_required:
      - phone: телефон доверия (единый, круглосуточный)
      - text_helpline: чат-линии психологической помощи
      - guidance: короткая инструкция что делать
    forbidden_content: медицинские советы, диагнозы, лекарства

  false_positive_metric:
    name: red_flags_false_positive_rate
    formula: false_positives / total_triggers
    review: monthly by Legal (calibrate lemmas)

  covers: [Д-11]

fz323_terminology_blacklist:
  contract: |
    Список запрещённых терминов (диагнозы по МКБ-10, названия лекарств, врачебные назначения)
    ведётся Legal, версионируется.
    Проверяется на всех текстах Чек-Апа + красной зоны + Red Flags + рефлексий (out-going).
  ci_check: pre-release scan against blacklist → block if hit
  covers: [Д-12]

# -------------------------------------------------------------
# REVERT (Б13) — БЕЗ МУТАЦИИ ДАННЫХ
# -------------------------------------------------------------

revert_contract:
  event: revert_notice(pid, from_stage, to_stage, at)
  data_mutation: none  # только visible_frontier меняется
  history_preservation: yes (все stage_completed остаются в event log)
  ui_effect_for_participant: notification via Б9 (text in И4)
  compensating_step_for_refund: emitted by refund_saga step_3
  covers: [R258, R259, Р439, Р441 refund compensating]

# -------------------------------------------------------------
# LEGAL PACK ДОБАВЛЕНИЯ (Д-20, Д-21, F1)
# -------------------------------------------------------------

legal_pack_i3:
  D_20_cloud_provider:
    sse_kms_for_photos: mandatory
    ale_azure_like_encryption: recommended
    crypto_shredding: recommended (при >1000 участников или бюджете)
    covers: [Д-20]

  D_21_reflections_retention:
    without_C6:
      lifecycle_end: exclude from corpus by end of ЖЦ
      no_analytics_use: enforced by view filter
    with_C6:
      allowed_uses: internal aggregates only
      forbidden_uses: raw text external, third-party sharing
    covers: [Д-21]

  F1_system_fraud_deidentification:
    contract: |
      При обнаружении system_fraud (или payment_fraud) до legal-deadline
      участник переводится в frozen=true на 14 сут (Д-19 из И1).
      Апелляционный канал: Support с меткой fraud_appeal.
      Финализация frozen → erased требует ко-подпись owner (hard_confirm).
      Основание: ст.6 ч.1 п.7 152-ФЗ (защита интересов оператора).
    legal_status: pre-legal-review
    covers: [F1]

# -------------------------------------------------------------
# ПАТЧ CAPABILITY MATRIX (И3 additions)
# -------------------------------------------------------------

role_capability_matrix_i3_additions:
  - {role: owner, capability: refund_initiate, allow: true, hard_confirm_required: false}
  - {role: owner, capability: refund_rollback_manual_reissue, allow: true, hard_confirm_required: true}
  - {role: owner, capability: publish_checkup_config, allow: true, gate: legal_review_status_approved}
  - {role: owner, capability: override_baseline, allow: true, reason_required: true, audit_layer: privacy}
  - {role: owner, capability: red_zone_review_response, allow: true, sla: 24h}
  - {role: owner, capability: red_flags_review, allow: true, sla: 24h}
  - {role: finance, capability: refund_initiate, allow: true, hard_confirm_required: false}
  - {role: finance, capability: refund_rollback_manual_reissue, allow: false}
  - {role: moderator, capability: view_checkup_zone, allow: true, restricted_to: aggregate_only}
  - {role: moderator, capability: view_checkup_raw_score, allow: false}

# -------------------------------------------------------------
# HARD_CONFIRM ФРАЗЫ ДОБАВЛЕНИЯ И3
# -------------------------------------------------------------

hard_confirm_phrases_i3_additions:
  publish_checkup_config: "ПРИМЕНИТЬ ПОРОГИ"
  override_baseline: "ИЗМЕНИТЬ БАЗУ"
  frozen_to_erased_fraud: "УТВЕРДИТЬ ФРОД"

# -------------------------------------------------------------
# CI-CHECKS И3
# -------------------------------------------------------------

ci_checks_i3:
  - name: refund_saga_idempotency
    kind: integration_test
    scenario: "each step re-run yields same outcome"
    covers: [Р443 refund scope]

  - name: photo_ingest_magic_bytes_before_processing
    kind: unit_test
    scenario: "SVG-in-JPEG-clothing rejected at step_2"
    covers: [R384]

  - name: no_photo_bucket_object_lock
    kind: infra_test
    scenario: "S3 bucket policies verified pre-deploy"
    covers: [R335]

  - name: no_cross_region_replication
    kind: infra_test
    scenario: "bucket policy denies replication targets outside RU"
    covers: [R352, R353]

  - name: fz323_blacklist_scan
    kind: pre_release_scan
    covers: [Д-12]

  - name: red_zone_text_legal_gate
    kind: config_validation
    scenario: "red zone text without legal_status=approved blocks release"
    covers: [Д-09]

  - name: csv_injection_prefix
    kind: unit_test
    covers: [R374]

  - name: refund_details_retention_separate
    kind: unit_test
    scenario: "participant erasure does not delete refund_details before 3y"
    covers: [Р478]

# -------------------------------------------------------------
# ПЕРЕНОСЫ В И4
# -------------------------------------------------------------

deferred_from_i3:
  to_i4_wave_D:
    texts:
      - refund_saga_participant_texts (refund_pending, refund_completed, refund_declined, refund_partial_review)
      - manual_reissue_notification
      - photo_upload_errors (mime_rejected, magic_mismatch, size_exceeded)
      - red_zone_body_texts (green_variant, yellow_variant, red_variant)
      - red_flags_emergency_text (pre-legal-review → Legal)
      - service_acceptance_act_text (Д-28)
      - c2_withdrawal_notification (Д-27 breakdown)
    mini_app:
      - all client-side flows for refund initiation
      - photo upload UI + progress
      - "Мои согласия" panel including C5 revoke button
      - baseline_override UI (owner view)
      - red zone modal presentation
      - DSAR export button ("Мои данные")
    themes_and_broadcast:
      - admin_topic broadcast for publish_stage/publish_epoch (Р489 UI side)
      - alerts routing for red_flags/red_zone_review
# -------------------------------------------------------------
# ДОПОЛНЕНИЯ ПО РЕЗУЛЬТАТАМ АУДИТА И3
# -------------------------------------------------------------

audit_additions_i3:

  refund_psp_reconciliation:
    worker: refund_reconciliation_watcher
    frequency: hourly
    check: query PSP /transaction/status for refunds in last 7d
    on_discrepancy: alert admin_topic + freeze new refunds for that payment_id
    covers: [Refund reliability from Скептик Q1]

  exif_strip_post_verify:
    contract: "after step 4 reparse image; assert no metadata blocks; reject if found"
    logging: security_audit on metadata leak
    covers: [R349 hardening from Скептик Q2]

  red_flags_emergency_text_requirements_extended:
    must_include: [phone_24_7, explicit_bot_pause_disclosure, self_action_hint]
    must_not_include: ["мы Вам ответим", "ждите", "скоро"]
    covers: [Д-11 UX safety from Скептик Q3]

  erasure_deferral_precedence:
    cooling_off: initial erasure request (24-72h)
    refund_finalization_deferral: 14d AFTER cooling_off IF active refund
    no_active_refund: erasure proceeds immediately
    covers: [Р478 vs T1-ERASURE-INITIATE clarification from Скептик Q4]

  checkup_scored_immutable:
    rule: "checkup.scored event carries zone computed at emission time; not reinterpreted"
    covers: [R306/R307 hardening from Data Caveat 2]

  config_change_kind_split:
    safety_critical:
      apply: retroactive_immediate
      hard_confirm_required: true
      hard_confirm_phrase: "ПРИМЕНИТЬ ЗАДНИМ ЧИСЛОМ"
      audit_layer: privacy
    calibration:
      apply: forward_only
    covers: [publish_checkup_config safety from Скептик Q7]

  red_flags_text_early_start:
    action: Legal begins drafting red_flags_emergency_text at И3 start
    target: text approved before И4 code integration
    covers: [UX caveat + Скептик Q3]

# -------------------------------------------------------------
# РЕЕСТР РИСКОВ (продолжение из И1/И2)
# -------------------------------------------------------------

risk_registry_additions_i3:
  RISK-L-11:
    title: "PII leak через baseline_override reason free text"
    mitigation: "PII detector + FZ323 blacklist scan pre-write"
    severity: medium
    implementation_in: И4 (UI contract)

  RISK-L-12:
    title: "Old epoch participants на устаревшем checkup_config со связанным багом"
    mitigation: "config_change_kind split (safety_critical vs calibration)"
    severity: medium
    implemented: audit_additions_i3.config_change_kind_split

  RISK-L-13:
    title: "Orphaned staging files при watchdog kill photo saga"
    mitigation: "staging GC 24h + staging_orphan_rate alert"
    severity: low
    monitored_metric: staging_orphan_rate (>1% warn)

  RISK-L-14:
    title: "Red Flags SLA 24ч vs ночные срабатывания"
    mitigation: "emergency_text содержит 24/7 helpline + explicit bot pause disclosure"
    severity: high  # безопасность участника
    monitored_metric: red_flags_response_latency (p95)

  RISK-L-15:
    title: "Pillow EXIF strip медленный на heavy load"
    mitigation: "monitor ingest_p95_latency; migrate to libvips if >30s"
    severity: low
    trigger_threshold: 30s p95

# -------------------------------------------------------------
# УТОЧНЕНИЯ ЛЕГАЛА (Д-25/Д-28)
# -------------------------------------------------------------

legal_pack_i3_clarifications:
  D_25_operator_initiated_refund_wording:
    formulation: "оператор устраняет нарушение условий приёма участника (возраст)"
    NOT: "оператор отменяет договор в одностороннем порядке"
    legal_status: pre-legal-review
    covers: [Legal Caveat 1]

  D_28_minors_exception:
    rule: "3-дневная презумпция принятия услуги НЕ применяется к несовершеннолетним"
    fallback: "письменное подтверждение законного представителя требуется"
    covers: [Legal Caveat 2]

  Sh21_psp_notification_wording:
    contract: "PSP уведомляется, а не обязывается удалить. Тексты уведомления это отражают."
    participant_communication: "передача данных PSP регулируется его собственным retention (115-ФЗ 5 лет)"
    legal_status: pre-legal-review
    covers: [Legal Caveat 3]
```
