---
file: 15/15-03-deletion-history-protection.md
block: 15
title: "Шаг 3 — Удаление контента и защита истории"
status: закрыт
doc_version: "consolidated v3"
contains: [Шаг 3, аксиома 1, аксиома 2, каталог триггеров, каноническая процедура удаления, поведение при обрыве, erasure, yaml step_3]
---

# БЛОК 15 · ШАГ 3 — УДАЛЕНИЕ КОНТЕНТА И ЗАЩИТА ИСТОРИИ

Шаг определяет полный каталог событий, удаляющих/изменяющих контент, единый порядок удаления, устойчивый к обрывам, и окончательно закрывает два сквозных вопроса проекта двумя аксиомами, действующими на весь проект.

## Аксиома 1 (защита контента, закрыта навсегда)

Система включает максимальную доступную на платформе защиту: protect_content на каждом контент-сообщении (запрет пересылки/копирования/сохранения); внутри бота нет медиа вовсе; второй эшелон — см. Шаг 6. Признанное платформенное ограничение: на части клиентов (iOS, начало 2026) системный скриншот текста платформой не блокируется, и Bot API не уведомляет о скриншоте — это вне нашего контроля. Съёмка экрана сторонней камерой признана неустранимой по природе (физический предел любой платформы) и выведена за границы проекта. Вопрос защиты контента в архитектуре больше не поднимается.

## Аксиома 2 (судьба данных при удалении, закрыта навсегда)

Физически удаляется только идентифицирующее личность (имя, дата рождения, телефон, идентификатор и имя в мессенджере, фото, регион и любые поля-привязки). Всё остальное обезличивается и хранится навсегда (замеры, чек-ап, тексты рефлексий как обезличенный корпус, прогресс, журнал жизней, платёжная статистика, аналитика) — ради статистики и масштабирования. Разрыв связи с личностью необратим: ключа для повторного сопоставления не сохраняется — это одновременно «право быть забытым» в строгом смысле и вывод данных из-под режима ПДн. Возвращающийся участник всегда начинает с чистого листа. Инвариант append-only не нарушается: журнал физически цел, вырезается только привязка к личности. Дефолт при неоднозначности: идентификатор — удалить, всё прочее — обезличить и сохранить.

## Каталог триггеров

Рефанд — единственный триггер, удаляющий защищённый (committed) контент; затрагивает контент возвращаемого Этапа, снимает commit_guard, меняет платёжный статус; не трогает другие Этапы, сообщения участника, замеры, финансы, служебные. Рестарт — удаляет контент ровно рестартируемой зоны (текущий pending-Этап целиком), committed прошлых Этапов неприкосновенен; механически идентичен рефанд-удалению, но работает по незащищённой зоне и не снимает guard. Ревёрт — для ленты не триггер удаления вообще: меняет только видимость в дереве «Пройденного», старые сообщения остаются, дубли не вычищаются. Erasure — работает по признаку личности и по приоритету поглощает все триггеры: вычищает весь контент бота по всем Этапам (включая committed), затем необратимо рвёт идентичность и обезличивает остальное.

## Единая каноническая процедура удаления — четыре стадии

Стадия 0 (снятие защиты): при удалении committed-зоны (только рефанд) первым снимается commit_guard, иначе он заблокирует собственное удаление; для pending-зон — вхолостую. Стадия 1 (пометка намерения): целевые строки атомарно помечаются статусом «намечено к удалению» в одной транзакции с бизнес-решением — зеркало фазы намерения доставки. Стадия 2 (физическое удаление): бот удаляет сообщения пачками (до 100 id за вызов), по факту успеха пачки строки → «удалено»; флуд-контроль обрабатывается как при доставке (ждём retry_after, повторяем пачку, не считаем провалом). Стадия 3 (финальное уведомление): одно мягкое сообщение (механика — Б15, текст — блок коммуникации).

## Поведение при обрыве

Поведение при обрыве — симметрично досылке. Точка невозврата — фиксация намерения (стадия 1). До неё — откат назад в чистое исходное (ничего не удалено, статус не изменён). После неё — доведение вперёд: фоновый процесс находит «намечено к удалению» и дочищает пачками. Обоснование: физическое удаление необратимо, восстановить нельзя, поэтому после зафиксированного намерения единственный корректный итог — довести удаление до конца. Это уточняет recovery-асимметрию Б13 («refund/restart откатываются назад» относится к бизнес-состоянию; у физического удаления граница отката — по фиксации намерения). Гарантия: нет состояния, в котором возвращённый контент навсегда остался бы доступным.

Erasure — композиция: канон-удаление всех Этапов → необратимый разрыв идентификаторов → обезличивание. Порядок жёсткий: сначала вычистить ленту (для адресации нужен идентификатор чата), потом рвать идентичность. Прощальное уведомление — последнее действие перед разрывом (нет пустых экранов). Гонки триггеров разрешаются идемпотентностью удаления и приоритетом erasure. Открытых вопросов нет.

## YAML — Шаг 3

```yaml
block_15:

  # ================================================================
  step_3:
    title: "Удаление контента и защита истории"
    status: closed
    axiom_1_content_protection:
      status: closed_forever
      protection_enabled: maximum_available_on_platform
      mechanisms: [{protect_content: true}, {no_media_inside_bot: true}, {hidden_marker_ref: step_6}]
      platform_limitation: {ios_text_screenshot: "не блокируется (нач. 2026)", screenshot_notification: not_available_in_bot_api}
      out_of_project_forever: {external_camera_capture: true, rationale: "физический предел любой платформы"}
      never_reraise: true
    axiom_2_deletion_vs_anonymization:
      status: closed_forever
      physically_deleted: {scope: identity_only, fields: [name, birthdate, phone, tg_user_id, tg_username, photos, region, "любые идентифицирующие"]}
      anonymized_and_kept_forever: {items: [measurements, checkup, reflections_anon_corpus, progress, lives_journal, payment_stats, analytics], attachment_to_identity: none}
      identity_break: irreversible
      returning_user: from_scratch_no_restore
      append_only_compat: "журнал физически цел; вырезается только привязка к личности"
      default_on_ambiguity: "идентификатор -> удалить; прочее -> обезличить и хранить"
      never_reraise: true
    deletion_triggers:
      refund: {deletes: committed_and_pending_content_of_stage_N, removes_commit_guard: true, changes_payment_status: true, never_touches: [other_stages, participant_messages, reflection_replies, measurements, financial, service]}
      restart: {deletes: current_stage_content_all_days, never_touches: committed_of_completed_stages, mechanics: identical_to_refund_deletion, differs: "не снимает guard, работает по pending"}
      revert: {chat_deletion: none, affects: visibility_tree_only, dupes_cleanup: false}
      erasure: {by: identity, priority: absorbs_all, deletes_from_chat: all_bot_content_all_stages, then: [break_identity_irreversible, anonymize_rest]}
    canonical_deletion_procedure:
      stage_0_remove_guard: {when: zone_is_committed, action: remove_commit_guard, else: noop}
      stage_1_mark_intent: {action: "set_status(pending_delete)", atomic_with: business_decision, mirror_of: delivery_intent_phase}
      stage_2_physical_delete: {api: deleteMessages, batch_up_to: 100, on_batch_success: "set_status(deleted)", flood_control_429: {treat_as: normal, on_429: [read_retry_after, wait, retry_same_batch]}}
      stage_3_final_notification: {mechanism_owner: block_15, wording_owner: communication_block, principle: no_empty_screens}
    failure_recovery:
      point_of_no_return: stage_1_intent_committed
      before_intent: {action: rollback_backward, state: [nothing_deleted, business_unchanged]}
      after_intent: {action: forward_complete, worker: background_deleter, finds: "rows(status==pending_delete)"}
      reconciliation_with_b13: "'refund/restart назад' — про бизнес-состояние; у физудаления граница отката = фиксация намерения"
      security_guarantee: "нет состояния с навсегда доступным возвращённым контентом"
    erasure_procedure:
      composition: ["run_canonical_deletion(all_stages)", break_identity_irreversible, anonymize_rest]
      order_rule: "сначала вычистить ленту (нужен адрес чата), потом рвать идентичность"
      farewell_notification: {sent: last_action_before_identity_break, wording_owner: communication_block}
    trigger_races: {resolution: [idempotent_deletion, erasure_absorbs_all]}
    open_questions: []
```
