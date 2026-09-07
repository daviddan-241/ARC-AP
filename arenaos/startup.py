"""ArenaOS boot sequence — runs at app startup.

Guarantees, in order:
1. DB schema + operator account ready.
2. Secret vault key ready.
3. Arena web session: attempts login at STARTUP using vault credentials
   (arena_web_email / arena_web_password or arena_web_session_cookie) so the
   platform is ready to chat immediately. The honest outcome is stored in the
   settings table — 'ready', 'needs_credentials', 'login_required',
   'captcha_required' — never a faked success.
"""
from __future__ import annotations

import logging
from typing import Any

from arenaos.core.config import get_settings
from arenaos.db.database import get_sessionmaker, init_db, seed
from arenaos.db.models import Setting

logger = logging.getLogger(__name__)

STATUS_KEY = "arena_web_session_status"


def _get_credential(name: str) -> str | None:
    """Resolve a credential from the vault without ever logging its value."""
    try:
        from arenaos.secrets.manager import SecretsManager

        return SecretsManager().get(name)
    except Exception:
        return None


def _set_setting(key: str, value: Any) -> None:
    session = get_sessionmaker()()
    try:
        row = session.get(Setting, key)
        if row is None:
            row = Setting(key=key, value=value)
            session.add(row)
        else:
            row.value = value
        session.commit()
    finally:
        session.close()


def boot(transport: str = "web") -> dict[str, Any]:
    """Initialize ArenaOS. Called once at startup. Returns honest status."""
    settings = get_settings()
    settings.ensure_dirs()
    init_db()
    seed()
    logger.info("ArenaOS booted: db ready (transport=%s)", transport)

    if transport != "web":
        _set_setting(STATUS_KEY, {"status": "api_mode"})
        return {"status": "api_mode"}

    try:
        from arenaos.arena.web_provider import (
            ArenaWebCaptchaRequired,
            ArenaWebLoginRequired,
            ArenaWebSession,
            WebSessionConfig,
        )

        config = WebSessionConfig()
        session = ArenaWebSession(
            config,
            get_credential=lambda name: _get_credential(name),
        )
        import asyncio

        async def _login() -> None:
            page = await session.get_page()
            await session.ensure_logged_in(page)

        asyncio.run(_login())
        _set_setting(STATUS_KEY, {"status": "ready"})
        logger.info("Arena web session: ready")
        return {"status": "ready"}
    except ArenaWebLoginRequired as exc:
        _set_setting(STATUS_KEY, {"status": "login_required", "detail": str(exc)})
        logger.warning("Arena web session needs login: %s", exc)
        return {"status": "login_required", "detail": str(exc)}
    except ArenaWebCaptchaRequired as exc:
        _set_setting(STATUS_KEY, {"status": "captcha_required", "detail": str(exc)})
        logger.warning("Arena web session blocked by captcha at login: %s", exc)
        return {"status": "captcha_required", "detail": str(exc)}
    except Exception as exc:  # never crash the app over the model layer
        _set_setting(STATUS_KEY, {"status": "error", "detail": str(exc)})
        logger.warning("Arena web session error at boot: %s", exc)
        return {"status": "error", "detail": str(exc)}
