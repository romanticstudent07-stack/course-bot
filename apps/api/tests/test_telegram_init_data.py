"""Тесты проверки Telegram initData (PR 1a): HMAC + TTL + зависимость FastAPI."""
import hashlib
import hmac
import json
import logging
import time
from urllib.parse import parse_qsl, quote, urlencode

import pytest

import app.telegram_init_data as tid
from app.config import Settings, get_settings
from app.telegram_init_data import (
    INIT_DATA_HEADER,
    InitDataError,
    InitDataReason,
    build_data_check_string,
    validate_init_data,
)
from tests.conftest import (
    FAKE_BOT_TOKEN,
    TEST_USER_ID,
    make_fields,
    sign_init_data,
    valid_init_data,
)

FIRST_LAUNCH = "/miniapp/v1/onboarding/first-launch"
ADULT = {"birth_date": "1990-01-01"}
MAX_AGE = 86400
SKEW = 60
NOW = 1_800_000_000


def validate(raw: str, now: float = NOW, **kw):
    params = {"bot_token": FAKE_BOT_TOKEN, "max_age_seconds": MAX_AGE, "future_skew_seconds": SKEW}
    params.update(kw)
    return validate_init_data(raw, now=now, **params)


def reason_of(raw: str, **kw) -> InitDataReason:
    with pytest.raises(InitDataError) as ei:
        validate(raw, **kw)
    return ei.value.reason


# ---------------- алгоритм ----------------


def test_hash_matches_telegram_algorithm_computed_independently():
    """Сверка с алгоритмом из документации Telegram, посчитанным здесь вручную."""
    fields = make_fields(auth_date=NOW, signature="sig-value")
    dcs = "\n".join(f"{k}={fields[k]}" for k in sorted(fields))
    secret = hmac.new(b"WebAppData", FAKE_BOT_TOKEN.encode(), hashlib.sha256).digest()
    expected = hmac.new(secret, dcs.encode(), hashlib.sha256).hexdigest()
    raw = urlencode({**fields, "hash": expected})
    assert validate(raw).tg_user_id == TEST_USER_ID


def test_valid_signature_parses_user_and_auth_date():
    user = {
        "id": 777,
        "first_name": "Ivan",
        "last_name": "Petrov",
        "username": "ivan",
        "language_code": "ru",
        "is_premium": True,
        "allows_write_to_pm": True,
        "photo_url": "https://t.me/i/userpic/320/x.svg",
    }
    ctx = validate(sign_init_data(make_fields(user=user, auth_date=NOW, start_param="ref1")))
    assert ctx.tg_user_id == 777
    assert ctx.auth_date == NOW
    assert ctx.user.first_name == "Ivan"
    assert ctx.user.username == "ivan"
    assert ctx.user.is_premium is True
    assert ctx.start_param == "ref1"
    assert ctx.query_id == "AAHdF6IQAAAAAN0XohDhrOrc"


def test_context_does_not_keep_raw_or_hash():
    raw = sign_init_data(make_fields(auth_date=NOW))
    ctx = validate(raw)
    h = dict(parse_qsl(raw))["hash"]
    assert h not in repr(ctx)
    assert not hasattr(ctx, "raw")


def test_wrong_token_is_bad_signature():
    raw = sign_init_data(make_fields(auth_date=NOW), bot_token="999:other-token")
    assert reason_of(raw) is InitDataReason.BAD_SIGNATURE


def test_tampered_hash_is_bad_signature():
    fields = make_fields(auth_date=NOW)
    pairs = dict(parse_qsl(sign_init_data(fields)))
    pairs["hash"] = ("0" if pairs["hash"][0] != "0" else "1") + pairs["hash"][1:]
    assert reason_of(urlencode(pairs)) is InitDataReason.BAD_SIGNATURE


def test_non_hex_hash_is_bad_signature():
    pairs = dict(parse_qsl(sign_init_data(make_fields(auth_date=NOW))))
    pairs["hash"] = "кириллица"
    assert reason_of(urlencode(pairs)) is InitDataReason.BAD_SIGNATURE


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("user", json.dumps({"id": 1, "first_name": "Evil"})),
        ("auth_date", str(NOW - 1)),
        ("query_id", "other"),
    ],
)
def test_modified_field_is_bad_signature(key, value):
    pairs = dict(parse_qsl(sign_init_data(make_fields(auth_date=NOW))))
    pairs[key] = value
    assert reason_of(urlencode(pairs)) is InitDataReason.BAD_SIGNATURE


def test_added_field_after_signing_is_bad_signature():
    pairs = dict(parse_qsl(sign_init_data(make_fields(auth_date=NOW))))
    pairs["start_param"] = "injected"
    assert reason_of(urlencode(pairs)) is InitDataReason.BAD_SIGNATURE


def test_signature_field_stays_in_data_check_string():
    fields = make_fields(auth_date=NOW, signature="abc_SIG-value")
    assert "signature=abc_SIG-value" in build_data_check_string(fields)
    raw = sign_init_data(fields)
    assert validate(raw).tg_user_id == TEST_USER_ID
    # Удаление signature после подписи ломает подпись — значит, поле в строке.
    pairs = dict(parse_qsl(raw))
    del pairs["signature"]
    assert reason_of(urlencode(pairs)) is InitDataReason.BAD_SIGNATURE


def test_hash_is_excluded_from_data_check_string():
    assert "hash=" not in build_data_check_string({"a": "1", "hash": "x", "b": "2"})
    assert build_data_check_string({"b": "2", "hash": "x", "a": "1"}) == "a=1\nb=2"


def test_unknown_optional_field_is_accepted():
    """security-checklist §7: новые поля Bot API (chat_join_request_query_id) не ломают проверку."""
    raw = sign_init_data(make_fields(auth_date=NOW, chat_join_request_query_id="q-1"))
    assert validate(raw).tg_user_id == TEST_USER_ID


def test_cyrillic_and_special_chars_in_user_are_url_encoded():
    user = {
        "id": 555,
        "first_name": "Иван & Ко =+% ?#/;",
        "last_name": "Пётр😀 \"кавычки\" \\ \n",
        "username": "ivan_ru",
    }
    fields = make_fields(user=user, auth_date=NOW)
    raw = sign_init_data(fields)
    assert "Иван" not in raw  # в сырой строке всё URL-кодировано
    ctx = validate(raw)
    assert ctx.user.first_name == "Иван & Ко =+% ?#/;"
    assert ctx.user.last_name == "Пётр😀 \"кавычки\" \\ \n"


def test_percent_encoded_spaces_as_telegram_sends():
    """Telegram кодирует пробел как %20, а не '+'. Обе формы должны проходить."""
    fields = make_fields(user={"id": 9, "first_name": "Анна Мария"}, auth_date=NOW)
    pairs = {**fields, "hash": tid.compute_hash(fields, FAKE_BOT_TOKEN)}
    raw = "&".join(f"{k}={quote(v, safe='')}" for k, v in pairs.items())
    assert "%20" in raw
    assert validate(raw).user.first_name == "Анна Мария"


def test_compare_digest_is_used(monkeypatch):
    calls = []
    real = hmac.compare_digest

    def spy(a, b):
        calls.append((a, b))
        return real(a, b)

    monkeypatch.setattr(tid.hmac, "compare_digest", spy)
    validate(valid_init_data(auth_date=NOW))
    assert len(calls) == 1
    with pytest.raises(InitDataError):
        validate(sign_init_data(make_fields(auth_date=NOW), bot_token="1:x"))
    assert len(calls) == 2


# ---------------- битая строка ----------------


@pytest.mark.parametrize(
    "raw",
    [
        "&&&",
        "no_equals_sign",
        "a=1&a=2&hash=x",  # повтор ключа
        "auth_date=%FF&hash=x",  # не UTF-8
    ],
)
def test_malformed_strings(raw):
    assert reason_of(raw) is InitDataReason.MALFORMED


def test_missing_hash_is_malformed():
    assert reason_of(urlencode(make_fields(auth_date=NOW))) is InitDataReason.MALFORMED


def test_empty_raw_is_missing():
    assert reason_of("") is InitDataReason.MISSING


@pytest.mark.parametrize("auth_date", ["", "abc", "-5", "1.5", "١٢٣"])
def test_bad_auth_date_is_malformed(auth_date):
    fields = make_fields(auth_date=NOW)
    fields["auth_date"] = auth_date
    assert reason_of(sign_init_data(fields)) is InitDataReason.MALFORMED


def test_missing_auth_date_is_malformed():
    fields = make_fields(auth_date=NOW)
    del fields["auth_date"]
    assert reason_of(sign_init_data(fields)) is InitDataReason.MALFORMED


@pytest.mark.parametrize(
    "user_raw",
    [None, "", "not json", "[]", '{"first_name":"x"}', '{"id":"42"}', '{"id":true}', '{"id":0}'],
)
def test_bad_user_is_malformed(user_raw):
    fields = make_fields(auth_date=NOW)
    if user_raw is None:
        del fields["user"]
    else:
        fields["user"] = user_raw
    assert reason_of(sign_init_data(fields)) is InitDataReason.MALFORMED


def test_empty_bot_token_raises_value_error():
    with pytest.raises(ValueError):
        validate(valid_init_data(auth_date=NOW), bot_token="")


# ---------------- свежесть auth_date ----------------


def test_auth_date_exactly_at_ttl_is_accepted():
    assert validate(valid_init_data(auth_date=NOW - MAX_AGE)).auth_date == NOW - MAX_AGE


def test_auth_date_expired_by_one_second():
    assert reason_of(valid_init_data(auth_date=NOW - MAX_AGE - 1)) is InitDataReason.EXPIRED


def test_auth_date_custom_ttl():
    raw = valid_init_data(auth_date=NOW - 301)
    assert reason_of(raw, max_age_seconds=300) is InitDataReason.EXPIRED


def test_auth_date_future_within_skew_is_accepted():
    assert validate(valid_init_data(auth_date=NOW + SKEW)).auth_date == NOW + SKEW


def test_auth_date_future_beyond_skew_is_rejected():
    assert reason_of(valid_init_data(auth_date=NOW + SKEW + 1)) is InitDataReason.FUTURE


def test_expired_check_happens_after_signature():
    """Просроченная строка с неверной подписью — это bad_signature, а не expired."""
    raw = sign_init_data(make_fields(auth_date=NOW - MAX_AGE - 100), bot_token="1:x")
    assert reason_of(raw) is InitDataReason.BAD_SIGNATURE


# ---------------- HTTP: зависимость ----------------


def test_http_no_header_401_missing(api_client):
    r = api_client.post(FIRST_LAUNCH, json=ADULT)
    assert r.status_code == 401
    assert r.json()["code"] == "TG_INIT_MISSING"


@pytest.mark.parametrize("value", ["", "   "])
def test_http_empty_header_401_missing(api_client, value):
    r = api_client.post(FIRST_LAUNCH, json=ADULT, headers={INIT_DATA_HEADER: value})
    assert r.status_code == 401
    assert r.json()["code"] == "TG_INIT_MISSING"


@pytest.mark.parametrize(
    "make_raw",
    [
        lambda: sign_init_data(make_fields(), bot_token="1:other"),  # неверная подпись
        lambda: valid_init_data(auth_date=int(time.time()) - MAX_AGE - 10),  # просрочено
        lambda: valid_init_data(auth_date=int(time.time()) + 3600),  # из будущего
        lambda: "garbage",  # битая строка
    ],
    ids=["bad_signature", "expired", "future", "malformed"],
)
def test_http_invalid_is_401_without_leaks(api_client, caplog, make_raw):
    raw = make_raw()
    caplog.set_level(logging.DEBUG)
    r = api_client.post(FIRST_LAUNCH, json=ADULT, headers={INIT_DATA_HEADER: raw})
    assert r.status_code == 401
    body = r.json()
    assert body["code"] == "TG_INIT_INVALID"
    assert set(body) == {"code", "message"}

    text = r.text + caplog.text
    assert FAKE_BOT_TOKEN not in text
    assert raw not in text
    pairs = dict(parse_qsl(raw))
    if pairs.get("hash"):
        assert pairs["hash"] not in text
        assert tid.compute_hash(pairs, FAKE_BOT_TOKEN) not in text  # ожидаемый hash
    assert "auth_date=" not in text  # нет data_check_string
    assert "reason=" in caplog.text  # причина в логе есть


def test_http_valid_is_501_with_own_tg_user_id(api_client, caplog):
    caplog.set_level(logging.DEBUG)
    raw = valid_init_data(user={"id": 123456789, "first_name": "Автор"})
    r = api_client.post(FIRST_LAUNCH, json=ADULT, headers={INIT_DATA_HEADER: raw})
    assert r.status_code == 501
    assert r.json()["details"] == {"tg_user_id": 123456789}
    assert raw not in caplog.text
    assert FAKE_BOT_TOKEN not in caplog.text


def test_http_empty_bot_token_is_503(api_client, caplog):
    from main import app

    app.dependency_overrides[get_settings] = lambda: Settings(bot_token="")
    caplog.set_level(logging.DEBUG)
    r = api_client.post(FIRST_LAUNCH, json=ADULT, headers={INIT_DATA_HEADER: valid_init_data()})
    assert r.status_code == 503
    assert r.json() == {"code": "SERVICE_MISCONFIGURED", "message": "Сервис временно недоступен"}
    assert any(rec.levelno == logging.ERROR for rec in caplog.records)


def test_http_healthz_without_header(api_client):
    assert api_client.get("/healthz").status_code == 200


def test_every_miniapp_v1_route_requires_init_data(api_client):
    """Страховка: КАЖДЫЙ маршрут /miniapp/v1/** из OpenAPI без заголовка → 401.

    Проверяем поведение, а не внутренности FastAPI (с 0.141 роутеры включаются лениво).
    Тело пустое: зависимость роутера срабатывает раньше валидации тела (иначе было бы 422).
    """
    paths = api_client.app.openapi()["paths"]
    checked = 0
    for path, methods in paths.items():
        if not path.startswith("/miniapp/v1/"):
            continue
        url = path.replace("{", "").replace("}", "")  # подставить что-то в path-параметры
        for method in methods:
            r = api_client.request(method.upper(), url)
            assert r.status_code == 401, (method, path, r.status_code)
            assert r.json()["code"] == "TG_INIT_MISSING", (method, path)
            checked += 1
    assert checked >= 1, "нет ни одного маршрута /miniapp/v1"


def test_openapi_has_only_expected_public_routes(api_client):
    """Маршруты вне /miniapp/v1 (без initData) — только /healthz и /security/csp-report."""
    public = {p for p in api_client.app.openapi()["paths"] if not p.startswith("/miniapp/v1/")}
    assert public == {"/healthz", "/security/csp-report"}


def test_router_level_dependency_protects_route_without_own_depends():
    """Новый роутер Mini App без собственного Depends всё равно защищён (уровень роутера)."""
    from fastapi import APIRouter, FastAPI
    from fastapi.testclient import TestClient

    from app.errors import install_error_handlers
    from main import build_miniapp_v1_router

    dummy = APIRouter(prefix="/dummy")

    @dummy.get("/ping")
    async def ping() -> dict[str, str]:
        return {"ok": "yes"}

    app = FastAPI()
    install_error_handlers(app)
    app.include_router(build_miniapp_v1_router(dummy))
    app.dependency_overrides[get_settings] = lambda: Settings(bot_token=FAKE_BOT_TOKEN)
    client = TestClient(app)

    r = client.get("/miniapp/v1/dummy/ping")
    assert r.status_code == 401
    assert r.json()["code"] == "TG_INIT_MISSING"
    r = client.get("/miniapp/v1/dummy/ping", headers={INIT_DATA_HEADER: valid_init_data()})
    assert r.status_code == 200
