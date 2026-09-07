"""Security redaction + encrypted vault tests."""
from arenaos.core.security import SecretVault, redact


def test_redact_removes_known_token_patterns():
    text = "use sk-abc123def456ghi789 and ghp_abcdefghijklmnopqrstuvwxyz to connect"
    result = redact(text)
    assert "sk-abc123" not in result
    assert "ghp_" not in result
    assert "[REDACTED]" in result


def test_redact_masks_key_value_pairs():
    result = redact("api_key: supersecretvalue123")
    assert "supersecretvalue123" not in result
    result = redact("password=hunter2pass")
    assert "hunter2pass" not in result


def test_redact_leaves_normal_text():
    text = "build the app and run tests"
    assert redact(text) == text


def test_vault_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("SECRET_VAULT_KEY", "")
    from arenaos.core.config import get_settings
    get_settings.cache_clear()
    import arenaos.core.config as config
    monkeypatch.setattr(config.Settings, "model_config", config.Settings.model_config)
    vault = SecretVault()
    ciphertext = vault.encrypt("arena-password-xyz")
    assert b"arena-password-xyz" not in ciphertext
    assert vault.decrypt(ciphertext) == "arena-password-xyz"


def test_vault_tamper_raises():
    from cryptography.fernet import Fernet
    vault = SecretVault(key=Fernet.generate_key().decode())
    ciphertext = bytearray(vault.encrypt("secret"))
    ciphertext[5] ^= 0xFF
    try:
        vault.decrypt(bytes(ciphertext))
        assert False, "tampered ciphertext must raise"
    except Exception:
        pass
