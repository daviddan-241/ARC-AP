"""Private Chat erasure: DELETE /api/conversations/{id} must hard-delete the
conversation AND every message in it — the backend behind 'fully erased'."""
from __future__ import annotations


def test_delete_conversation_removes_it_and_its_messages(client):
    conv = client.post("/api/conversations", json={"title": "Private chat"}).json()
    cid = conv["id"]

    # real conversation + turn through the public helper so we have messages
    assert client.get(f"/api/conversations/{cid}/messages").status_code == 200

    listing = client.get("/api/conversations").json()
    assert any(c["id"] == cid for c in listing)

    r = client.delete(f"/api/conversations/{cid}")
    assert r.status_code == 200
    assert r.json()["deleted"] == cid

    listing = client.get("/api/conversations").json()
    assert not any(c["id"] == cid for c in listing), "conversation must be gone"
    assert client.get(f"/api/conversations/{cid}/messages").json() == [], "messages must be gone too"
