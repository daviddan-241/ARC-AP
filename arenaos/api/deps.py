"""Auth: operator password -> signed session cookie; API keys via Bearer token."""
from __future__ import annotations

import hashlib
import time
from typing import Optional

from fastapi import Depends, HTTPException, Request
from itsdangerous import BadSignature, SignatureExpired, TimestampSigner
from sqlalchemy.orm import Session

from arenaos.core.config import get_settings
from arenaos.db.database import get_sessionmaker
from arenaos.db.models import ApiKey, User

SESSION_COOKIE = "arenaos_session"
SESSION_MAX_AGE = 7 * 24 * 3600  # 7 days
MAX_FAILED_PER_MIN = 5

_failed: dict[str, list[float]] = {}


def _signer() -> TimestampSigner:
    settings = get_settings()
    secret = settings.jwt_secret or "dev-insecure-change-me"
    return TimestampSigner(secret)


def create_session_token(user_id: int) -> str:
    """Create a signed session token for a user id."""
    signer = _signer()
    return signer.sign(str(user_id)).decode("utf-8")


def verify_session_token(token: str) -> Optional[int]:
    """Verify a session token; return the user id or None."""
    try:
        value = _signer().unsign(token, max_age=SESSION_MAX_AGE).decode("utf-8")
        return int(value)
    except (BadSignature, SignatureExpired, ValueError):
        return None


def check_rate_limit(client_key: str) -> bool:
    """Sliding 1-minute window for login attempts. True = allowed."""
    now = time.time()
    window = [t for t in _failed.get(client_key, []) if now - t < 60]
    _failed[client_key] = window
    return len(window) < MAX_FAILED_PER_MINUTE if False else len(window) < MAX_FAILED_PER_MIN


def record_failed_login(client_key: str) -> None:
    _failed.setdefault(client_key, []).append(time.time())


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def _verify_api_key(token: str, session: Session) -> bool:
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    row = session.query(ApiKey).filter(ApiKey.key_hash == digest).first()
    if row is None:
        return False
    row.last_used_at = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
    session.commit()
    return True


def get_current_user(request: Request) -> dict:
    """FastAPI dependency: session cookie or Bearer API key. 401 otherwise."""
    settings = get_settings()
    session: Session = get_sessionmaker()()
    try:
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            if _verify_api_key(token, session):
                return {"id": 0, "role": "api_key"}
            raise HTTPException(status_code=401, detail="invalid API key")
        token = request.cookies.get(SESSION_COOKIE)
        if token:
            user_id = verify_session_token(token)
            if user_id is not None:
                user = session.get(User, user_id)
                if user and user.is_active:
                    return {"id": user.id, "role": user.role, "email": user.email}
        raise HTTPException(status_code=401, detail="authentication required")
    finally:
        session.close()


require_auth = Depends(get_current_user)
