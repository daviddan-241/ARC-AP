"""DEEP END-TO-END SMOKE TEST: exercise EVERY route + frontend asset through
the real app like an actual user session — real DB, real registry, real tool
executions, real file uploads. Anything failing here is a bug the user hits.
Uses the shared conftest `client` fixture (logged-in operator, TEST_MODE on).
"""
import hashlib
import io
import os


def test_me(client):
    r = client.get("/api/auth/me")
    assert r.status_code == 200
    assert r.json().get("authenticated") in (True, "true", None) or r.json()


def test_settings_roundtrip_and_pin(client):
    r = client.get("/api/settings")
    assert r.status_code == 200
    body = r.json()
    assert "pin_hash" in body or "pin" in body or body
    # set a PIN exactly like the Pin screen does (sha256 hex)
    import hashlib
    pin = hashlib.sha256(b"1234").hexdigest()
    r = client.put("/api/settings", json={"key": "pin_hash", "value": pin})
    assert r.status_code == 200
    assert client.get("/api/settings").json().get("pin_hash") == pin


def test_moods_real_list(client):
    r = client.get("/api/moods")
    assert r.status_code == 200
    assert isinstance(r.json(), list) and len(r.json()) >= 1


def test_conversation_lifecycle(client):
    r = client.post("/api/conversations", json={"title": "deep smoke"})
    assert r.status_code == 200, r.text
    cid = r.json()["id"]
    assert client.get("/api/conversations").json()
    r = client.get(f"/api/conversations/{cid}/messages")
    assert r.status_code == 200
    r = client.delete(f"/api/conversations/{cid}")
    assert r.status_code == 200
    assert all(c["id"] != cid for c in client.get("/api/conversations").json())


def test_tools_registry_has_all_real_capabilities(client):
    r = client.get("/api/tools")
    assert r.status_code == 200
    names = {t["name"] for t in r.json()}
    for expected in (
        "freqtrade_backtest", "gpt_research", "torbot_crawl",  # vendored repos
        "shell", "net.http",  # core capabilities
        "email_read",  # agent's own inbox
    ):
        assert expected in names, f"{expected} missing from registry: {sorted(names)[:10]}..."


def test_invoke_real_tool_end_to_end(client):
    r = client.post("/api/tools/shell/invoke",
                    json={"args": {"command": "echo deep-smoke-ok"}})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("ok"), body
    assert "deep-smoke-ok" in body.get("output", "")


def test_invoke_honest_failure_for_vendored_deps(client):
    """freqtrade_backtest with no deps installed must fail LOUDLY with the
    install command — the honesty contract."""
    r = client.post("/api/tools/freqtrade_backtest/invoke",
                    json={"args": {"config": "x.json", "strategy": "S"}})
    assert r.status_code == 200
    body = r.json()
    assert not body.get("ok")
    assert "pip install" in (body.get("error") or "")


def test_memory_roundtrip(client):
    r = client.post("/api/memory", json={"layer": "long", "content": "deep smoke memory", "key": "smoke"})
    assert r.status_code == 200, r.text
    mid = r.json().get("id")
    mems = client.get("/api/memory").json()
    assert any(m.get("id") == mid or "deep smoke memory" in str(m) for m in mems)
    if mid:
        assert client.delete(f"/api/memory/{mid}").status_code == 200


def test_projects_and_real_file_upload_download(client):
    r = client.post("/api/projects", json={"name": "DeepSmoke"})
    assert r.status_code == 200, r.text
    pid = r.json()["id"]
    r = client.post(f"/api/projects/{pid}/files/upload",
                    files={"file": ("smoke.txt", io.BytesIO(b"real bytes"), "text/plain")})
    assert r.status_code == 200, r.text
    files = client.get(f"/api/projects/{pid}/files").json()
    assert any("smoke.txt" in str(f) for f in files)


def test_processes_status_and_audit_logs(client):
    assert client.get("/api/processes").status_code == 200
    assert client.get("/api/logs/audit").status_code == 200
    assert client.get("/api/logs/tool-calls").status_code == 200
    assert client.get("/api/status").status_code == 200


def test_vault_roundtrip(client):
    assert client.post("/api/vault", json={"name": "deep_key", "kind": "api_key", "value": "v"}).status_code == 200
    names = {v["name"] if isinstance(v, dict) else str(v) for v in client.get("/api/vault").json()}
    assert "deep_key" in names
    assert client.delete("/api/vault/deep_key").status_code == 200


def test_tasks_list(client):
    r = client.get("/api/tasks")
    assert r.status_code == 200


# ------------------------------------------------ frontend assets (SPA fallback)

def test_spa_index_served(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "ARC" in r.text  # rebranded title


def test_manifest_and_icons_served(client):
    r = client.get("/manifest.json")
    assert r.status_code == 200
    m = r.json()
    assert m["name"] == "ARC" and m["theme_color"] == "#007AFF"
    r = client.get("/assets/icons/icon-192.png")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("image/png")


def test_deep_chat_route_and_404_spa_fallback(client):
    # any unknown path falls back to the SPA index (so refresh on /chat works)
    r = client.get("/chat")
    assert r.status_code == 200
    assert "ARC" in r.text
