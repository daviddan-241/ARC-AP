"""API integration tests: auth, projects, files jail, memory, vault, chat degradation."""
import pytest


def test_healthz_open(client):
    res = client.get("/healthz")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert body["degraded"] is False  # test env runs transport=api — never degraded


def test_login_rejects_wrong_password():
    from fastapi.testclient import TestClient
    from arenaos.api.app import create_app

    app = create_app()
    with TestClient(app) as fresh:
        res = fresh.post("/api/auth/login", json={"password": "wrong"})
        assert res.status_code == 401


def test_projects_create_and_files_jail(client):
    res = client.post("/api/projects", json={"name": "demo proj"})
    assert res.status_code == 200
    project = res.json()
    pid = project["id"]

    res = client.put(f"/api/projects/{pid}/files/content",
                     json={"path": "hello.txt", "content": "jail test"})
    assert res.status_code == 200
    res = client.get(f"/api/projects/{pid}/files/content?path=hello.txt")
    assert res.json()["content"] == "jail test"

    escape = client.get(f"/api/projects/{pid}/files/content?path=../../etc/passwd")
    assert escape.status_code == 400
    assert "escapes" in escape.json()["detail"]


def test_memory_crud_via_api(client):
    res = client.post("/api/memory", json={"layer": "long", "content": "prefers dark ui", "key": "ui"})
    assert res.status_code == 200
    mid = res.json()["id"]
    res = client.get("/api/memory?q=dark")
    assert any(m["id"] == mid for m in res.json())
    res = client.delete(f"/api/memory/{mid}")
    assert res.status_code == 200


def test_vault_never_returns_values(client):
    res = client.post("/api/vault", json={"name": "arena_web_email", "kind": "password",
                                          "value": "super-secret-value-99"})
    assert res.status_code == 200
    listing = client.get("/api/vault").json()
    entry = next(v for v in listing if v["name"] == "arena_web_email")
    assert "super-secret-value-99" not in str(entry)
    assert set(entry.keys()) == {"name", "kind", "meta"}


def test_chat_stream_reports_degraded_transport_honestly(client):
    conv = client.post("/api/conversations", json={"title": "t"}).json()
    res = client.post(f"/api/conversations/{conv['id']}/message",
                      json={"content": "hello"})
    assert res.status_code == 200
    assert "kind" in res.text and "error" in res.text


def test_tasks_endpoint_works_without_provider(client):
    res = client.get("/api/tasks")
    assert res.status_code == 200
    assert res.json() == []


def test_unauthenticated_denied():
    from fastapi.testclient import TestClient
    from arenaos.api.app import create_app

    with TestClient(create_app()) as anon:
        res = anon.get("/api/status")
        assert res.status_code == 401
        res = anon.get("/api/vault")
        assert res.status_code == 401
