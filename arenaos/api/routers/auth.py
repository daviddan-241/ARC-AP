"""Auth router: login, logout, me, API keys."""
from __future__ import annotations

import hashlib
import secrets as pysecrets

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from arenaos.api.deps import (SESSION_COOKIE, check_rate_limit, create_session_token,
                              get_current_user, hash_password, record_failed_login)
from arenaos.core.logging import get_logger
from arenaos.db.database import get_sessionmaker
from arenaos.db.models import ApiKey, User
from arenaos.observability.audit import Audit

logger = get_logger(__name__)
router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginBody(BaseModel):
    password: str


class ApiKeyBody(BaseModel):
    name: str


@router.post("/login")
def login(body: LoginBody, request: Request, response: Response) -> dict:
    """Operator login. Sets a signed session cookie on success."""
    client_key = request.client.host if request.client else "unknown"
    if not check_rate_limit(client_key):
        raise HTTPException(status_code=429, detail="too many attempts — wait a minute")
    session: Session = get_sessionmaker()()
    try:
        user = session.query(User).filter(User.role == "operator").first()
        stored = user.password_hash if user else ""
        if not stored or hash_password(body.password) != stored:
            record_failed_login(client_key)
            from arenaos.observability.threat import AuthHammerMonitor
            if not hasattr(request.app.state, "auth_monitor"):
                request.app.state.auth_monitor = AuthHammerMonitor()
            if request.app.state.auth_monitor.record_failure(client_key):
                Audit().log(client_key, "threat:auth_brute_force", "auth")
            raise HTTPException(status_code=401, detail="invalid password")
        user_id = user.id
    finally:
        session.close()
    mon = getattr(request.app.state, "auth_monitor", None)
    if mon:
        mon.clear(client_key)
    response.set_cookie(SESSION_COOKIE, create_session_token(user_id),
                        httponly=True, samesite="lax", max_age=7 * 24 * 3600)
    Audit().log("operator", "login", "auth")
    return {"ok": True}


@router.post("/logout")
def logout(response: Response, user=Depends(get_current_user)) -> dict:
    response.delete_cookie(SESSION_COOKIE)
    return {"ok": True}


@router.get("/me")
def me(user=Depends(get_current_user)) -> dict:
    return {"id": user["id"], "role": user["role"], "email": user.get("email", "")}


@router.post("/api-keys")
def create_api_key(body: ApiKeyBody, user=Depends(get_current_user)) -> dict:
    """Create an API key. The plaintext token is returned exactly once."""
    token = "ak_" + pysecrets.token_hex(24)
    session: Session = get_sessionmaker()()
    try:
        session.add(ApiKey(user_id=user["id"], name=body.name,
                           key_hash=hashlib.sha256(token.encode()).hexdigest(),
                           scopes=["all"]))
        session.commit()
    finally:
        session.close()
    Audit().log(str(user["id"]), "api_key_created", body.name)
    return {"name": body.name, "token": token}
