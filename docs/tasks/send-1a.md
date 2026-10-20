# send-1a — render: HTML-текст, части «(часть k из N)», plain-text (Р252–Р254)

## 1. Паспорт
- id: send-1a · область: бот (apps/bot) · режим: Р0+ (КОДЕР — бесплатный чат, пакет + tools/unpack.py).
- Заголовок PR: feat(bot): render — HTML, части «(часть k из N)», plain-text (send-1a)
- Ветка: send-1a · Зависит от: нет (main 65fb74c). Миграций нет. send-1b начинать ПОСЛЕ мержа send-1a.

## 2. Цель
Чистые функции без сети и БД: собрать текст сообщения из шаблона text_registry и переменных, проверить HTML
по контракту формы Б9, разбить длинный текст на части (Р253), дать запасной plain-text (Р254).
Воркер outbox (send-1b) только вызывает эти функции.

## 3. Решения Автора
- 20.10 «ОК все рекомендации»: «В26 — А: send-1a (render, Р0+, КОДЕР, бесплатно) → send-1b (outbox-воркер, Р1, Агент,
  начинать после мержа 1a, РЕВЬЮЕР да)».
- Р-6 (docs/decisions/R-2026-10-1.md): настроек уведомлений нет, тихих часов нет — в render их нет.
- Тексты курса — только заглушки (репо публичный): в тестах строки вида «Тест абзац 1».

## 4. Выдержки (docs/architecture/09-communications.md; КОДЕР архитектуру не читает)
- Выжимка, контракт формы: «parse_mode=HTML единственный (MarkdownV2 запрещён), разрешённый набор тегов ограничен,
  все подстановки проходят html_escape … лимит 4096 символов — жёсткий, T1/T2 разбиваются … с суффиксом (часть k из N),
  T3 усекается до 900 символов». «Fail-closed дефолты: пропущенный тир → T1; невозможность собрать шаблон →
  отправка plain-text без parse_mode.»
- YAML text_form_technical_contract: allowed_tags: [b, i, u, s, code, pre, a, blockquote]; escape_placeholders: html_escape;
  placeholder_format: "{name:type}"; long_message_policy: T3: truncate_to_900, no_parts_suffix.
- Р252: «В <a> разрешены только схемы https/http/tg; mailto:/tel: в HTML-режиме запрещены».
- Р253: max_bytes_utf8: 4096; cut_at_last_whitespace_before: 4000; close_open_html_tags_at_boundary: true;
  reopen_same_tags_in_next_part: true; suffix: "(часть {k} из {N})".
- Р254: on_html_parse_error: strip_tags_and_send_plain; preserve_links_as: "{text} ({url})"; preserve_line_breaks: true.
- Вне задачи: plural_ru (Р255) — вместе с пушами; T3-гейты и Р260 (1 T3 в 24 ч) — сторона продюсера.

## 5. ЧТО ПРОЧИТАТЬ (КОДЕР) — по hash main из docs/STATE.md
| Файл | КБ | Зачем |
|---|---|---|
| docs/process/CODER.md | 11 | правила окна |
| AGENT-BRIEF.md | 15 | факты и запреты |
| docs/STATE.md | ≈ 17 | состояние |
| docs/tasks/send-1a.md (эта карточка) | ≈ 8 | задача |
| apps/bot/tests/test_bot.py | ≈ 4 | стиль тестов (pytest, без pytest-asyncio) |
Чтение КОДЕРА ≈ 55 КБ. render.py новый — читать нечего.

## 6. Файлы
- Создать: apps/bot/bot/render.py (≈ 200 строк), apps/bot/tests/test_render.py (≈ 150 строк).
- Не менять: остальное в apps/bot/**, apps/api/**, infra/**, docs/STATE.md (ШТАБ строк не дал).

## 7. Контракт apps/bot/bot/render.py (только stdlib: html, html.parser, re)
    TIERS = ("T1", "T2", "T3"); MAX_BYTES = 4096; CUT_BYTES = 4000; T3_MAX_CHARS = 900
    ALLOWED_TAGS = frozenset({"b", "i", "u", "s", "code", "pre", "a", "blockquote"}); LINK_SCHEMES = ("https", "http", "tg")
    class MissingVarError(ValueError)   # нет переменной → воркер кладёт строку в DLQ
    class TemplateError(ValueError)     # HTML не по контракту → воркер шлёт plain-text
    def normalize_tier(value: object) -> str
    def fill(template: str, variables: dict) -> str
    def check_html(text: str) -> None
    def split_html(text: str, tier: str) -> list[str]
    def to_plain(text: str) -> str
    def build_html_parts(template: str, variables: dict, tier: object) -> list[str]   # fill → check_html → split_html
    def build_plain_parts(template: str, variables: dict, tier: object) -> list[str]  # fill → to_plain → разбиение без тегов
Правила:
1. normalize_tier: значение не из TIERS (None, "", "t1", "X") → "T1" (fail-closed).
2. fill: плейсхолдер — \{([a-z_][a-z0-9_]*)(?::[a-z_]+)?\} («{name}» и «{n:hours}»); подстановка html.escape(str(v), quote=True);
   ключа нет или значение не str/int/float (bool тоже нельзя) → MissingVarError(имя). Остальной шаблон — доверенный HTML
   Автора, не экранируется. Скобки, не подходящие под регэксп, остаются как есть.
3. check_html (html.parser.HTMLParser) → TemplateError, если: тег не из ALLOWED_TAGS; тег не закрыт или лишний закрывающий;
   атрибут у любого тега, кроме a; у a атрибут не href или схема href не из LINK_SCHEMES (mailto:, tel:, javascript:,
   относительная ссылка). В тексте ошибки нет текста шаблона.
4. split_html:
   - T3: видимых символов (без тегов, после html.unescape) > 900 → оставить первые 900, обрезать по последнему пробелу
     (пробела нет — жёстко), закрыть открытые теги; суффикса нет; одна часть.
   - T1/T2: len(text.encode("utf-8")) ≤ 4096 → [text] без суффикса. Иначе каждая часть: заново открытые теги стека
     (с теми же атрибутами) + текст до 4000-го байта (считая открытые теги) с разрезом по последнему пробельному
     символу текста (не внутри тега, не внутри сущности &…;); пробела нет — по границе символа; затем закрыть
     открытые теги и добавить "\n\n(часть k из N)". N считается после разбиения (две фазы).
   - Каждая часть вместе с суффиксом ≤ 4096 байт UTF-8; пустых частей нет; пробел, по которому резали, отбрасывается.
5. to_plain: <a href="U">T</a> → «T (U)», при T == U — только U; остальные теги убрать; html.unescape; переводы строк сохранить.
6. build_plain_parts: то же разбиение, что в п. 4, но без тегов (T3 — до 900 символов). check_html здесь не вызывать.
7. Без print и логов. Модуль не знает про БД, aiogram и сеть.

## 8. БД: нет.

## 9. Тесты — apps/bot/tests/test_render.py (синхронные, без сети)
1. normalize_tier: "T2" → "T2"; None, "", "t1", "X" → "T1".
2. fill: «{name}» и «{n:hours}» подставлены; "<b>" в значении → "&lt;b&gt;"; кавычка → "&quot;"; нет ключа → MissingVarError;
   значение-список и True → MissingVarError; «{ не плейсхолдер }» осталась как есть.
3. check_html: все 8 тегов и a href https/http/tg → без ошибки; <script>, <br>, <span>, незакрытый <b>, лишний </i>,
   href "mailto:x", "tel:1", "javascript:x", "/rel", <b class="x"> → TemplateError.
4. Короткий T1 → одна часть без суффикса, равна входу.
5. Длинный T2 (≈ 10 000 байт кириллицы в абзацах) → N ≥ 3; каждая часть ≤ 4096 байт; суффиксы "(часть 1 из N)" … "(часть N из N)";
   слова всех частей (без суффиксов и тегов) в том же порядке = слова исходного текста.
6. Разрез внутри <b>…</b>: часть k кончается "</b>" перед суффиксом, часть k+1 начинается с "<b>"; <a href="https://x.test/">
   открывается заново с тем же href; каждая часть без суффикса проходит check_html.
7. Сущность &amp; у границы не разорвана; кириллица и эмодзи целы (каждая часть .encode().decode() без ошибок).
8. Текст без пробелов 9000 байт → разрез по границе символа, части ≤ 4096 байт.
9. T3 1500 видимых символов → одна часть, видимых ≤ 900, нет "(часть", теги закрыты (check_html без ошибки).
10. to_plain: «<a href="https://x.test/">Сайт</a>» → «Сайт (https://x.test/)»; «<b>a</b>\n<i>b</i>» → «a\nb»; «&lt;» → «<».
11. build_plain_parts длинного T1: нет "<b>", части ≤ 4096 байт, суффиксы есть.
12. Шаблон с <span>: build_html_parts → TemplateError; build_plain_parts того же шаблона → список частей.
Цель Codespaces: bash tools/check.sh bot. CI: bot (pytest), docker (сборка bot).

## 10. Сервер: нет (до send-1b код не вызывается; выката нет).

## 11. Запреты
- Только 2 файла из раздела 6. Новых зависимостей нет (stdlib). Не трогать apps/api/**, docs/architecture/**, .github/**,
  .env, docs/STATE.md, docs/DEFECTS-FOUND.md.
- Не делать: plural_ru, T3-гейты, тихие часы, настройки уведомлений (Р-6), MarkdownV2.
- Только тексты-заглушки. Запреты AGENT-BRIEF.md, раздел 3.

## 12. Готовность
render.py по разделу 7; тесты 1–12; check.sh bot зелёный; CI 7/7 зелёный.

## 13. Оценка
Автор ≈ 0,5 ч; кредиты 0 (Р0+).

## 14. РЕВЬЮЕР: нет — нет initData, 18+, согласий, ролей БД, секретов. Экранирование подстановок ШТАБ проверит в PR.
