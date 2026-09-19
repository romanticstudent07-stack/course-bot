---
file: debt/15-A4-nonreidentifiability-backup-erasure.md
block: 15
title: "Артефакт долга A4 — нереидентифицируемость и erasure в бэкапах"
node: A4
attach_to: "подшить под → БЛОК 15"
outcome: "CLOSE(тех) / STUB(Legal)"
status: "CLOSE(тех)/STUB(Legal), v3.2"
doc_version: "consolidated v3"
contains: [выжимка, interface contract yaml, erasure-blacklist, restore-reapply, stub-хвосты Legal]
---

# [АРТЕФАКТ ДОЛГА · подшить под → БЛОК 15 · узел A4 · CLOSE(тех) / STUB(Legal) · v3.2]

осн. адресат Б15/Инфра; STUB-хвосты → Legal (стандарт нереидентифицируемости, срок ротации бэкапов, правовая судьба reflections_anon_corpus, повышенный стандарт детских данных)

## Выжимка

Обезличивание удаляет прямые идентификаторы (имя, дата рождения, телефон, tg_user_id/username, фото, регион) и хранит остальное навсегда без привязки к личности (замеры, чек-ап, корпус рефлексий, прогресс, журнал жизней, платёжная статистика). Разрыв необратим — ключа для повторного сопоставления не сохраняется. Однако утверждение attachment_to_identity: none означает отсутствие прямого ключа, а не корреляционную устойчивость: критерий нереидентифицируемости в корпусе не специфицирован и вводится этим узлом (NR).

Технический дефолт нереидентифицируемости: квазиидентификаторы (замеры + прогресс + платёжный профиль) хранить несвязуемо — разнесение без общего ключа либо агрегация платёжной статистики до когорты; нереализуемая связка помечается как остаточный риск для Legal, а не замалчивается. Корпус рефлексий — отдельный, самый острый вектор: свободный текст несёт стилометрический/содержательный отпечаток автора, техника не устраняет authorship-реидентификацию. Поэтому reflections_anon_corpus фиксируется как явно принятый остаточный риск, решение по которому (хранить / условие согласия / не хранить) принадлежит Legal — это НЕ технический CLOSE.

Бэкапы: erasure применяется мгновенно к живой базе, снапшоты не вскрываются (вскрытие ломает целостность), PII вымывается пассивно по ротации. Это подводится под канонический стандарт ICO «beyond use»: бэкап после erasure не используется ни для чего, кроме disaster-recovery. Но пассивная модель корректна лишь для хранящегося снапшота; в момент восстановления снапшот воскрешает обезличенного участника со всем PII. В корпусном restore_runbook (Шаг 5) шага переприменения erasure нет — это реальная дыра, из-за которой инвариант A1 identity_break: irreversible истинен на живой базе, но ложен после restore.

Дыра закрывается введением erasure-blacklist (durable суррогатная таблица стёртых participant_id + timestamp, без PII, входит в pg_dump) и обязательного шага restore-reapply: после проигрывания WAL и верификации, но строго до старта воркеров и webhook, erasure переприменяется по всей blacklist (идемпотентно, forward-only, через существующую сагу A1). Прогон по всей blacklist — вопрос корректности; фильтр по timestamp — лишь оптимизация. Активация любого воркера/webhook до завершения reapply запрещена (иначе бот обслужит воскресшего участника с живым chat_id). Ретеншен blacklist обязан быть не меньше максимального срока жизни любого бэкапа/WAL — иначе старый бэкап останется без записи для reapply.

Правовой слой — STUB(Legal): стандарт качества обезличивания (Recital 26 анонимизация vs псевдонимизация / 152-ФЗ), число срока ротации бэкапов (в корпусе отсутствует, задаёт нижнюю границу ретеншена blacklist), правовая достаточность «beyond use» как исполнения Art.17, судьба корпуса рефлексий, повышенный стандарт для детских данных (на случай протечки гейта 18+ из E3).

## Interface Contract (YAML)

```yaml
artifact: A4_nonreidentifiability_and_backup_erasure
file_under: {block: 15, node: A4, outcome: "CLOSE(tech) / STUB(Legal)", version: v3.2}
owner: Б15/Инфра

anonymization:
  physically_deleted: [name, birthdate, phone, tg_user_id, tg_username, photos, region, any_direct_identifier]
  anonymized_kept_forever: [measurements, checkup, reflections_anon_corpus, progress, lives_journal, payment_stats, analytics]
  identity_break: irreversible   # A1, key for re-linking NOT kept
  caveat: "attachment_to_identity:none = нет ПРЯМОГО ключа, НЕ корреляционная устойчивость"

nonreidentifiability:   # NR — критерий в корпусе отсутствует
  tech_default:
    quasi_identifiers: "measurements/progress/payment_stats хранить несвязуемо (разнесение без общего ключа / агрегация payment до когорты)"
    unlinkable_impossible: "→ явный остаточный риск для Legal, не замалчивать"
  reflections_anon_corpus:
    status: accepted_residual_risk   # НЕ tech CLOSE
    vector: authorship_attribution_by_content
    decision_owner: Legal            # хранить / условие согласия / не хранить

backups:
  live_db: anonymized_instantly
  snapshots: not_opened              # вскрытие ломает целостность
  passive_washout: by_rotation
  standard: ICO_beyond_use           # бэкап только для DR, иначе не используется
  restore_gap_FOUND: "restore_runbook (Шаг5) НЕ переприменяет erasure → A1 irreversible ложен после restore"

erasure_blacklist:      # NR — сущность в корпусе отсутствует
  table: durable_surrogate
  fields: [participant_id, erasure_timestamp]   # без PII, класс surrogate → INV-A3-REF-PURITY ok
  survives_restore: true   # входит в pg_dump
  retention: ">= max(retention всех бэкапов + WAL)"   # правовое число ротации = нижняя граница (STUB Legal)

restore_reapply:        # NR — недостающий шаг runbook
  when: "после let_wal_replay + then_verify, СТРОГО до воркеров/webhook"
  scope: whole_blacklist_no_filter   # корректность; timestamp-фильтр = только оптимизация
  mechanism: reuse_A1_saga   # run_canonical_deletion→break_identity→anonymize; идемпотентно, forward-only
  invariant_INV-A4-REAPPLY-BEFORE-SERVE: "ни воркер, ни webhook не активны до завершения reapply"
  ties_to: delete_old_webhook_before_new (Шаг5)

stub_tails:
  - {to: Legal, what: "стандарт нереидентифицируемости (Recital26 / 152-ФЗ обезличивание)"}
  - {to: Legal, what: "срок ротации бэкапов/WAL (число отсутствует) → нижняя граница retention blacklist"}
  - {to: Legal, what: "правовая достаточность beyond-use как исполнения Art.17 в части бэкапов"}
  - {to: Legal, what: "судьба reflections_anon_corpus (остаточный риск реидентификации по содержанию)"}
  - {to: Legal, what: "повышенный стандарт стирания детских данных (ICO) — на случай протечки гейта 18+ (E3)"}
```
