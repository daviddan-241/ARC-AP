"""Real plugin system: loader discovers, registers, persists, survives failures."""
import json

from fastapi.testclient import TestClient

from arenaos.api.app import create_app
from arenaos.plugins.loader import PluginLoader


def test_loader_discovers_real_plugin():
    from arenaos.core.config import BASE_DIR
    loader = PluginLoader(BASE_DIR / "plugins")
    found = loader.discover()
    assert any(p.name == "context-stats" for p in found)


def test_plugin_registers_route_and_persists():
    with TestClient(create_app()) as client:
        # login
        assert client.post("/api/auth/login", json={"password": "test-pass-123"}).status_code == 200
        res = client.get("/plugin/context-stats")
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["plugin"] == "context-stats"
        assert "memories" in body and "credentials" in body

        # persisted in the plugins table
        from arenaos.plugins.loader import PluginLoader as _PL
        from arenaos.db.database import session_scope
        from arenaos.db.models import Plugin
        with session_scope() as session:
            row = session.query(Plugin).filter_by(name="context-stats").first()
            assert row is not None
            assert row.status == "installed"
            assert json.loads(json.dumps(row.manifest))["name"] == "context-stats"


def test_broken_plugin_is_skipped_not_fatal(tmp_path, monkeypatch):
    bad = tmp_path / "broken"
    bad.mkdir()
    (bad / "manifest.json").write_text(json.dumps({"name": "broken"}))
    (bad / "plugin.py").write_text("raise RuntimeError('boom at import')")
    loader = PluginLoader(tmp_path)
    results = loader.load_all({"app": None, "state": None})
    assert len(results) == 1
    assert results[0]["status"] == "error"
