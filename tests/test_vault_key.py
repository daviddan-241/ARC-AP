"""Vault robustness: ANY SECRET_VAULT_KEY value must work — the Render crash."""
import os

import pytest

from arenaos.core.security import SecretVault, redact_values


def test_raw_fernet_key_passes_through():
    from cryptography.fernet import Fernet
    key = Fernet.generate_key().decode()
    vault = SecretVault(key=key)
    ct = vault.encrypt("arena-secret")
    assert vault.decrypt(ct) == "arena-secret"


def test_render_generated_key_material_works():
    """Render's generateValue produces arbitrary strings like this one."""
    for material in ["r4nd0mR3nderValue-no-base64!!", "short", "x" * 64,
                     "a-very-long-render-generated-secret-value-1234567890"]:
        vault = SecretVault(key=material)
        ct = vault.encrypt("secret-value")
        assert vault.decrypt(ct) == "secret-value"
        # deterministic: same material -> same key (prove by cross-decryption,
        # since Fernet ciphertexts embed a random IV and never compare equal)
        other = SecretVault(key=material)
        assert other.decrypt(vault.encrypt("secret-value")) == "secret-value"


def test_bytes_key_material_works():
    vault = SecretVault(key=b"\x01" * 45)
    assert vault.decrypt(vault.encrypt("ok")) == "ok"


def test_empty_material_derives_not_crashes():
    vault = SecretVault(key="   ")
    assert vault.decrypt(vault.encrypt("ok")) == "ok"


def test_app_boots_with_render_style_vault_key(tmp_path, monkeypatch):
    """The exact Render crash: arbitrary SECRET_VAULT_KEY at import time."""
    monkeypatch.setenv("ARENAOS_TEST", "1")
    monkeypatch.setenv("OPERATOR_PASSWORD", "test-pass-123")
    monkeypatch.setenv("SECRET_VAULT_KEY", "not-a-fernet-key-at-all-!!")
    from arenaos.api.app import create_app
    app = create_app()  # must NOT raise
    # and the vault round-trips through app.state
    app.state.secrets.set("arena_web_password", "password", "hunter2")
    assert app.state.secrets.get("arena_web_password") == "hunter2"


def test_redact_values_masks_nonempty():
    out = redact_values({"A": "1", "B": "", "C": "x"})
    assert out["A"].startswith("[REDACTED") and out["C"].startswith("[REDACTED")
    assert out["B"] == ""
