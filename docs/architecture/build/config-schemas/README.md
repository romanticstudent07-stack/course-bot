---
file: build/config-schemas/README.md
block: "—"
title: "JSON-Schema для всех YAML-конфигов"
status: скелет
---

# Config-schemas

Каталог для JSON-Schema, валидирующей конфиги перед деплоем.

## Список ожидаемых схем

| Файл | Что валидирует | Источник |
|---|---|---|
| `text_registry.schema.json` | `text_registry` (три тона, правовой статус, `{домен}.{имя}`) | И4 |
| `commands.schema.json` | `config/commands/*.yaml` (35 команд, 15 полей на команду) | Б17 |
| `metric_catalog.schema.json` | Seed-YAML `metric_catalog` | Б14 |
| `checkup_config.schema.json` | Конфиг Чек-Апа (5 зон, шкала, экстренный текст) | И3 |
| `topic_bindings.schema.json` | Привязки тем Telegram | И4 |
| `role_capability_matrix.schema.json` | Матрица «команда → роль» | Б17 |
| `hard_confirm_phrases.schema.json` | Реестр фраз hard-confirm (хэши) | Б17, E3 |
| `feature_flags.schema.json` | Флаги фич (Б14/И1) | И1 |

## Долги

- Ни одна из схем ещё не написана.
- Seed-файлы `text_registry` (75 текстов по Б9) не приведены в корпусе списком id — задел [C-registries.md#9-долги-реестра](../../appendix/C-registries.md).

## Плейсхолдеры прод-запуска (без них не собираем)

- `{s3-domain-ru}` — Boot-gate.
- `full_backup_rotation_cycle` — Boot-gate.
