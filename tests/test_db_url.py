"""DB URL robustness: bad/legacy DB_URL values must never crash boot."""
from arenaos.core.config import Settings


def test_empty_db_url_falls_back_to_sqlite(tmp_path):
    s = Settings(db_url="", data_dir=tmp_path)
    assert s.resolved_db_url().startswith("sqlite:///")


def test_placeholder_db_url_falls_back(tmp_path):
    for bad in ["  ", '"your-postgres-url"', "'changeme'", "postgres-url"]:
        url = Settings(db_url=bad, data_dir=tmp_path).resolved_db_url()
        assert url.startswith("sqlite:///")


def test_legacy_render_postgres_scheme_normalized(tmp_path):
    s = Settings(db_url="postgres://user:pass@host:5432/mydb", data_dir=tmp_path)
    assert s.resolved_db_url() == "postgresql+psycopg://user:pass@host:5432/mydb"


def test_plain_postgresql_scheme_normalized(tmp_path):
    s = Settings(db_url="postgresql://user:pass@host:5432/mydb", data_dir=tmp_path)
    assert s.resolved_db_url() == "postgresql+psycopg://user:pass@host:5432/mydb"


def test_garbage_db_url_falls_back_with_warning(tmp_path, caplog):
    s = Settings(db_url="not a url at all ::::", data_dir=tmp_path)
    assert s.resolved_db_url().startswith("sqlite:///")


def test_app_boots_with_garbage_db_url(tmp_path, monkeypatch):
    """The exact Render crash: unparseable DB_URL at import time."""
    monkeypatch.setenv("ARENAOS_TEST", "1")
    monkeypatch.setenv("OPERATOR_PASSWORD", "test-pass-123")
    monkeypatch.setenv("DB_URL", ":::: not a valid url")
    monkeypatch.setattr(Settings, "data_dir", tmp_path, raising=False)
    from arenaos.api.app import create_app
    app = create_app()  # must NOT raise
    from arenaos.db.database import get_engine
    assert str(get_engine().url).startswith("sqlite:///")
