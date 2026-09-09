"""Secret redaction + encrypted vault primitives. Secrets never reach logs or model output."""
from __future__ import annotations

import os
import re
import stat
from pathlib import Path
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

from arenaos.core.config import get_settings

_REDACTED = "[REDACTED]"

_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_\-]{16,}"),
    re.compile(r"ghp_[A-Za-z0-9]{20,}"),
    re.compile(r"gho_[A-Za-z0-9]{20,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"xox[baprs]-[A-Za-z0-9\-]{10,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"Bearer\s+[A-Za-z0-9._\-]{16,}"),
    re.compile(r"(?i)(api[_-]?key|token|password|passwd|secret)\s*[:=]\s*\S+"),
]


def redact(text: str) -> str:
    """Strip secret-looking values from arbitrary text."""
    if not text:
        return text
    for pattern in _PATTERNS:
        text = pattern.sub(_REDACTED, text)
    return text


def redact_values(env: dict[str, str]) -> dict[str, str]:
    """Mask secret values in an env mapping (keys kept, values replaced)."""
    return {k: (_REDACTED if v else v) for k, v in env.items()}


class VaultKeyMissing(RuntimeError):
    """Raised when no vault key can be resolved."""


class SecretVault:
    """Fernet vault. Key from env SECRET_VAULT_KEY or auto-generated at data/.vault_key (0600)."""

    def __init__(self, key: Optional[str] = None) -> None:
        self._fernet = Fernet(self._resolve_key(key))

    @staticmethod
    def _to_fernet_key(material: str | bytes) -> bytes:
        """Turn ANY key material into a valid Fernet key, deterministically.

        Fernet requires exactly 32 url-safe base64-encoded bytes. Env values
        like Render's auto-generated SECRET_VAULT_KEY are arbitrary strings,
        so we derive: valid Fernet keys pass through unchanged, anything else
        is SHA-256-derived (same input -> same key, so secrets stay
        decryptable across restarts; rotated key = old secrets unreadable,
        which is the correct security behavior anyway).
        """
        raw = material if isinstance(material, bytes) else material.encode("utf-8")
        raw = raw.strip()
        try:
            import base64
            decoded = base64.urlsafe_b64decode(raw + b"=" * (-len(raw) % 4))
            if len(decoded) == 32 and not [b for b in decoded if b is None]:
                return raw
        except Exception:
            pass
        import base64
        import hashlib
        return base64.urlsafe_b64encode(hashlib.sha256(raw).digest())

    @classmethod
    def _resolve_key(cls, explicit: Optional[str]) -> bytes:
        if explicit:
            return cls._to_fernet_key(explicit)
        settings = get_settings()
        if settings.secret_vault_key:
            return cls._to_fernet_key(settings.secret_vault_key)
        key_file = settings.data_dir / ".vault_key"
        if key_file.exists():
            return cls._to_fernet_key(key_file.read_bytes().strip())
        settings.ensure_dirs()
        new_key = Fernet.generate_key()
        key_file.write_bytes(new_key)
        os.chmod(key_file, stat.S_IRUSR | stat.S_IWUSR)  # 0600
        return new_key

    def encrypt(self, value: str) -> bytes:
        """Encrypt a plaintext secret, returning the ciphertext."""
        return self._fernet.encrypt(value.encode("utf-8"))

    def decrypt(self, data: bytes) -> str:
        """Decrypt ciphertext back to plaintext. Raises InvalidToken on tamper."""
        return self._fernet.decrypt(bytes(data)).decode("utf-8")

    def rotate(self, values: dict[str, bytes]) -> dict[str, bytes]:
        """Re-encrypt a mapping of name->ciphertext under a new key."""
        new_fernet = Fernet(Fernet.generate_key())
        out = {}
        for name, ct in values.items():
            out[name] = new_fernet.encrypt(self._fernet.decrypt(bytes(ct)))
        self._fernet = new_fernet
        return out
