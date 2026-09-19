---
file: debt/07-C1-ban-sanction-contract.md
type: артефакт долга
artifact: C1_ban_sanction_contract
file_under_block: 7
node: C1
outcome: "CLOSE(mech)/STUB"
version: v3.2
owner_rules: Б7
owner_lifecycle_reaction: Б10
tail_to: [Б9, Legal]
---

# [АРТЕФАКТ ДОЛГА · подшить под → БЛОК 7 · узел C1 · CLOSE(мех) / STUB · v3.2]

осн. адресат Б7; STUB-хвосты → Б9 (критерии «за что банят», тексты алертов бана/апелляции), Legal (основание payment_fraud-терминализации — ссылка на A1-STUB)

**Выжимка.** Собственной механики бана в корпусе Б7 нет (Б7 = «Контрольные дни и модерация»; слов «бан/апелляция» нет). Весь бан живёт как Б10-реакция (Ш6): ban_mod, reason enum[behavior,payment_fraud], appeal[none|pending|resolved], removal: manual_by_author_only, окно 7д, 🔓, out_of_scope (Р109). C1 — NR-контракт, дозакрывающий санкционную часть Б7 поверх готовой Б10-реакции: правила-триггеры + апелляционный процесс. Владение: Б7 = правила/триггер/апелляция; Б10 = диспетчер-исполнитель (b10_reads_facts_not_computes).

**Ключевые решения.** Р-C1.1 — Триггер бана: явное модераторское/авторское действие (не авто), reason обязателен. Push нет (ban_reveal: pull, Б10-Ш6). Р-C1.2 — Апелляция ветвится по reason: behavior → диалоговый пересмотр; payment_fraud → исход по умолчанию resolved=rejected, пока платёж не урегулирован (appeal_restores_access:false). Канал = Поддержка (единств. канал апелляции, Б10-Ш4 support:active во всех состояниях). Р-C1.3 — Решение о пересмотре выносит только Автор (manual_by_author_only); статусы pending→resolved — авторское идемпотентное действие. Р-C1.4 (Скептик) — appeal=pending НЕ замораживает окно 7д (анти-эксплойт); истечение окна с открытой апелляцией → Тир-1 алерт автору до терминализации (владелец таймера Б10, C1 требует алерт). Р-C1.5 (Скептик) — отдельное durable-поле unban_reason (≠ reason бана) для аудит-следа снятия. Граница: событие снятия и исход restore/fresh = Б10-Р107; Б7 отдаёт только сигнал+reason снятия, НЕ вычисляет способ восстановления.

```yaml
artifact: C1_ban_sanction_contract
file_under: {block: 7, node: C1, outcome: "CLOSE(mech)/STUB", version: v3.2}
owner_rules: Б7
owner_lifecycle_reaction: Б10   # b10_reads_facts_not_computes
closes: contract_requests.to_B7_ban   # из Б10-Ш6

Б7_emits_to_Б10:
  ban_fact: true
  reason: {required: true, enum: [behavior, payment_fraud]}
  trigger: explicit_author_moderator_action   # НЕ авто; push:none (pull-reveal)
  unban_signal: {decision_owner: author_only, unban_reason: durable_field}   # исход restore/fresh = Б10-Р107
Б7_requires_from_Б10_Б6:
  - ban_mod (modifier)
  - out_of_scope_immediate (Р109)
  - 🔓_in_card (снимает только ban_mod, Р36)
  - terminalization_timer_7d + reveal:pull

appeal:
  channel: support   # Б10-Ш4, единственный
  statuses: [none, pending, resolved]
  restores_access: false   # запускает пересмотр, не возврат
  by_reason:
    behavior: dialogic_review
    payment_fraud: {default_resolution: rejected_until_payment_settled}
  decision: author_only
  idempotent: true   # pending→resolved = CAS; после терминализации = no-op (Р117)

invariants:
  INV-C1-PENDING-NO-FREEZE: "appeal=pending НЕ замораживает окно 7д (анти-эксплойт)"
  INV-C1-EXPIRY-ALERT: "истечение окна с appeal=pending → Тир-1 алерт автору ДО терминализации"
  INV-C1-APPEAL-AFTER-TERM-NOOP: "апелляция после терминализации/erasure = no-op"

stub_tails:
  - {to: Б9, what: "критерии 'за что банят' (behavior/payment_fraud детально) + тексты алертов бана/апелляции"}
  - {to: Legal, what: "основание/обратимость payment_fraud-терминализации → ссылка на A1-STUB (initiator_system_fraud)"}
```
