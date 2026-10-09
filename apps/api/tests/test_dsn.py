"""B-3a-2: свой DSN у проектора и загрузчика текстов (docs/tasks/B-3a-2.md, раздел 9).

Без БД: соединений нет, get_engine и запись в БД подменены заглушками.
conftest не импортируем (урок B-3a-1): все константы — здесь.
"""
from __future__ import annotations

import logging

import pytest

import app.config as config
import app.db.session as db_session
import app.projector as projector
import app.texts as texts
from app.config import Settings

DSN_API = "postgresql+psycopg://api_user:pw-api-1@db:5432/d"
DSN_PROJECTOR = "postgresql+psycopg://proj_user:pw-proj-1@db:5432/d"
DSN_MIGRATIONS = "postgresql+psycopg://owner_user:pw-mig-1@db:5432/d"
ENV_NAMES = ("DATABASE_URL", "PROJECTOR_DATABASE_URL", "MIGRATIONS_DATABASE_URL")

# (метод, поле настроек, свой DSN)
CASES = [
    ("projector_dsn", "projector_database_url", DSN_PROJECTOR),
    ("migrations_dsn", "migrations_database_url", DSN_MIGRATIONS),
]


@pytest.fixture
def clean_env(monkeypatch):
    """Без DSN-переменных окружения; кэш get_settings чистится до и после теста."""
    for name in ENV_NAMES:
        monkeypatch.delenv(name, raising=False)
    config.get_settings.cache_clear()
    yield monkeypatch
    config.get_settings.cache_clear()


def _settings(**kwargs) -> Settings:
    return Settings(postgres_user="u", postgres_password="x", postgres_db="d", **kwargs)


# 1–2. Свой DSN задан → он.
@pytest.mark.parametrize("method, field, own", CASES)
def test_own_dsn_wins(clean_env, method, field, own):
    s = _settings(database_url=DSN_API, **{field: own})
    assert getattr(s, method)() == own


# 1–2. Не задан или "" → DATABASE_URL.
@pytest.mark.parametrize("value", [None, ""])
@pytest.mark.parametrize("method, field, own", CASES)
def test_fallback_to_database_url(clean_env, method, field, own, value):
    s = _settings(database_url=DSN_API, **{field: value})
    assert getattr(s, method)() == DSN_API


# 1–2. Оба не заданы → то же, что sqlalchemy_dsn() из POSTGRES_*.
@pytest.mark.parametrize("method, field, own", CASES)
def test_fallback_to_postgres_parts(clean_env, method, field, own):
    s = _settings(database_url=None, **{field: None})
    dsn = getattr(s, method)()
    assert dsn == s.sqlalchemy_dsn()
    assert dsn.startswith("postgresql+psycopg://u:x@")
    assert dsn.endswith("/d")


# 3. Переменные окружения видны Settings().
def test_env_variables_are_read(clean_env):
    clean_env.setenv("PROJECTOR_DATABASE_URL", DSN_PROJECTOR)
    clean_env.setenv("MIGRATIONS_DATABASE_URL", DSN_MIGRATIONS)
    s = Settings()
    assert s.projector_database_url == DSN_PROJECTOR
    assert s.migrations_database_url == DSN_MIGRATIONS
    assert s.projector_dsn() == DSN_PROJECTOR
    assert s.migrations_dsn() == DSN_MIGRATIONS


# 3. Пустая переменная окружения = не задана.
def test_empty_env_variable_means_not_set(clean_env):
    clean_env.setenv("DATABASE_URL", DSN_API)
    clean_env.setenv("PROJECTOR_DATABASE_URL", "")
    clean_env.setenv("MIGRATIONS_DATABASE_URL", "")
    s = Settings()
    assert s.projector_dsn() == DSN_API
    assert s.migrations_dsn() == DSN_API


# 4. API не затронут (I2: API не ходит ролью проектора).
def test_api_dsn_unchanged(clean_env):
    s = Settings(
        database_url=DSN_API,
        projector_database_url=DSN_PROJECTOR,
        migrations_database_url=DSN_MIGRATIONS,
    )
    assert s.sqlalchemy_dsn() == DSN_API


def _assert_no_secret(secret: str, capsys, caplog) -> str:
    out = capsys.readouterr()
    for captured in (out.out, out.err, caplog.text):
        assert secret not in captured
    return out.out


# 5. projector.main(["once"]) берёт PROJECTOR_DATABASE_URL; пароль не в выводе.
def test_projector_main_uses_projector_dsn(clean_env, capsys, caplog):
    clean_env.setenv("DATABASE_URL", DSN_API)
    clean_env.setenv("PROJECTOR_DATABASE_URL", DSN_PROJECTOR)
    caplog.set_level(logging.DEBUG)
    engine = object()
    seen: list[Settings] = []

    def fake_get_engine(settings):
        seen.append(settings)
        return engine

    def fake_run_once(got_engine):
        assert got_engine is engine
        return projector.ProjectorResult(0, 0)

    clean_env.setattr(projector, "get_engine", fake_get_engine)
    clean_env.setattr(projector, "run_once", fake_run_once)

    assert projector.main(["once"]) == 0
    assert len(seen) == 1
    assert seen[0].sqlalchemy_dsn() == DSN_PROJECTOR
    printed = _assert_no_secret("pw-proj-1", capsys, caplog)
    assert "projector once: обработано 0, пропущено 0" in printed


# 6. Загрузчик texts берёт MIGRATIONS_DATABASE_URL; пароль не в выводе.
def test_texts_loader_uses_migrations_dsn(clean_env, capsys, caplog):
    clean_env.setenv("DATABASE_URL", DSN_API)
    clean_env.setenv("MIGRATIONS_DATABASE_URL", DSN_MIGRATIONS)
    caplog.set_level(logging.DEBUG)
    engine = object()
    seen: list[Settings] = []

    def fake_get_engine(settings):
        seen.append(settings)
        return engine

    def fake_write_entries(got_engine, entries):
        assert got_engine is engine
        return texts.LoadResult(inserted=0, updated=len(entries), extra=[])

    clean_env.setattr(db_session, "get_engine", fake_get_engine)
    clean_env.setattr(texts, "write_entries", fake_write_entries)

    assert texts.main(["load"]) == 0
    assert len(seen) == 1
    assert seen[0].sqlalchemy_dsn() == DSN_MIGRATIONS
    printed = _assert_no_secret("pw-mig-1", capsys, caplog)
    assert "загружено 0, обновлено" in printed
    assert "лишних в БД 0" in printed
