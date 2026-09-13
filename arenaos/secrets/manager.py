"""Encrypted secrets manager over the Credential table. Values never logged or echoed."""
from __future__ import annotations

import os
from typing import Optional

from sqlalchemy.orm import Session

from arenaos.core.logging import get_logger
from arenaos.core.security import SecretVault
from arenaos.db.database import get_sessionmaker
from arenaos.db.models import Credential

logger = get_logger(__name__)


class SecretNotFound(KeyError):
    """Raised when a credential name is not in the vault."""


# Env vars re-imported into the vault on every boot — the durable path for
# keys that must survive Render REDEPLOYS (which wipe the container's
# filesystem, DB and all). Set them once in the Render dashboard →
# Environment and they carry forever.
ENV_BOOTSTRAP: list[tuple[str, str, str]] = [
    ("COMPOSIO_API_KEY", "composio_api_key", "token"),
    ("APPDEPLOY_API_KEY", "appdeploy_api_key", "token"),
    ("ARENA_WEB_EMAIL", "arena_web_email", "credential"),
    ("ARENA_WEB_PASSWORD", "arena_web_password", "credential"),
    ("ARENA_WEB_SESSION_COOKIE", "arena_web_session_cookie", "cookie"),
]


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

    def reseed_from_env(self) -> dict:
        """Re-import operator-provided env secrets into the vault on every boot.

        WHY: Render wipes the container filesystem on every redeploy — the
        DB-backed vault dies with it, which is exactly why an API key added
        once in Settings could disappear "after restart". Env vars set once
        in the Render dashboard survive redeploys forever, so they are the
        durable path: when an env var is present it is re-imported into the
        vault on boot (env wins, so updating the dashboard updates ARC);
        when it is absent, an in-app vault entry is left untouched and
        still survives ordinary restarts/crashes. Values are never logged.
        """
        imported, skipped = [], []
        for env_name, vault_name, kind in ENV_BOOTSTRAP:
            value = os.getenv(env_name)
            if not value:
                continue
            try:
                self.set(vault_name, kind, value)
                imported.append(env_name)
            except Exception as exc:
                logger.warning("vault reseed failed for %s: %s", env_name, exc)
                skipped.append(env_name)
        if imported:
            logger.info("vault: reseeded from env on boot: %s", ", ".join(imported))
        return {"imported": imported, "skipped": skipped}

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
