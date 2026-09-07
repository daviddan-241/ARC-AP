"""Encrypted secrets manager over the Credential table. Values never logged or echoed."""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from arenaos.core.logging import get_logger
from arenaos.core.security import SecretVault
from arenaos.db.database import get_sessionmaker
from arenaos.db.models import Credential

logger = get_logger(__name__)


class SecretNotFound(KeyError):
    """Raised when a credential name is not in the vault."""


class SecretsManager:
    """CRUD for encrypted credentials + env injection for tool subprocesses."""

    def __init__(self, session_factory=None, vault: Optional[SecretVault] = None) -> None:
        self._sessions = session_factory or get_sessionmaker()
        self._vault = vault or SecretVault()

    def set(self, name: str, kind: str, value: str, meta: Optional[dict] = None) -> None:
        """Create or update a credential. `value` is encrypted immediately."""
        session: Session = self._sessions()
        try:
            row = session.query(Credential).filter(Credential.name == name).first()
            ciphertext = self._vault.encrypt(value)
            if row is None:
                row = Credential(name=name, kind=kind, encrypted_value=ciphertext,
                                 meta=meta or {})
                session.add(row)
            else:
                row.kind = kind
                row.encrypted_value = ciphertext
                row.meta = meta or row.meta
            session.commit()
            logger.info("vault: set credential %s (kind=%s)", name, kind)
        finally:
            session.close()

    def get(self, name: str) -> str:
        """Return the plaintext value, or raise SecretNotFound. Never logs the value."""
        session: Session = self._sessions()
        try:
            row = session.query(Credential).filter(Credential.name == name).first()
            if row is None:
                raise SecretNotFound(f"credential {name!r} not configured — add it in Settings > Vault")
            return self._vault.decrypt(row.encrypted_value)
        finally:
            session.close()

    def get_meta(self, name: str) -> dict:
        """Return credential metadata only (no value)."""
        session: Session = self._sessions()
        try:
            row = session.query(Credential).filter(Credential.name == name).first()
            return {"name": row.name, "kind": row.kind, "meta": row.meta} if row else {}
        finally:
            session.close()

    def delete(self, name: str) -> bool:
        """Delete a credential. Returns True if it existed."""
        session: Session = self._sessions()
        try:
            row = session.query(Credential).filter(Credential.name == name).first()
            if row is None:
                return False
            session.delete(row)
            session.commit()
            return True
        finally:
            session.close()

    def list(self) -> list[dict]:
        """List names/kinds/metadata only — never values."""
        session: Session = self._sessions()
        try:
            rows = session.query(Credential).order_by(Credential.name).all()
            return [{"name": r.name, "kind": r.kind, "meta": r.meta} for r in rows]
        finally:
            session.close()

    def inject_env(self, names: Optional[list[str]] = None) -> dict[str, str]:
        """Build an env dict of secret values for a tool subprocess. Never logged."""
        if names is None:
            names = [item["name"] for item in self.list()]
        env: dict[str, str] = {}
        for name in names:
            try:
                env[name.upper().replace("-", "_")] = self.get(name)
            except SecretNotFound:
                continue
        return env
