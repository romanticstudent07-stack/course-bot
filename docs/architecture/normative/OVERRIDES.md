---
file: normative/OVERRIDES.md
title: "Реестр ERRATA-переопределений: как читать патчи с оговорками"
status: активный
doc_version: "overrides v1.0"
contains: [навигация по OVERRIDES.yaml, правило чтения, примеры]
---

# OVERRIDES.md — как правильно читать патчи

Этот файл — навигатор к машиночитаемому реестру
[OVERRIDES.yaml](OVERRIDES.yaml). Он объясняет, зачем реестр нужен и как им
пользоваться.

## Зачем этот реестр существует

В патчах И1/И2/И4 и в патче Б17 YAML-блоки перенесены **вместе с уже
отменёнными значениями**. Прозаическая врезка сверху говорит правду
(«Переопределено ERRATA-UNIFIED»), но сам YAML остаётся «историческим
снимком» — так требует оригинал Архитектуры.

Проблема: **человек, читающий врезку, знает правду; агент, парсящий YAML
напрямую, — не знает.** Он получает 6 устаревших значений (`materialized_view`,
`default_src: 'none'`, `publish_epoch.owner_block: B10`,
`risk_registry_total: 19`, дубль `db_role` в И2, `banned_*` как целевое
состояние `/block`).

Файл [OVERRIDES.yaml](OVERRIDES.yaml) закрывает этот пробел: он
собирает все переопределения в один машиночитаемый список.

## Правило чтения (обязательное)

1. Прочитать YAML из целевого патча (И1/И2/И4/Б17).
2. Применить поверх все записи из `OVERRIDES.yaml`, у которых
   совпадает поле `path`.
3. Итоговое значение — из `OVERRIDES.yaml`, не из патча.
4. Если пути нет в `OVERRIDES.yaml` — значение из патча каноническое.

## Что сейчас в реестре (10 записей)

| id | Путь | Отменено чем | Каноническое значение | Статус |
|---|---|---|---|---|
| E1 | `I2.participant_state_contract.storage.projection.kind` | ERRATA E1 | `regular_table_populated_by_projector` | closed |
| E2 | `I4.mini_app_client.csp_header.default_src` | ERRATA E2 | `'self'` + allowlist | closed |
| E3 | `B17.hard_confirm.paste_blocked` | ERRATA E3 + И2 п.15 | `true` (UX-слой) + `risk_status: mitigated_by_multilayer` | mitigated_by_multilayer |
| E4 | `I4.totals.risk_registry_total` | ERRATA E4 NOTE1 | `22` | closed |
| FIX1 | `I1.glossary_patch.new_entities_v3_5.publish_epoch.owner_block` | ERRATA FIX1 | `B14` | closed |
| N02 | `I2.read_only_enforcement` | нормализация | `db_roles: [...]` (список из 2 записей) | closed |
| R477_TARGET | `B17.commands.block.target_state` | Р477 (И2) | `sleeping + author_pause(reason_class=block) + owner_review` | closed |
| OPEN_A | `B17.commands.erasure_finalize_before_cooling_off` | И3 (не рассмотрено ERRATA) | недоступна до решения Автора | open_author_decision |
| OPEN_B | `B17.roles.moderator.card_visibility` | роль не определена | не разграничивать до решения Автора | open_author_decision |
| OPEN_C | `I3.red_zone.auto_escalation_60s` | разъяснение | разрешена (эскалация в sleeping, не banned) | closed |

## Как связано с другими файлами

- [CANONICAL-SOURCES.md](../CANONICAL-SOURCES.md) — общий арбитр источников
  (верхний файл vs подпапка). Теперь ссылается на этот реестр.
- [E-yaml-normalizations.md](../appendix/E-yaml-normalizations.md) — реестр
  синтаксических нормализаций (N-01 удаление дубля `forbidden_auto_transitions_to`,
  N-02 нормализация дубля `db_role`).
- [D-source-defects.md](../appendix/D-source-defects.md) — дефекты источника
  (D-01…D-31), не являющиеся ERRATA-переопределениями.

## Что делать, если нашли новое переопределение

1. Добавить запись в [OVERRIDES.yaml](OVERRIDES.yaml) с новым `id`.
2. Обновить таблицу выше.
3. Прогнать `bash tools/checks.sh` — должен пройти чек `overrides_registry_present`.

## CI-защита

Проверка `overrides_registry_present` в `tools/checks.sh` гарантирует, что
файл `OVERRIDES.yaml` существует и содержит записи `E1`, `E2`, `E4`, `FIX1`,
`R477_TARGET`, `N02`. При отсутствии — релиз блокируется.
