---
file: build/commands-mapping.md
title: "Маппинг команд: UI-поверхность бота ↔ backend-capabilities"
status: активный
doc_version: "commands-mapping v1.0"
contains: [объяснение двух слоёв, таблица маппинга slash→capability, список разбежек]
---

# commands-mapping.md — маппинг команд

## Зачем этот файл

В репозитории существуют **два разных списка команд**, и это не ошибка — это два разных слоя:

| Слой | Файл | Что это | Число элементов |
|---|---|---|---:|
| **UI-поверхность бота** | [bot-commands-registry.yaml](bot-commands-registry.yaml) | Что оператор реально вводит в Telegram-клиенте (`/life`, `/pause_author`, `/erasure_initiate`) | 35 slash-команд + 1 dangling |
| **Backend capabilities** | [../17/17-99-yaml-full.md](../17/17-99-yaml-full.md), `block_17.commands` | Внутренние операции backend с контрактом `capability`, `expected_*`, идемпотентностью (`life_plus`, `pause`, `confirm_payment`) | 25 внутренних имён |

Пересечение имён — всего 9 (`approve, audit, block, card, graph, legal, refund, revert, unblock`).
Остальные — либо разное имя одной операции (`/life +1` = `life_plus`), либо операция одного
слоя не имеет прямого аналога в другом (например, `/health` — служебная UI-команда без
доменной операции; `admin_add` — backend-операция без выделенной slash-команды, часть
`/whitelist_change`).

Агент реализации **читает оба файла** и использует эту таблицу маппинга для соединения.

## Таблица маппинга (UI → backend)

Формат: `slash-команда (UI)` → `capability или список внутренних имён (backend)` → домен-владелец.

### Жизненный цикл участника

| UI-команда | Backend capability / внутренние имена | Домен | Целевое состояние FSM |
|---|---|---|---|
| `/start` | (UI-only, инициирует Mini App first-launch) | Б4/SEAM-1 | — |
| `/pause_author` | `pause_author` / `pause` | Б2 | active → sleeping + author_pause |
| `/unpause_author` | `pause_author` (снятие) / `unpause` | Б2 | sleeping → active (снятие author_pause) |
| `/pause_grant` (из оригинала) | `pause_grant` | Б2 | добавляет квоту паузы |
| `/set_shadow` | `set_shadow` | Б7 | active → active + shadow (маскировка Автора) |
| `/life` (с параметром `+N`/`-N`) | `life_op` / `life_plus`, `life_minus` | Б2 | границы [0..3] |
| `/block` | `block_participant` / `block` | Б10 | **active/any → sleeping + author_pause(reason_class=block) + owner-review** (Р477, И2 стр. 323) |
| `/unblock` | `unblock_participant` / `unblock` | Б10 | sleeping → active (mode: restore\|fresh) |

### Рефлексии и этапы

| UI-команда | Backend capability | Домен |
|---|---|---|
| `/approve` | `approve` | Б7 |
| `/revert` | `revert` | Б7 |
| `/publish_stage` | `publish_stage` | Б14 (владелец `publish_epoch`) |
| `/publish_checkup_config` | `publish_checkup_config` | Б5 |

### Финансы

| UI-команда | Backend capability | Домен |
|---|---|---|
| `/refund` | `refund` (запуск Refund Saga) | Б16 + И3 |
| `/refund_rollback` | `refund_rollback` (manual_reissue flow) | Б16 |
| `/reconcile_psp` | (интеграционная задача, не в YAML block_17) | Б16 |
| — | `confirm_payment` (backend-only) | Б16 |
| — | `reject_payment` (backend-only) | Б16 |

### ПДн и медиа

| UI-команда | Backend capability | Домен |
|---|---|---|
| `/export` | `export_participant_data` | Б14 (export-worker) |
| `/view_photos` | `view_photos` (+ `/grant_photos_access` — dangling, RISK-L-22) | Б15 |
| `/view_change_map` | `view_change_map` | Б14 |
| `/override_baseline` | `override_baseline` | Б5 |
| `/erasure_initiate` | `erasure_initiate` (48ч cooling-off) | Б14 |
| `/erasure_finalize_before_cooling_off` | `erasure_finalize_before_cooling_off` | Б14 (несовместимость с И3, ждёт решения Автора) |
| `/legal` | `legal` (только по кнопке 📎 Legal, NR-17.10) | юрблок 99 |
| `/consent_export` | (расширение `/export` с фильтром `consents_only`) | 99 |
| `/privacy_report` | (расширение `/audit` с фильтром `privacy`) | Б14 |

### Модерация и сообщения

| UI-команда | Backend capability | Домен |
|---|---|---|
| `/announce` | (broadcast, отдельная механика) | Б9 |
| `/mute` (из оригинала) | `mute` | Б8 |
| `/unmute` (из оригинала) | `unmute` | Б8 |
| — | `message_via_bot` (backend-only, gate по состояниям) | Б9 |
| `/support_inbox` (из оригинала) | `support_inbox` | Б8 |
| `/red_zone_review` (из оригинала) | `red_zone_review` | Б9 |
| `/red_flags_review` (из оригинала) | `red_flags_review` | Б9 |

### Инфраструктура и сервис

| UI-команда | Backend capability | Домен |
|---|---|---|
| `/whitelist_change` (из оригинала) | `admin_add`, `admin_remove`, `admin_role` (все три) | Б17 |
| `/panic_maintenance` | `panic_maintenance` | Б17 |
| `/unpanic` (из оригинала) | `unpanic` (требует passphrase из bootstrap-файла) | Б17 |
| `/dlq_view` (из оригинала) / `/dlq_replay` | `dlq_view`, `dlq_replay` | Б15 |
| `/unfreeze_piracy` (из оригинала) | `unfreeze_piracy` | Б15 |
| `/bind_topic` (из оригинала) | `bind_topic` | Б8 |
| `/audit` | `audit` | Б17 |
| `/graph` | `graph` (k>=5) | Б14 |
| `/graph_review` | (мониторинг, схема аналогична `/graph`) | Б14 |
| `/health`, `/help`, `/support`, `/whoami`, `/version`, `/features`, `/flags`, `/backfill_check` | UI-only, без доменной capability | Б17 |
| `/card` | `card` (три профиля: full, reduced, financial) | Б6 |
| `/finance_summary` (из оригинала) | `finance_summary` | Б16 |

## Открытые точки маппинга (решение Автора)

1. **`/erasure_finalize_before_cooling_off`** — противоречит 14-дневной отсрочке И3 (одна
   из трёх несовместимостей Б7↔И3, шапка `../17-author-panel.md`). До решения Автора
   действует более строгое требование И3 — команда фактически недоступна.
2. **Дублирующие имена `pause` / `unpause`** — в оригинале Б17 существуют оба:
   `/pause_author` (владелец `/pause_author` в патче Б7) и внутренняя операция `pause`
   (в `block_17.commands`). Каноническое имя UI — `/pause_author`; `/pause` в реестре
   бота не заведён во избежание коллизии с `pause_shadow`.
3. **`/grant_photos_access`** — «висячая 36-я» команда (Д-30, RISK-L-22). Либо завести
   полную запись в `bot-commands-registry.yaml`, либо убрать примечание из `/view_photos`.

## Правило для агента реализации

1. Реализовать 35 UI-команд из `bot-commands-registry.yaml` — это набор точек входа Telegram-бота.
2. Каждый обработчик UI-команды вызывает backend-функцию, которая реализует
   соответствующую `capability` из `block_17.commands` (см. таблицу выше).
3. Если UI-команда не имеет доменной capability (`/help`, `/health` и т.п.) — обработчик
   исполняется целиком на уровне бота без обращения к backend-контракту `block_17.commands`.
4. Если backend capability не имеет прямой UI-команды (`confirm_payment`, `message_via_bot`)
   — это внутренний вызов от других backend-процессов (Refund Saga, Notifier).

## Связанные файлы

- [bot-commands-registry.yaml](bot-commands-registry.yaml) — реестр 35 UI-команд.
- [../17/17-99-yaml-full.md](../17/17-99-yaml-full.md) — YAML-контракт `block_17` с 25 backend-capabilities.
- [../17/17-01-command-catalog.md](../17/17-01-command-catalog.md) — каталог команд Панели Автора.
- [../normative/B17-admin-panel-patch.md](../normative/B17-admin-panel-patch.md) — патч Б7 нормативного стека.
- [../appendix/C-registries.md](../appendix/C-registries.md) — сводный реестр (риски RISK-L-22 про 25 vs 35).
- [../appendix/D-source-defects.md](../appendix/D-source-defects.md) — Д-29 (число команд), Д-30 (висячая 36-я).
