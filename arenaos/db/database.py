"""Database engine, session management, initialization and seeding."""
from __future__ import annotations

import hashlib
import json
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from arenaos.core.config import BASE_DIR, get_settings
from arenaos.db.models import Base, Setting, User

_engine: Engine | None = None
_SessionLocal: sessionmaker | None = None


def hash_password(password: str) -> str:
    """Hash a password using SHA-256 for basic operator auth."""
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def get_engine(db_url: str | None = None) -> Engine:
    """Return or create the global SQLAlchemy Engine instance."""
    global _engine
    if db_url is not None:
        url = db_url
        connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
        return create_engine(url, connect_args=connect_args)

    if _engine is None:
        settings = get_settings()
        url = settings.resolved_db_url()
        connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
        _engine = create_engine(url, connect_args=connect_args,
                                pool_pre_ping=not url.startswith("sqlite"))
    return _engine


def get_sessionmaker(engine: Engine | None = None) -> sessionmaker:
    """Return or create the sessionmaker factory."""
    global _SessionLocal
    eng = engine or get_engine()
    if _SessionLocal is None or engine is not None:
        sm = sessionmaker(bind=eng, autoflush=False, autocommit=False, expire_on_commit=False)
        if engine is None:
            _SessionLocal = sm
        return sm
    return _SessionLocal


@contextmanager
def session_scope() -> Session:
    """Context manager for direct DB work outside FastAPI request scope."""
    sm = get_sessionmaker()
    session = sm()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_session() -> Generator[Session, None, None]:
    """FastAPI dependency for database sessions."""
    sm = get_sessionmaker()
    session = sm()
    try:
        yield session
    finally:
        session.close()


def init_db(engine: Engine | None = None) -> None:
    """Create all DB tables declared on Base, plus any ext_* tables."""
    eng = engine or get_engine()
    Base.metadata.create_all(bind=eng)

    # Register any ext_* schemas if present
    db_dir = Path(__file__).parent
    for ext_file in db_dir.glob("ext_*.py"):
        module_name = f"arenaos.db.{ext_file.stem}"
        try:
            mod = __import__(module_name, fromlist=["register"])
            if hasattr(mod, "register"):
                mod.register(eng)
        except Exception:
            pass


def seed(session: Session | None = None) -> None:
    """Seed initial data (operator user, default settings, default endpoints)."""
    settings = get_settings()
    sm = get_sessionmaker()
    close_session = False
    if session is None:
        db = sm()
        close_session = True
    else:
        db = session

    try:
        # Seed default operator user if password set
        op_password = settings.operator_password or "admin"
        op_user = db.query(User).filter(User.role == "operator").first()
        if not op_user:
            op_user = User(
                email="operator@arenaos.local",
                password_hash=hash_password(op_password),
                role="operator",
                is_active=True,
            )
            db.add(op_user)

        # Seed autonomous_mode setting if not present
        auto_setting = db.query(Setting).filter(Setting.key == "autonomous_mode").first()
        if not auto_setting:
            db.add(Setting(key="autonomous_mode", value=settings.autonomous_mode))

        db.commit()

        # Ensure default arena endpoints file exists
        endpoints_path = Path(settings.arena_endpoints_path)
        if not endpoints_path.is_absolute():
            endpoints_path = BASE_DIR / endpoints_path
        endpoints_path.parent.mkdir(parents=True, exist_ok=True)
        if not endpoints_path.exists():
            default_endpoints = [
                {
                    "name": "default-arena",
                    "base_url": settings.arena_base_url,
                    "path": "/chat/completions",
                    "protocol": "openai-chat",
                    "task_types": ["general"],
                    "priority": 100,
                    "default_temperature": 0.7,
                    "max_tokens": 4096,
                    "mood": "uncensored",
                    "notes": "Default Arena endpoint",
                }
            ]
            endpoints_path.write_text(json.dumps(default_endpoints, indent=2))
    finally:
        if close_session:
            db.close()
