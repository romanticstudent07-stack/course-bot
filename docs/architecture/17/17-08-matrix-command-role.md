---
file: 17/17-08-matrix-command-role.md
block: 17
part: "08"
title: "Матрица «команда × роль»"
status: закрыт (v3.4)
doc_version: "consolidated v3 + патч v3.4"
contains: [матрица «команда × роль» и правила отображения ролей]
---

> **Переопределено/уточнено ERRATA-UNIFIED и OVERRIDES.** Этот файл — часть Блока 17, нормы которого перекрываются нормативным стеком (`И1 → И2 → И3 → И4 → Б17 → SEAM-PATCH-1 → ERRATA-UNIFIED`). При парсинге YAML применяются машиночитаемые переопределения: [../normative/OVERRIDES.yaml](../normative/OVERRIDES.yaml) (E1, E2, E4, FIX1, R477_TARGET, N02 и др.). Единый список открытых несовместимостей — [../normative/README.md](../normative/README.md), раздел «Открытые несовместимости». Правило чтения — [../CANONICAL-SOURCES.md](../CANONICAL-SOURCES.md).

# Блок 17 — Часть 08. Матрица «команда × роль»

> Источник — [../17-author-panel.md](../17-author-panel.md), раздел «МАТРИЦА «КОМАНДА × РОЛЬ»».
> Дополнения к матрице (v3.4) — в
> [17-09-patch-v3-3-to-v3-4.md](17-09-patch-v3-3-to-v3-4.md), раздел «МАТРИЦА «КОМАНДА × РОЛЬ» — дополнения к v3.3».

## МАТРИЦА «КОМАНДА × РОЛЬ»

Обозначения: `Y` — доступно, `—` — недоступно, `R` — только чтение соответствующих экранов/выводов.
Роли: `owner`, `moderator`, `finance`, `helper` (см. «Модель ролей (окончательная)»).

| Команда                         | owner | moderator | finance | helper |
|---------------------------------|:-----:|:---------:|:-------:|:------:|
| `/pause_author` / `/unpause_author` | Y | Y        | —       | R      |
| `/unpause_user`                 | Y     | Y         | —       | —      |
| `/set_shadow` / `/unset_shadow` | Y     | Y         | —       | —      |
| `/life ±N`                      | Y     | Y         | —       | —      |
| `/approve` / `/revert`          | Y     | Y         | —       | R      |
| `/complete_stage`               | Y     | —         | —       | —      |
| `/publish_stage` / `/withdraw_stage` | Y | —      | —       | R      |
| `/refund` / `/refund_rollback`  | Y     | —         | Y       | —      |
| `/finance_summary`              | Y     | —         | Y       | R      |
| `/override_baseline`            | Y     | —         | —       | —      |
| `/export`                       | Y     | —         | —       | —      |
| `/view_photos`                  | Y     | —         | —       | —      |
| `/view_change_map`              | Y     | R         | —       | —      |
| `/erasure_initiate` / `/erasure_finalize_before_cooling_off` | Y | — | — | — |
| `/block` / `/unblock`           | Y     | —         | —       | —      |
| `/support_inbox`                | Y     | Y         | —       | —      |
| `/red_zone_review`              | Y     | Y         | —       | —      |
| `/red_flags_review`             | Y     | Y         | —       | —      |
| `/whitelist_change`             | Y     | —         | —       | —      |
| `/panic_maintenance` / `/unpanic` | Y   | —         | —       | —      |
| `/dlq_view` / `/dlq_replay`     | Y     | —         | —       | R      |
| `/unfreeze_piracy`              | Y     | —         | —       | —      |
| `/bind_topic`                   | Y     | —         | —       | —      |
| `/audit`                        | Y     | R         | R       | R      |
| `/legal`                        | Y     | —         | —       | —      |
