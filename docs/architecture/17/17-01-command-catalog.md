---
file: 17/17-01-command-catalog.md
block: 17
part: "01"
title: "Каталог команд"
status: закрыт (v3.4)
doc_version: "consolidated v3 + патч v3.4"
contains: [реестр доменов и команд Панели Автора]
---

> **Переопределено/уточнено ERRATA-UNIFIED и OVERRIDES.** Этот файл — часть Блока 17, нормы которого перекрываются нормативным стеком (`И1 → И2 → И3 → И4 → Б17 → SEAM-PATCH-1 → ERRATA-UNIFIED`). При парсинге YAML применяются машиночитаемые переопределения: [../normative/OVERRIDES.yaml](../normative/OVERRIDES.yaml) (E1, E2, E4, FIX1, R477_TARGET, N02 и др.). Единый список открытых несовместимостей — [../normative/README.md](../normative/README.md), раздел «Открытые несовместимости». Правило чтения — [../CANONICAL-SOURCES.md](../CANONICAL-SOURCES.md).

# Блок 17 — Часть 01. Каталог команд

> Источник — [../17-author-panel.md](../17-author-panel.md), раздел «Каталог команд».
> Исполняемая форма реестра — [../build/bot-commands-registry.yaml](../build/bot-commands-registry.yaml).

## Каталог команд

Реестр по доменам-владельцам. `/pause_author`, `/unpause_author`, `/unpause_user`, `/set_shadow`, `/unset_shadow`, `/life ±N` — Б2. `/approve`, `/revert`, `/complete_stage`, `/publish_stage`, `/withdraw_stage`, `/publish_checkup_config` — Б7 (Б3/Б5 — читатели). `/refund`, `/refund_rollback`, `/finance_summary` — Б16. `/override_baseline` — Б5. `/export`, `/view_photos`, `/view_change_map`, `/erasure_initiate`, `/erasure_finalize_before_cooling_off` — юр/ПДн (Б14 — durability, Б15 — хранение). `/block`, `/unblock` — Б10/Б17 (двухшаг, аудит; **не восстанавливают `/place`** — миграции исключены поправкой v3.1). `/support_inbox`, `/red_zone_review` — Б8/Б9. `/red_flags_review` — Б9. `/whitelist_change` — Б17. `/panic_maintenance`, `/unpanic` — Б14. `/dlq_view`, `/dlq_replay` — Б14/Б15. `/unfreeze_piracy` — Б15. `/bind_topic` — Б8. `/audit` — Б17. `/legal` — юрблок; путь только через кнопку-ярлык `📎 Legal` (см. NR-17.10).
