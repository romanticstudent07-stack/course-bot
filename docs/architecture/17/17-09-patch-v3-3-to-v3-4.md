---
file: 17/17-09-patch-v3-3-to-v3-4.md
block: 17
part: "09"
title: "Патч к Блоку 17 (v3.3 → v3.4)"
status: закрыт (v3.4)
doc_version: "consolidated v3 + патч v3.4"
contains: [выжимка-патч, правки/дополнения матрицы «команда × состояние», дополнения матрицы «команда × роль», NR-17.15…23]
---

> **Переопределено/уточнено ERRATA-UNIFIED и OVERRIDES.** Этот файл — часть Блока 17, нормы которого перекрываются нормативным стеком (`И1 → И2 → И3 → И4 → Б17 → SEAM-PATCH-1 → ERRATA-UNIFIED`). При парсинге YAML применяются машиночитаемые переопределения: [../normative/OVERRIDES.yaml](../normative/OVERRIDES.yaml) (E1, E2, E4, FIX1, R477_TARGET, N02 и др.). Единый список открытых несовместимостей — [../normative/README.md](../normative/README.md), раздел «Открытые несовместимости». Правило чтения — [../CANONICAL-SOURCES.md](../CANONICAL-SOURCES.md).

# Блок 17 — Часть 09. Патч v3.3 → v3.4

> Источник — [../17-author-panel.md](../17-author-panel.md), раздел «ПАТЧ к Блоку 17 (v3.3 → v3.4)»
> и все его подразделы. Патч Б17 нормативного стека — [../normative/B17-admin-panel-patch.md](../normative/B17-admin-panel-patch.md).

## Выжимка-патч

Патч v3.4 — операционные шлифовки к Панели Автора без смены модели:

- Уточнены обозначения «WARN» и «— » в матрицах: WARN всегда сопровождается двухшагом и записью риска в аудит.
- В матрицу добавлены сервисные состояния `owner_paused` и `user_paused` как отдельные оси (ранее сливались с «пауза» без различения инициатора).
- Явно зафиксировано поведение `/publish_stage`, `/withdraw_stage`, `/whitelist_change`, `/panic_maintenance`, `/unpanic`, `/dlq_view`, `/dlq_replay`, `/bind_topic`, `/audit` — они доступны во всех состояниях участника, потому что оперируют системными артефактами, а не «этим участником».
- Ужесточён контракт `/refund` до `psp_transferred_at_utc` — после этого момента только `/refund_rollback` под свою идемпотентность.
- Добавлена трасса `expected_publish_epoch` в мастер для команд Б14/Б7, зависящих от эпохи публикации.
- В аудит добавлены явные события `send_blocked_hard_ban` и `send_blocked_erasure`.
- Введены новые инварианты **NR-17.15…NR-17.23** (см. ниже).

## МАТРИЦА «КОМАНДА × СОСТОЯНИЕ» — исправления к v3.3

```text
/approve, /revert:  owner_paused → WARN (было —)
                    user_paused  → WARN (было —)
/complete_stage:    owner_paused → WARN (было —)
                    user_paused  → WARN (было —)
/block:             banned_soft  → OK   (эскалация в banned_hard, было —)
/unblock:           banned_soft  → OK   (было WARN)
                    banned_hard  → OK   (было WARN)
/erasure_initiate:  active       → WARN (было —)
                    owner_paused → WARN (было —)
                    user_paused  → WARN (было —)
```

## МАТРИЦА «КОМАНДА × СОСТОЯНИЕ» — дополнения к v3.3

```text
Добавлены столбцы owner_paused и user_paused (ранее была одна «пауза»).
Добавлена команда /finance_summary (доступна всем состояниям, OK).
Добавлены столбцы pending_erasure и erased для команд
  /refund, /refund_rollback, /export, /view_photos, /view_change_map,
  /support_inbox, /red_zone_review, /red_flags_review, /legal.
Добавлены команды /publish_stage и /withdraw_stage
  как OK во всех состояниях (действуют на артефакт, а не участника).
```

## МАТРИЦА «КОМАНДА × РОЛЬ» — дополнения к v3.3

```text
/finance_summary:      finance = Y, helper = R
/audit:                moderator = R, finance = R (было —)
/view_change_map:      moderator = R (было —)
/publish_stage:        helper = R (было —)
/withdraw_stage:       helper = R (было —)
/dlq_view, /dlq_replay: helper = R (было —)
/legal:                moderator = — (явно зафиксировано)
```

## NR-инварианты, добавленные патчем v3.4

- **NR-17.15** — matrix «команда × состояние» покрывает **все** состояния FSM: `active`, `sleeping`, `owner_paused`, `user_paused`, `banned_soft`, `banned_hard`, `pending_erasure`, `erased`. Столбцы `owner_paused` и `user_paused` разделены (инициатор паузы влияет на допустимость).
- **NR-17.16** — Команды, оперирующие системными артефактами (`/publish_stage`, `/withdraw_stage`, `/whitelist_change`, `/panic_maintenance`, `/unpanic`, `/dlq_*`, `/bind_topic`, `/audit`), доступны во всех состояниях участника — их успех/отказ определяется владельцем-доменом, а не FSM участника.
- **NR-17.17** — После `psp_transferred_at_utc` `refund` — только через `/refund_rollback`; попытка повторного `/refund` на этом же переводе — no-op с диагнозом «psp_transferred, use /refund_rollback».
- **NR-17.18** — В мастер параметров всех команд Б14/Б7, зависящих от эпохи публикации, добавлен `expected_publish_epoch`; несовпадение — отказ с диагнозом.
- **NR-17.19** — `callback_data` Б17 ограничен 64 байтами Bot API; в кнопке передаётся стабильный ID мастера, параметры хранятся в Redis/PG.
- **NR-17.20** — Все тексты, идущие через Бота, санируются Б9 до предпросмотра; сырой HTML в сообщениях запрещён.
- **NR-17.21** — Форум-темы Работочей группы адресуются через alias→thread_id (Б8); хардкод числовых `thread_id` в конфиге Б17 запрещён.
- **NR-17.22** — Refund preflight-freeze выдачи контента выполняется **до** перевода PSP; отмена preflight-freeze возможна только через отдельную компенсирующую операцию, не «молчком».
- **NR-17.23** — `/panic_maintenance` обходит whitelist-кэш; снятие панического режима (`/unpanic`) требует passphrase из bootstrap-файла (не из БД).
