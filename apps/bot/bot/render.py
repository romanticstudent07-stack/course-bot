"""Рендер сообщений бота (send-1a, Р252–Р254): чистые функции без сети и БД.

Шаблон text_registry + переменные -> текст для parse_mode=HTML или запасной plain-text.
Порядок для воркера outbox (send-1b):
    build_html_parts(...): MissingVarError -> строка в DLQ; TemplateError -> build_plain_parts(...)
Контракт формы: теги только b, i, u, s, code, pre, a, blockquote; у <a> только href со схемой
https/http/tg; все подстановки проходят html.escape. Лимит части 4096 байт UTF-8; T1/T2 режутся
на части с суффиксом «(часть k из N)», T3 усекается до 900 видимых символов без суффикса.
Модуль ничего не печатает и не логирует; про aiogram, БД и сеть не знает.
"""
import html
import re
from html.parser import HTMLParser

TIERS = ("T1", "T2", "T3")
MAX_BYTES = 4096
CUT_BYTES = 4000
T3_MAX_CHARS = 900
ALLOWED_TAGS = frozenset({"b", "i", "u", "s", "code", "pre", "a", "blockquote"})
LINK_SCHEMES = ("https", "http", "tg")


class MissingVarError(ValueError):
    """Нет переменной для плейсхолдера или значение не str/int/float. Текст ошибки — имя."""


class TemplateError(ValueError):
    """HTML не по контракту формы. Текст ошибки — причина, без текста шаблона."""


_PLACEHOLDER_RE = re.compile(r"\{([a-z_][a-z0-9_]*)(?::[a-z_]+)?\}")
# Голые & и < (Ф14): & — только в начале сущности, < — только в начале разрешённого тега.
_ENTITY_AT_RE = re.compile(r"&(?:[A-Za-z][A-Za-z0-9]*|#[0-9]+|#[xX][0-9A-Fa-f]+);")
_TAG_AT_RE = re.compile(r'</?([A-Za-z][A-Za-z0-9]*)(?:[^<>"\']|"[^"]*"|\'[^\']*\')*>')
_SCHEME_RE = re.compile(r"^([A-Za-z][A-Za-z0-9+.\-]*):")
# Токены HTML: тег целиком | сущность &…; целиком | один символ.
_TOKEN_RE = re.compile(
    r'<(/?)([A-Za-z][A-Za-z0-9]*)(?:[^>"\']|"[^"]*"|\'[^\']*\')*>'
    r"|&(?:#[0-9]+|#[xX][0-9A-Fa-f]+|[A-Za-z][A-Za-z0-9]*);"
    r"|.",
    re.S,
)


def _blen(s: str) -> int:
    return len(s.encode("utf-8"))


def _suffix(k: int, n: int) -> str:
    return f"\n\n(часть {k} из {n})"


_SUFFIX_RESERVE = _blen(_suffix(99999, 99999))


def normalize_tier(value: object) -> str:
    """Тир из TIERS; любое другое значение (None, "", "t1", "X") -> "T1" (fail-closed)."""
    if isinstance(value, str) and value in TIERS:
        return value
    return "T1"


def fill(template: str, variables: dict) -> str:
    """Подставить {name} и {name:type}; значения экранируются, остальной шаблон — доверенный HTML."""

    def repl(m: re.Match) -> str:
        name = m.group(1)
        if name not in variables:
            raise MissingVarError(name)
        value = variables[name]
        if isinstance(value, bool) or not isinstance(value, (str, int, float)):
            raise MissingVarError(name)
        return html.escape(str(value), quote=True)

    return _PLACEHOLDER_RE.sub(repl, template)


def _href_ok(href) -> bool:
    if not href:
        return False
    m = _SCHEME_RE.match(href)
    return bool(m) and m.group(1).lower() in LINK_SCHEMES


class _Checker(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[str] = []
        self.error: str | None = None

    def _fail(self, reason: str) -> None:
        if self.error is None:
            self.error = reason

    def handle_starttag(self, tag, attrs):
        if tag not in ALLOWED_TAGS:
            self._fail("тег вне разрешённого набора")
        elif tag == "a":
            if len(attrs) != 1 or attrs[0][0] != "href" or not _href_ok(attrs[0][1]):
                self._fail("у <a> разрешён только href со схемой https/http/tg")
        elif attrs:
            self._fail("атрибуты разрешены только у <a>")
        self.stack.append(tag)

    def handle_startendtag(self, tag, attrs):
        self._fail("самозакрывающийся тег")

    def handle_endtag(self, tag):
        if self.stack and self.stack[-1] == tag:
            self.stack.pop()
        else:
            self._fail("лишний или непарный закрывающий тег")

    def handle_comment(self, data):
        self._fail("комментарий в HTML")

    def handle_decl(self, decl):
        self._fail("объявление в HTML")

    def unknown_decl(self, data):
        self._fail("объявление в HTML")

    def handle_pi(self, data):
        self._fail("инструкция обработки в HTML")


def _check_bare(text: str) -> None:
    """«&» не в начале сущности и «<» не в начале разрешённого тега -> TemplateError."""
    for m in re.finditer(r"[&<]", text):
        pos = m.start()
        if text[pos] == "&":
            if not _ENTITY_AT_RE.match(text, pos):
                raise TemplateError("голый & вне сущности")
        else:
            tag = _TAG_AT_RE.match(text, pos)
            if not tag or tag.group(1).lower() not in ALLOWED_TAGS:
                raise TemplateError("голый < вне разрешённого тега")


def check_html(text: str) -> None:
    """Проверить HTML по контракту формы; нарушение -> TemplateError (без текста шаблона)."""
    _check_bare(text)
    parser = _Checker()
    try:
        parser.feed(text)
        parser.close()
    except Exception:
        raise TemplateError("HTML не разбирается") from None
    if parser.error is None and parser.stack:
        parser.error = "тег не закрыт"
    if parser.error is not None:
        raise TemplateError(parser.error)


class _Tok:
    """Токен: open / close (тег) или text (символ либо сущность &…;)."""

    __slots__ = ("kind", "raw", "name", "chars", "ws", "size")

    def __init__(self, kind: str, raw: str, name: str = "", chars: int = 0, ws: bool = False):
        self.kind = kind
        self.raw = raw
        self.name = name
        self.chars = chars
        self.ws = ws
        self.size = _blen(raw)


def _tokenize_html(text: str) -> list:
    toks = []
    for m in _TOKEN_RE.finditer(text):
        raw = m.group(0)
        if m.group(2):
            toks.append(_Tok("close" if m.group(1) else "open", raw, m.group(2).lower()))
        else:
            toks.append(_Tok("text", raw, chars=len(html.unescape(raw)), ws=raw.isspace()))
    return toks


def _tokenize_plain(text: str) -> list:
    return [_Tok("text", ch, chars=1, ws=ch.isspace()) for ch in text]


def _push(stack: list, tok) -> list:
    """Новый стек открытых тегов после токена (старый список не меняется)."""
    if tok.kind == "open":
        return stack + [tok]
    if tok.kind == "close":
        for idx in range(len(stack) - 1, -1, -1):
            if stack[idx].name == tok.name:
                return stack[:idx]
    return stack


def _closers(stack: list) -> str:
    return "".join(f"</{t.name}>" for t in reversed(stack))


def _take(toks: list, start: int, stack: list, cut_bytes: int, total_bytes: int, max_chars):
    """Набрать одну часть с позиции start -> (тело, следующая позиция, стек в конце).

    Тело = заново открытые теги стека (те же атрибуты) + текст + закрытие открытых тегов.
    Лимиты: открытые теги + текст <= cut_bytes; вместе с закрытиями <= total_bytes;
    видимых символов <= max_chars (если задан). Разрез — по последнему пробельному символу
    текста (он отбрасывается); пробела нет — по границе символа. Тег и сущность не рвутся.
    """
    prefix = "".join(t.raw for t in stack)
    out = [prefix]
    size = _blen(prefix)
    cur = stack
    cur_close = _blen(_closers(cur))
    chars = 0
    seen_text = False
    last_ws = None
    j = start
    n = len(toks)
    while j < n:
        t = toks[j]
        nxt = _push(cur, t)
        nxt_close = cur_close if nxt is cur else _blen(_closers(nxt))
        if size + t.size > cut_bytes or size + t.size + nxt_close > total_bytes:
            break
        if t.kind == "text":
            if max_chars is not None and chars + t.chars > max_chars:
                break
            if not t.ws:
                seen_text = True
            elif seen_text:
                last_ws = (j, len(out), cur)
            chars += t.chars
        out.append(t.raw)
        size += t.size
        cur, cur_close = nxt, nxt_close
        j += 1
    if j >= n:
        return "".join(out) + _closers(cur), j, cur
    if last_ws is not None:
        ws_j, n_out, ws_stack = last_ws
        return "".join(out[:n_out]) + _closers(ws_stack), ws_j + 1, ws_stack
    if not seen_text:
        raise TemplateError("часть не вмещает ни одного символа текста")
    return "".join(out) + _closers(cur), j, cur


def _split_tokens(toks: list, text: str, tier: str) -> list[str]:
    if tier == "T3":
        body, _, _ = _take(toks, 0, [], MAX_BYTES, MAX_BYTES, T3_MAX_CHARS)
        return [body]
    if _blen(text) <= MAX_BYTES:
        return [text]
    has_text_from = [False] * (len(toks) + 1)
    for idx in range(len(toks) - 1, -1, -1):
        t = toks[idx]
        has_text_from[idx] = has_text_from[idx + 1] or (t.kind == "text" and not t.ws)
    bodies: list[str] = []
    i, stack = 0, []
    # Фаза 1: тела частей. Хвост без видимого текста (закрытия, пробелы) не даёт пустую часть.
    while i < len(toks) and has_text_from[i]:
        body, i, stack = _take(toks, i, stack, CUT_BYTES, MAX_BYTES - _SUFFIX_RESERVE, None)
        bodies.append(body)
    if len(bodies) <= 1:
        return bodies
    # Фаза 2: N известно — добавить суффиксы.
    total = len(bodies)
    return [body + _suffix(k, total) for k, body in enumerate(bodies, 1)]


def split_html(text: str, tier: str) -> list[str]:
    """Разбить HTML на части по Р253 (T1/T2) или усечь до 900 видимых символов (T3)."""
    return _split_tokens(_tokenize_html(text), text, normalize_tier(tier))


class _Plain(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.links: list[tuple[str, int]] = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            href = ""
            for key, value in attrs:
                if key == "href" and value:
                    href = value
            self.links.append((href, len(self.out)))

    def handle_endtag(self, tag):
        if tag != "a" or not self.links:
            return
        href, pos = self.links.pop()
        if not href:
            return
        label = "".join(self.out[pos:]).strip()
        if not label or label == href:
            self.out[pos:] = [href]
        else:
            self.out.append(f" ({href})")

    def handle_data(self, data):
        self.out.append(data)


def to_plain(text: str) -> str:
    """HTML -> plain-text (Р254): <a href="U">T</a> -> «T (U)», теги убрать, сущности раскрыть."""
    parser = _Plain()
    try:
        parser.feed(text)
        parser.close()
    except Exception:
        return html.unescape(re.sub(r"<[^>]*>", "", text))
    return "".join(parser.out)


def build_html_parts(template: str, variables: dict, tier: object) -> list[str]:
    """fill -> check_html -> split_html. MissingVarError / TemplateError — наружу, воркеру."""
    text = fill(template, variables)
    check_html(text)
    return split_html(text, normalize_tier(tier))


def build_plain_parts(template: str, variables: dict, tier: object) -> list[str]:
    """fill -> to_plain -> то же разбиение без тегов (для отправки без parse_mode)."""
    plain = to_plain(fill(template, variables))
    return _split_tokens(_tokenize_plain(plain), plain, normalize_tier(tier))
