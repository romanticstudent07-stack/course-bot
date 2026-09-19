---
file: 17-author-panel.md
block: 17
title: "Панель Автора / командный режим (индекс)"
status: закрыт (v3.4, FULLY_DISASSEMBLED, части 00–09 + 99)
doc_version: "consolidated v3 + патч v3.4"
contains: [вводная часть блока, оглавление частей 17/17-00…17-09, ссылка на 17-99 YAML]
---

# БЛОК 17. ПАНЕЛЬ АВТОРА / КОМАНДНЫЙ РЕЖИМ

> **Канонический источник старшинства** — [normative/README.md](normative/README.md),
> раздел «Две оси: порядок присоединения ≠ ступень старшинства». Ступень старшинства:
> `корпус v3 → И1 → И2 → И3 → И4 → Б17 → SEAM-PATCH-1 → ERRATA-UNIFIED (высшая)`.

> **Переопределено/уточнено ERRATA-UNIFIED.** Три несовместимости патча Б17 с И3
> (`/erasure_finalize_before_cooling_off` против отсрочки 14 дн., автоэскалация в Red Zone
> за 60 сек, роли `finance`/`moderator`) единым ERRATA-слоем **не рассмотрены** и остаются
> решением Автора; до него действуют более строгие требования И3. См.
> [normative/errata-unified.md](normative/errata-unified.md),
> [normative/B17-admin-panel-patch.md](normative/B17-admin-panel-patch.md),
> [normative/seam-patch-1-onboarding.md](normative/seam-patch-1-onboarding.md).

> **Поверх этого блока действует патч Б17** —
> [normative/B17-admin-panel-patch.md](normative/B17-admin-panel-patch.md)
> (`consolidated-v3.9-b17`). Это разные документы: здесь — блок 17 корпуса (v3.4,
> требования NR-17.1…23), там — патч нормативного стека, снимающий STUB блока: единый
> реестр админ-команд (35 команд со схемой), командные кнопки Карточки, интерфейс аудита,
> дашборд, палитра, broadcast-инспектор.

Блок 17 — исполнительный слой Панели Автора. Он не вводит бизнес-правил, а даёт Автору и
его помощникам безопасные, единообразные, аудируемые входы к правилам блоков-владельцев.
Блок объёмный и разбит по разделам оригинала: один раздел = один файл в подпапке `17/`.
Ссылаться следует на номер части; тематические имена файлов — псевдонимы.

## Оглавление частей

| № | Содержание | Файл | Готовность |
|---|---|---|---|
| 00 | Назначение и границы + Модель ролей (окончательная) | [17/17-00-scope-and-roles.md](17/17-00-scope-and-roles.md) | ✅ |
| 01 | Каталог команд по доменам-владельцам | [17/17-01-command-catalog.md](17/17-01-command-catalog.md) | ✅ |
| 02 | UX-контракт входа + двухшаг + идемпотентность | [17/17-02-ux-hard-confirm.md](17/17-02-ux-hard-confirm.md) | ✅ |
| 03 | Атомарность и гонки + Fail-safe (сводка) | [17/17-03-atomicity-failsafe.md](17/17-03-atomicity-failsafe.md) | ✅ |
| 04 | Пауз-семантика, вердикт vs проход, refund-saga, цикл чек → reject → новый чек | [17/17-04-pause-verdict-refund.md](17/17-04-pause-verdict-refund.md) | ✅ |
| 05 | Приватность /legal, гейт сообщений через Бота, whitelist bootstrap, Аудит, undo | [17/17-05-privacy-audit-undo.md](17/17-05-privacy-audit-undo.md) | ✅ |
| 06 | Сквозной инвариант NR-17.14 + все NR-инварианты Б17 (NR-17.1…14) | [17/17-06-invariants.md](17/17-06-invariants.md) | ✅ |
| 07 | Матрица «команда × состояние участника» | [17/17-07-matrix-command-state.md](17/17-07-matrix-command-state.md) | ✅ |
| 08 | Матрица «команда × роль» | [17/17-08-matrix-command-role.md](17/17-08-matrix-command-role.md) | ✅ |
| 09 | Патч v3.3 → v3.4 (выжимка, правки/дополнения матриц, NR-17.15…23) | [17/17-09-patch-v3-3-to-v3-4.md](17/17-09-patch-v3-3-to-v3-4.md) | ✅ |
| 99 | Единый YAML-контракт `block_17` (дословно) | [17/17-99-yaml-full.md](17/17-99-yaml-full.md) | ✅ |

## Как ссылаться

Ссылаться на нормы Блока 17 следует со ссылкой на номер части: например,
«17/07 — WARN по `/erasure_initiate` в `active`» или «17/06 — NR-17.14, бот не банит».
Тематические имена файлов — псевдонимы, могут переименовываться под задачу.

## Правило приоритета для этого Блока

Верхний файл (`17-author-panel.md`) — индекс и вводная. При расхождении между верхним
файлом и содержательной частью в `17/` приоритет у файла из подпапки. См.
[CANONICAL-SOURCES.md](CANONICAL-SOURCES.md), строка Блок 17.

## Связанные документы

- [normative/README.md](normative/README.md) — старшинство нормативного стека.
- [normative/B17-admin-panel-patch.md](normative/B17-admin-panel-patch.md) — патч Б17.
- [normative/errata-unified.md](normative/errata-unified.md) — ERRATA (высшая).
- [normative/seam-patch-1-onboarding.md](normative/seam-patch-1-onboarding.md) — SEAM-1.
- [17-SPLIT-PROTOCOL.md](17-SPLIT-PROTOCOL.md) — протокол этой нарезки.
- [build/bot-commands-registry.yaml](build/bot-commands-registry.yaml) — исполняемый реестр 35 команд.
