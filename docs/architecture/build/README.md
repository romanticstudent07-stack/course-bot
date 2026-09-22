---
file: build/README.md
block: "—"
title: "Артефакты сборки — оглавление, Mini App-first"
status: скелет (наполняется Автором и техническим партнёром)
doc_version: "скелет v1 (Mini App-first)"
policy: "Проект реализуется как Mini App-first. Каталог build/ содержит исполняемые артефакты; при расхождении с корпусом побеждает корпус. Разделение реализации Mini App / Bot / Backend — в DIVISION.md."
---

# BUILD — артефакты сборки (Mini App-first)

Каталог `build/` не входит в источник истины (`architecture/` + `normative/` + `appendix/`). Это **отражение** истины в исполняемой форме: разделение реализации, DDL, JSON-Schema для API Mini App, seed-файлы конфигов, сводный список CI-чеков и порядок сборки. При расхождении между `build/` и корпусом побеждает корпус.

## Ключевая точка входа

**Первое, что должен открыть агент реализации:** [DIVISION.md](DIVISION.md). Там — карта «блок → Mini App / Bot / Backend».

## Файлы каталога

| Файл | Что | Источник истины |
|---|---|---|
| [DIVISION.md](DIVISION.md) | Разделение реализации: Mini App / Bot / Backend по каждому блоку | этот отчёт + весь корпус |
| [build-order.md](build-order.md) | Порядок сборки: зависимости, миграции, минимальный синтетический запуск | этот отчёт + `deferred_from_*` из И1–И4 |
| [db-schema.sql](db-schema.sql) | DDL всех таблиц и логов | 40+ имён из блоков 2, 6, 7, 9, 10, 14, 15, 16 + И1–И4 + Б17 |
| [db-tables-index.md](db-tables-index.md) | Реестр таблиц: имя → владелец-блок → назначение → ссылка на DDL | тот же |
| [miniapp-api-contract.yaml](miniapp-api-contract.yaml) | OpenAPI 3.1 для Mini App: эндпоинты, схемы, коды ошибок, аутентификация | Б14 (Mini App v3.3 + дельта v3.4), И4, ERRATA E2, SEAM-1 |
| [miniapp-screens.md](miniapp-screens.md) | Инвентарь экранов Mini App: список экранов, состояния, переходы, тексты | этот отчёт + DIVISION.md |
| [miniapp-frontend-stack.md](miniapp-frontend-stack.md) | Стек Mini App-клиента: React 18 + Vite + TS + @telegram-apps/sdk-react | Ресёрч 2025–2026, ERRATA E2 |
| [bot-commands-registry.yaml](bot-commands-registry.yaml) | Реестр 35 команд бота из Б17 в исполняемой форме | Б17 |
| [config-schemas/](config-schemas/) | JSON-Schema для всех YAML-конфигов и seed-файлов | Б1 (принцип), Б14 (`metric_catalog`), Б17 (`config/commands`), И4 (`text_registry`) |
| [ci-checks.yaml](ci-checks.yaml) | Плоский список 50+ CI-чеков с id/владельцем/командой | И1–И4 (40+) + Б17 (10) |

## Порядок работ (для Автора и агента)

1. Прочитать [DIVISION.md](DIVISION.md) — понять, что где живёт.
2. Прочитать [build-order.md](build-order.md) — понять последовательность.
3. Наполнить [db-schema.sql](db-schema.sql) — по каждому блоку.
4. Наполнить [miniapp-api-contract.yaml](miniapp-api-contract.yaml) — 12+ эндпоинтов Mini App.
5. Наполнить [miniapp-screens.md](miniapp-screens.md) и [miniapp-frontend-stack.md](miniapp-frontend-stack.md).
6. Собрать [bot-commands-registry.yaml](bot-commands-registry.yaml) — 35 команд в исполняемой форме.
7. Собрать [ci-checks.yaml](ci-checks.yaml).
8. Написать код в трёх подкаталогах реализации: `apps/miniapp/`, `apps/bot/`, `apps/api/`.

## Открытые решения (без них сборка не идёт)

- **S3-провайдер.** Yandex Cloud / Timeweb Cloud «Облако 152-ФЗ» / `{s3-domain-ru}` — Д-29 против `D_20_cloud_provider`. Плейсхолдер `{s3-domain-ru}` в CSP блокирует прод (ERRATA раздел 6). Решение — в [appendix/C-registries.md](../appendix/C-registries.md), раздел 8 «Boot-gate».
- **`full_backup_rotation_cycle`.** Не определено; блокирует прод (ADD5). Задел — в [appendix/D-source-defects.md](../appendix/D-source-defects.md), D-12.
- **Три несовместимости Б17.** См. [normative/README.md](../normative/README.md), «Открытые несовместимости».
- **Роли `finance` и `moderator`.** Задел — в [appendix/C-registries.md](../appendix/C-registries.md), раздел 9.
- **Каноническое число команд.** 35 (см. [appendix/C-registries.md](../appendix/C-registries.md), раздел 5) + висячая 36-я `/grant_photos_access`.
- **PSP для рублей.** YooKassa / CloudPayments / Тинькофф Kassa — решение Автора до первой платной когорты.
