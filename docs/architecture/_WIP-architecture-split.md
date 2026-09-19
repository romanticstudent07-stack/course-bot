---
file: _WIP-architecture-split.md
block: "—"
title: "_WIP: нарезка остатка архитектуры (нормативный стек) — служебный журнал"
status: закрыт (13/13 кусков выгружены; дефекты источника перенесены в appendix/D-source-defects.md)
doc_version: "служебный, консолидированный"
---

> ⚠️ **HISTORICAL (исторический).**
> Этот файл — служебный журнал процесса нарезки. Он **не является источником истины**.
> Действующий реестр дефектов источника — [appendix/D-source-defects.md](appendix/D-source-defects.md)
> (D-01…D-31). Каталог верхнего уровня — [README.md](README.md).
> Правило «верхний файл vs подпапка» — [CANONICAL-SOURCES.md](CANONICAL-SOURCES.md).

# _WIP: нарезка остатка архитектуры (нормативный стек)

## Что делаем

Остаток архитектуры (Юридический блок + цепочка консолидации `И1→И2→И3→И4→Б17→ERRATA→SEAM-PATCH-1`) режется на 13 транспортных кусков и раскладывается в 11 файлов каталога `architecture/`.

## Правила работы (не менять по ходу)

1. Пользователь присылает по одному куску за сообщение, строго по порядку 01→12b. Никаких маркеров/конвертов пользователь НЕ проставляет.
2. Ассистент на каждый кусок: (а) даёт квитанцию (первая/последняя строка, перечень верхнеуровневых ключей), (б) выдаёт готовый файл, (в) выдаёт строки-вставки для README, (г) отмечает галочку в этом реестре.
3. Проза не переносится в YAML и не сокращается. YAML переносится дословно.
4. Границы кусков 07/08, 09/10, 12a/12b — транспортные: склеиваются в один файл.
5. При обработке ERRATA (12a/12b) ассистент проставляет обратные ссылки «переопределено E1 / E2 / E3 / E4 / FIX1 / FIX2» в уже созданные файлы И1, И2, И3, И4 — чтобы в каталоге не осталось двух противоречащих утверждений.
6. Патч B17-ADMIN-PANEL ≠ существующий `17-author-panel.md` (v3.4, NR-17.1…23). Не сливать. Отдельный файл + перекрёстная ссылка в обе стороны.
7. Дефекты исходника (невалидный YAML, висячие зависимости, пропуски в нумерации инвариантов) не правятся в каталоге — переносятся дословно и заводятся долгом в **[appendix/D-source-defects.md](appendix/D-source-defects.md)** (ранее «в разделе „Найденные дефекты исходника“ этого файла»).
8. Внутри подпапок имя файла начинается с номера папки (`99/99-00-digest.md`), чтобы имена были уникальны на весь репозиторий. Файлы `normative/` имеют собственные уникальные имена без числового префикса; порядок старшинства фиксируется таблицей в [normative/README.md](normative/README.md).

## Реестр кусков

| № | Кусок | Целевой файл | Принят | Файл выдан | README обновлён |
|---|-------|--------------|--------|-----------|-----------------|
| 01 | Legal — проза ВЫЖИМКА | [99/99-00-digest.md](99/99-00-digest.md) | ☑ | ☑ | ☑ |
| 02 | Legal — проза ПАТЧ v2 | [99/99-01-patch-v2.md](99/99-01-patch-v2.md) | ☑ | ☑ | ☑ |
| 03 | Legal — YAML v1 | [99/99-02-yaml-v1.md](99/99-02-yaml-v1.md) | ☑ | ☑ | ☑ |
| 04 | Legal — YAML v2-ext | [99/99-03-yaml-v2ext.md](99/99-03-yaml-v2ext.md) | ☑ | ☑ | ☑ |
| 05 | И1 Волна A | [normative/I1-wave-a.md](normative/I1-wave-a.md) | ☑ | ☑ | ☑ |
| 06 | И2 Волна B | [normative/I2-wave-b.md](normative/I2-wave-b.md) | ☑ | ☑ | ☑ |
| 07 | И3 Волна C ч.1 | [normative/I3-wave-c.md](normative/I3-wave-c.md) | ☑ | ☑ | ☑ |
| 08 | И3 Волна C ч.2 | [normative/I3-wave-c.md](normative/I3-wave-c.md) (склеено с 07) | ☑ | ☑ | ☑ |
| 09 | И4 Волна D ч.1 | [normative/I4-wave-d.md](normative/I4-wave-d.md) | ☑ | ☑ | ☑ |
| 10 | И4 Волна D ч.2 | [normative/I4-wave-d.md](normative/I4-wave-d.md) (склеено с 09) | ☑ | ☑ | ☑ |
| 11 | Б17 патч панели | [normative/B17-admin-panel-patch.md](normative/B17-admin-panel-patch.md) | ☑ | ☑ | ☑ |
| 12a | ERRATA разделы 1–6 | [normative/errata-unified.md](normative/errata-unified.md) | ☑ | ☑ | ☑ |
| 12b | ERRATA 7–11 + SEAM-1 | [normative/errata-unified.md](normative/errata-unified.md) + [normative/seam-patch-1-onboarding.md](normative/seam-patch-1-onboarding.md) | ☑ | ☑ | ☑ |

## Финальные шаги (после закрытия 13/13)

- ✅ Пересборка [appendix/A-patch1-global-rules.md](appendix/A-patch1-global-rules.md) (P1–P5 + YAML без `P6_place_command`).
- ✅ Пересборка [appendix/C-registries.md](appendix/C-registries.md) (парковка без блока 12 + риски 22 + команды 35 + инварианты + сроки + boot-gate).
- ✅ Создание [appendix/D-source-defects.md](appendix/D-source-defects.md) (реестр D-01…D-31).
- ✅ Пересборка [normative/README.md](normative/README.md) (единая ось старшинства, ERRATA-UNIFIED = высшая).
- ✅ Врезки «Переопределено/Уточнено ERRATA-UNIFIED» проставлены в 14 файлах корпуса и в [I3-wave-c.md](normative/I3-wave-c.md) (см. раздел IV финального отчёта).
- ✅ Реестр 1.10 в [01-architecture.md](01-architecture.md) актуализирован (все блоки закрыты, строка про Mini App поправлена согласно ERRATA / SEAM-1).
- ✅ Три остатка `/place` вычищены (Приложение B YAML, Приложение C парковка + блок 17, [08-working-group.md](08-working-group.md) п. 8.4, [06-participant-card.md](06-participant-card.md) п. 6.6 — висячая запятая).
- ✅ Ссылка `[errata-unified.md](errata-unified.md)` в [17-author-panel.md](17-author-panel.md) поправлена на `[normative/errata-unified.md](normative/errata-unified.md)`.
- ✅ В [99-legal.md](99-legal.md) поправлена подпись `[99/00-digest.md] → [99/99-00-digest.md]`, снята оговорка «когда он будет создан».
- ✅ В корневой README добавлена строка `debt/infra-C4-maintenance-contract.md` (12 файлов долга вместо 11).

## Дефекты источника

Все 31 дефект вынесены в [appendix/D-source-defects.md](appendix/D-source-defects.md) (D-01…D-31): юрблок (4), И1 (12), И2 (3), И3 (3), И4 (5), Б17 (3), ERRATA/SEAM-1 (1). Правки — в источник (`Архитектура(1).docx`), следующей волной поднимаются в каталог.

## Долги, не закрытые нарезкой

Задел для сборки `build/` (порядок сборки, DDL, API-контракт Mini App, схема конфигов, сводный CI-реестр). См. раздел VI финального отчёта Автору.
