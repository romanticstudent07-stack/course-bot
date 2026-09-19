---
file: appendix/E-yaml-normalizations.md
title: "Реестр синтаксических нормализаций YAML"
status: активный (реестр открыт)
doc_version: "normalizations v1.1"
contains: [реестр отступлений YAML от оригинала Архитектура.docx, N-01, N-02]
---

# E-yaml-normalizations.md — реестр нормализаций YAML

Этот файл фиксирует **каждое осознанное отступление** YAML-контрактов в
репозитории от эталона (см.
[../CANONICAL-SOURCES.md](../CANONICAL-SOURCES.md), раздел «Эталон для
сверки YAML»).

Правило: любое изменение YAML, не совпадающее байт-в-байт с эталоном,
должно быть зарегистрировано здесь отдельной записью `N-NN` с
обоснованием и доказательством, что содержание не потеряно.

## Отличие от OVERRIDES.yaml

- **OVERRIDES.yaml** — переопределения ERRATA (E1, E2, E4, FIX1 и т.д.);
  меняют **семантику** ключей, не трогая исходные патчи.
- **E-yaml-normalizations.md** — **синтаксические нормализации**;
  исправляют невалидные конструкции YAML (дубли ключей и т.п.), не
  меняя семантики.

## Реестр записей

### N-01. Снят дублированный ключ `banning_invariant.forbidden_auto_transitions_to`

- **Файл:** `architecture/17/17-99-yaml-full.md`
- **Раздел YAML:** `block_17.banning_invariant`
- **Строка до правки:**

  ```yaml
  banning_invariant:
    # Р477 (И2): состояния banned_* из FSM удалены — запрет ниже сохранён как исторический инвариант
    forbidden_auto_transitions_to: [banned_soft, banned_hard]
    forbidden_auto_transitions_to: [banned_soft, banned_hard]
  ```

- **Строка после правки:**

  ```yaml
  banning_invariant:
    # Р477 (И2): состояния banned_* из FSM удалены — запрет ниже сохранён как исторический инвариант
    forbidden_auto_transitions_to: [banned_soft, banned_hard]
  ```

- **Причина:** синтаксическая грязь исходника — два одинаковых ключа в одном YAML-mapping.
  По спецификации YAML 1.2 такое поведение undefined; оба значения идентичны, эффекта у дубля нет.
- **Проверка отсутствия потерь:** значение сохранено; смысл NR-17.14 не затронут.
- **Кто внёс:** Автор.
- **Дата регистрации:** 2026-09-13.

### N-02. Нормализован дублированный ключ `read_only_enforcement.db_role` в И2

- **Файл:** `architecture/normative/I2-wave-b.md`
- **Раздел YAML:** `participant_state_contract.read_only_enforcement`
- **Строки до правки (стр. 323–324 оригинала, дубль-ключ подряд):**

  ```yaml
  read_only_enforcement:
    db_role: participant_state_reader (SELECT only)
    db_role: participant_state_projector (SELECT + INSERT on projection tables)
  ```

- **Каноническое значение (в OVERRIDES.yaml, id N02):**

  ```yaml
  read_only_enforcement:
    db_roles:
      - name: participant_state_reader
        grants: SELECT
        scope: read_only_projection
      - name: participant_state_projector
        grants: [SELECT, INSERT]
        scope: projection_tables
        restriction: "used only by Б10 projector process (INV-1)"
  ```

- **Причина:** синтаксически это undefined YAML (два одинаковых ключа
  в одном mapping). Стандартный парсер молча оставит только одну роль —
  агент, парсящий И2 напрямую, физически теряет `participant_state_reader`
  и получает схему прав БД без единственного разрешённого читателя.
- **Стратегия правки:** **не трогаем сам файл И2** (оригинал требует
  сохранять патчи как исторические снимки). Каноническая форма живёт
  в [../normative/OVERRIDES.yaml](../normative/OVERRIDES.yaml) под id `N02`.
  Правило чтения: агент читает И2, потом применяет OVERRIDES — получает
  корректную схему.
- **Проверка отсутствия потерь:** обе роли явно перечислены в OVERRIDES;
  оригинал стр. 323–324 подтверждает намеренность двух ролей; CI-чек
  `single_writer_participant_state` продолжает следить за инвариантом.
- **Кто внёс:** Автор (регистрация нормализации).
- **Дата регистрации:** 2026-11-XX (по факту вашего коммита).

## Правила ведения реестра

1. Каждая запись имеет уникальный id `N-NN`.
2. Запись создаётся **в том же PR**, где делается правка YAML.
3. Запись содержит: файл, раздел YAML, строку до, каноническое значение,
   причину, стратегию правки (in-place или через OVERRIDES), доказательство
   отсутствия потерь.
4. Без записи в этом файле любая правка YAML `block_17` или патчей И1/И2/И3/И4/Б17
   считается нарушением правила нулевых потерь.

## Связанные файлы

- [../CANONICAL-SOURCES.md](../CANONICAL-SOURCES.md) — правило эталона.
- [../normative/OVERRIDES.yaml](../normative/OVERRIDES.yaml) — машиночитаемые ERRATA-переопределения.
- [../normative/OVERRIDES.md](../normative/OVERRIDES.md) — навигатор к OVERRIDES.yaml.
- [D-source-defects.md](D-source-defects.md) — реестр дефектов D-01…D-31.
