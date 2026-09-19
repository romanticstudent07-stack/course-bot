---
file: 17/17-07-matrix-command-state.md
block: 17
part: "07"
title: "Матрица «команда × состояние участника»"
status: закрыт (v3.4)
doc_version: "consolidated v3 + патч v3.4"
contains: [матрица «команда × состояние» с обозначениями и таблицей]
---

> **Переопределено/уточнено ERRATA-UNIFIED и OVERRIDES.** Этот файл — часть Блока 17, нормы которого перекрываются нормативным стеком (`И1 → И2 → И3 → И4 → Б17 → SEAM-PATCH-1 → ERRATA-UNIFIED`). При парсинге YAML применяются машиночитаемые переопределения: [../normative/OVERRIDES.yaml](../normative/OVERRIDES.yaml) (E1, E2, E4, FIX1, R477_TARGET, N02 и др.). Единый список открытых несовместимостей — [../normative/README.md](../normative/README.md), раздел «Открытые несовместимости». Правило чтения — [../CANONICAL-SOURCES.md](../CANONICAL-SOURCES.md).

# Блок 17 — Часть 07. Матрица «команда × состояние участника»

> Источник — [../17-author-panel.md](../17-author-panel.md), раздел «МАТРИЦА «КОМАНДА × СОСТОЯНИЕ УЧАСТНИКА»».
> Исправления и дополнения к матрице (v3.4) — в
> [17-09-patch-v3-3-to-v3-4.md](17-09-patch-v3-3-to-v3-4.md), одноимённые разделы.

## МАТРИЦА «КОМАНДА × СОСТОЯНИЕ УЧАСТНИКА»

Обозначения:
`OK` — команда/переход допустимы штатно;
`WARN` — допустимо только с явным двухшаговым подтверждением и записью риска в аудит;
`—` — запрещено маршрутизатором (no-op с диагнозом).

Осями матрицы служат ключевые состояния FSM участника, в которых Панель Автора действительно может что-то менять или пробовать менять: `active`, `sleeping`, `owner_paused`, `user_paused`, `banned_soft`, `banned_hard`, `pending_erasure`, `erased`. Прочие технические состояния (например, `bootstrap`, `panic_maintenance`) — не участники, а системные режимы, и в матрицу не входят.

| Команда \ Состояние             | active | sleeping | owner_paused | user_paused | banned_soft | banned_hard | pending_erasure | erased |
|---------------------------------|:------:|:--------:|:------------:|:-----------:|:-----------:|:-----------:|:---------------:|:------:|
| `/pause_author`                 | OK     | OK       | —            | WARN        | —           | —           | —               | —      |
| `/unpause_author`               | —      | —        | OK           | —           | —           | —           | —               | —      |
| `/unpause_user`                 | —      | —        | —            | OK          | —           | —           | —               | —      |
| `/set_shadow` / `/unset_shadow` | OK     | OK       | OK           | OK          | —           | —           | —               | —      |
| `/life ±N`                      | OK     | OK       | OK           | WARN        | —           | —           | —               | —      |
| `/approve` / `/revert`          | OK     | OK       | WARN         | WARN        | —           | —           | —               | —      |
| `/complete_stage`               | OK     | WARN     | WARN         | WARN        | —           | —           | —               | —      |
| `/publish_stage`                | OK     | OK       | OK           | OK          | OK          | OK          | OK              | OK     |
| `/withdraw_stage`               | OK     | OK       | OK           | OK          | OK          | OK          | OK              | OK     |
| `/refund`                       | WARN   | OK       | OK           | OK          | OK          | OK          | OK              | —      |
| `/refund_rollback`              | WARN   | OK       | OK           | OK          | OK          | OK          | OK              | —      |
| `/finance_summary`              | OK     | OK       | OK           | OK          | OK          | OK          | OK              | OK     |
| `/override_baseline`            | OK     | OK       | OK           | WARN        | —           | —           | —               | —      |
| `/export`                       | OK     | OK       | OK           | OK          | OK          | OK          | OK              | —      |
| `/view_photos`                  | OK     | OK       | OK           | OK          | OK          | OK          | OK              | —      |
| `/view_change_map`              | OK     | OK       | OK           | OK          | OK          | OK          | OK              | —      |
| `/erasure_initiate`             | WARN   | OK       | WARN         | WARN        | OK          | OK          | —               | —      |
| `/erasure_finalize_before_cooling_off` | — | WARN | —          | —           | WARN        | WARN        | WARN            | —      |
| `/block`                        | OK     | OK       | OK           | WARN        | OK*         | —           | —               | —      |
| `/unblock`                      | —      | —        | —            | —           | OK          | OK          | —               | —      |
| `/support_inbox`                | OK     | OK       | OK           | OK          | WARN        | WARN        | WARN            | —      |
| `/red_zone_review`              | OK     | OK       | OK           | OK          | WARN        | WARN        | WARN            | —      |
| `/red_flags_review`             | OK     | OK       | OK           | OK          | WARN        | WARN        | WARN            | —      |
| `/whitelist_change`             | OK     | OK       | OK           | OK          | OK          | OK          | OK              | OK     |
| `/panic_maintenance`            | OK     | OK       | OK           | OK          | OK          | OK          | OK              | OK     |
| `/unpanic`                      | OK     | OK       | OK           | OK          | OK          | OK          | OK              | OK     |
| `/dlq_view` / `/dlq_replay`     | OK     | OK       | OK           | OK          | OK          | OK          | OK              | OK     |
| `/unfreeze_piracy`              | OK     | OK       | OK           | OK          | —           | —           | —               | —      |
| `/bind_topic`                   | OK     | OK       | OK           | OK          | OK          | OK          | OK              | OK     |
| `/audit`                        | OK     | OK       | OK           | OK          | OK          | OK          | OK              | OK     |
| `/legal`                        | OK     | OK       | OK           | OK          | WARN        | WARN        | WARN            | —      |

*«`/block` из `banned_soft` в `banned_hard` — OK*» — эскалация внутри бана; см. NR-17.14.
