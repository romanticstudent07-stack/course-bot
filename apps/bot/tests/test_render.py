"""Тесты render (send-1a): шаблон, контракт HTML, части «(часть k из N)», plain-text — без сети."""
import html
import re

import pytest

from bot import render
from bot.render import MissingVarError, TemplateError

SUFFIX_RE = re.compile(r"\n\n\(часть (\d+) из (\d+)\)$")
TAG_RE = re.compile(r"<[^>]+>")
LINK = '<a href="https://x.test/">'


def _blen(s: str) -> int:
    return len(s.encode("utf-8"))


def _body(part: str) -> str:
    return SUFFIX_RE.sub("", part)


def _words(text: str) -> list[str]:
    return TAG_RE.sub(" ", text).split()


def _visible(text: str) -> str:
    return html.unescape(TAG_RE.sub("", text))


def _long_text(n_bytes: int = 10_000) -> str:
    paras: list[str] = []
    k = 0
    while _blen("\n\n".join(paras)) < n_bytes:
        k += 1
        paras.append(f"Тест абзац {k}. " + " ".join(f"слово{k}_{i}" for i in range(20)))
    return "\n\n".join(paras)


# 1. Тир
@pytest.mark.parametrize("value", ["T1", "T2", "T3"])
def test_normalize_tier_keeps_known(value):
    assert render.normalize_tier(value) == value


@pytest.mark.parametrize("value", [None, "", "t1", "X", 1])
def test_normalize_tier_fail_closed(value):
    assert render.normalize_tier(value) == "T1"


# 2. fill
def test_fill_substitutes_and_escapes():
    out = render.fill("Тест {name}, осталось {n:hours} ч.", {"name": '<b>"Тест"</b>', "n": 3})
    assert out == "Тест &lt;b&gt;&quot;Тест&quot;&lt;/b&gt;, осталось 3 ч."
    assert render.fill("{x}", {"x": 1.5}) == "1.5"


def test_fill_keeps_trusted_html_and_non_placeholders():
    tpl = "<b>{name}</b> { не плейсхолдер } {Name} {}"
    assert render.fill(tpl, {"name": "Тест"}) == "<b>Тест</b> { не плейсхолдер } {Name} {}"


@pytest.mark.parametrize("variables", [{}, {"name": ["a"]}, {"name": True}, {"name": None}])
def test_fill_missing_or_bad_value(variables):
    with pytest.raises(MissingVarError) as err:
        render.fill("Тест {name}", variables)
    assert str(err.value) == "name"


# 3. check_html
def test_check_html_allows_contract():
    good = (
        "<b>ж</b> <i>к</i> <u>п</u> <s>з</s> <code>к</code> <pre>п</pre> "
        "<blockquote>ц</blockquote> <b><i>вложенный</i></b> "
        '<a href="https://x.test/">с</a> <a href="http://x.test/">с</a> '
        '<a href="tg://resolve?domain=x">с</a> &amp; &lt;'
    )
    render.check_html(good)


@pytest.mark.parametrize(
    "bad",
    [
        "<script>x</script>",
        "a<br>b",
        "a<br/>b",
        "<span>x</span>",
        "<b>x",
        "x</i>",
        "<b><i>x</b></i>",
        '<a href="mailto:x">m</a>',
        '<a href="tel:1">t</a>',
        '<a href="javascript:x">j</a>',
        '<a href="/rel">r</a>',
        "<a>n</a>",
        '<a href="https://x.test/" title="t">t</a>',
        '<b class="x">x</b>',
        "<!-- c -->",
    ],
)
def test_check_html_rejects(bad):
    with pytest.raises(TemplateError):
        render.check_html(bad)


@pytest.mark.parametrize(
    "bad",
    [
        "A & B",
        "a &amp b",
        "&;",
        "&#;",
        "&#x;",
        "&#xZZ;",
        "a < b",
        "a <3 b",
        "<b>x</b> < y",
        "<>",
        "</>",
        "<b x</b>",
        "a <<b>x</b>",
    ],
)
def test_check_html_rejects_bare_amp_and_lt(bad):
    with pytest.raises(TemplateError):
        render.check_html(bad)


@pytest.mark.parametrize(
    "good",
    ["&amp; &lt; &gt; &quot;", "&#38; &#x26; &#X3C;", "a > b", "<B>x</B>", "<b>x</b>&nbsp;y"],
)
def test_check_html_allows_entities_and_tags(good):
    render.check_html(good)


def test_bare_amp_lt_error_has_no_template_text():
    for bad in ("секрет & тайна", "секрет < тайна"):
        with pytest.raises(TemplateError) as err:
            render.check_html(bad)
        assert "секрет" not in str(err.value) and "тайна" not in str(err.value)


def test_build_html_parts_bare_amp_falls_to_plain_path():
    with pytest.raises(TemplateError):
        render.build_html_parts("A & {name}", {"name": "x"}, "T1")
    assert render.build_plain_parts("A & {name}", {"name": "x"}, "T1") == ["A & x"]


def test_check_html_error_has_no_template_text():
    with pytest.raises(TemplateError) as err:
        render.check_html("<span>секрет</span>")
    assert "секрет" not in str(err.value)


# 4. Короткий текст
def test_short_t1_single_part_unchanged():
    text = "<b>Тест</b> абзац 1"
    assert render.split_html(text, "T1") == [text]
    assert render.build_html_parts("<b>{name}</b>", {"name": "<script>"}, None) == ["<b>&lt;script&gt;</b>"]


# 5. Длинный T2
def test_split_long_t2_parts_and_words():
    text = _long_text()
    parts = render.split_html(text, "T2")
    n = len(parts)
    assert n >= 3
    words: list[str] = []
    for k, part in enumerate(parts, 1):
        assert _blen(part) <= render.MAX_BYTES
        assert part.endswith(f"\n\n(часть {k} из {n})")
        assert _visible(_body(part)).strip()
        words += _words(_body(part))
    assert words == _words(text)


# 6. Разрез внутри тегов
def test_split_closes_and_reopens_b():
    text = "<b>" + _long_text(9000) + "</b>"
    parts = render.split_html(text, "T1")
    assert len(parts) >= 3
    for part in parts:
        body = _body(part)
        assert body.startswith("<b>") and body.endswith("</b>")
        render.check_html(body)


def test_split_reopens_link_with_same_href():
    text = LINK + _long_text(9000) + "</a>"
    parts = render.split_html(text, "T1")
    assert len(parts) >= 3
    for part in parts:
        body = _body(part)
        assert body.startswith(LINK) and body.endswith("</a>")
        render.check_html(body)


# 7. Сущности, кириллица, эмодзи
@pytest.mark.parametrize("text", ["Тест &amp; 😀ё " * 800, "ё&amp;😀" * 1000])
def test_split_keeps_entities_and_emoji(text):
    parts = render.split_html(text, "T1")
    assert len(parts) >= 2
    for part in parts:
        assert _blen(part) <= render.MAX_BYTES
        assert part.encode("utf-8").decode("utf-8") == part
        body = _body(part)
        assert body.count("&") == body.count("&amp;")
        render.check_html(body)


# 8. Без пробелов
def test_split_without_spaces_cuts_by_char():
    text = "ж" * 4500
    parts = render.split_html(text, "T1")
    assert len(parts) >= 3
    assert all(_blen(p) <= render.MAX_BYTES for p in parts)
    assert "".join(_body(p) for p in parts) == text


# 9. T3
def test_t3_truncated_to_900_visible():
    text = "<b>" + "Тест " * 300 + "</b>"
    parts = render.split_html(text, "T3")
    assert len(parts) == 1
    part = parts[0]
    assert len(_visible(part)) <= render.T3_MAX_CHARS
    assert "(часть" not in part
    assert part.startswith("<b>Тест") and part.endswith("</b>")
    render.check_html(part)


def test_t3_short_unchanged():
    assert render.split_html("<i>Тест</i>", "T3") == ["<i>Тест</i>"]


# 10. to_plain
def test_to_plain():
    assert render.to_plain(LINK + "Сайт</a>") == "Сайт (https://x.test/)"
    assert render.to_plain(LINK + "https://x.test/</a>") == "https://x.test/"
    assert render.to_plain("<b>a</b>\n<i>b</i>") == "a\nb"
    assert render.to_plain("&lt;") == "<"


# 11. build_plain_parts
def test_build_plain_parts_long_t1():
    tpl = "<b>{name}</b>\n\n" + _long_text()
    parts = render.build_plain_parts(tpl, {"name": "Тест"}, "T1")
    n = len(parts)
    assert n >= 3
    for k, part in enumerate(parts, 1):
        assert "<b>" not in part
        assert _blen(part) <= render.MAX_BYTES
        assert part.endswith(f"\n\n(часть {k} из {n})")


def test_build_plain_parts_t3():
    parts = render.build_plain_parts("<b>Тест</b> " + "абзац " * 300, {}, "T3")
    assert len(parts) == 1
    assert len(parts[0]) <= render.T3_MAX_CHARS
    assert "(часть" not in parts[0]


# 12. Плохой шаблон: HTML отклонён, plain-text собирается
def test_bad_template_html_raises_plain_works():
    tpl = "<span>Тест {name}</span> " + LINK + "Сайт</a>"
    with pytest.raises(TemplateError):
        render.build_html_parts(tpl, {"name": "абзац"}, "T2")
    assert render.build_plain_parts(tpl, {"name": "абзац"}, "T2") == ["Тест абзац Сайт (https://x.test/)"]
    with pytest.raises(MissingVarError):
        render.build_html_parts(tpl, {}, "T2")
