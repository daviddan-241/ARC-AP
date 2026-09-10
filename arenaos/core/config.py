"""Runtime configuration. Secrets arrive via env or the encrypted vault — never logged."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """ArenaOS settings, loaded from the environment and the repo `.env` file."""

    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"), env_file_encoding="utf-8", extra="ignore"
    )

    app_name: str = "ArenaOS"
    env: str = "development"

    data_dir: Path = BASE_DIR / "data"
    db_url: str = ""  # empty -> SQLite under data_dir

    # Arena model layer (the only provider).
    arena_api_key: str = ""
    arena_base_url: str = "https://api.arena.ai/v1"
    arena_endpoints_path: str = "data/arena_endpoints.json"

    # Bootstrap secrets; auto-generated on disk by the vault if empty.
    secret_vault_key: str = ""
    jwt_secret: str = ""

    # Platform auth (single operator).
    operator_password: str = ""
    # Tor routing for the agent's browser + http tools, e.g. "socks5://127.0.0.1:9050".
    tor_proxy: str = ""

    # Deploy manager.
    render_api_token: str = ""

    # Model transport: "web" (drive arena.ai in a logged-in browser) or "api".
    arena_transport: str = "web"

    # Autonomous mode: allow all permissions except credential.use without asking.
    autonomous_mode: bool = True

    def resolved_db_url(self) -> str:
        """Return the effective database URL (SQLite default).

        Robust against every realistic operator mistake: surrounding
        whitespace/quotes, Render's legacy ``postgres://`` scheme, a driver we
        don't ship (psycopg2), or an unparseable placeholder. If the value
        can't be used we fall back to SQLite with a loud warning instead of
        crashing the whole service at boot.
        """
        fallback = f"sqlite:///{(self.data_dir / 'arenaos.db').as_posix()}"
        raw = (self.db_url or "").strip().strip('"').strip("'").strip()
        if not raw or raw.lower() in {"changeme", "your-postgres-url", "postgres-url"}:
            return fallback
        # Normalize legacy schemes to the psycopg3 dialect we actually ship.
        for prefix in ("postgres://", "postgresql://", "postgresql+psycopg2://"):
            if raw.startswith(prefix):
                raw = "postgresql+psycopg://" + raw[len(prefix):]
                break
        try:
            from sqlalchemy.engine.url import make_url
            make_url(raw)
        except Exception as exc:
            import logging
            logging.getLogger("arenaos").warning(
                "DB_URL is unparseable (%s...); falling back to SQLite at %s. "
                "Set DB_URL to a full postgres://user:pass@host:5432/db URL. Error: %s",
                raw[:24], fallback, exc)
            return fallback
        return raw

    def ensure_dirs(self) -> None:
        """Create the data, workspaces and log directories."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        (self.data_dir / "workspaces").mkdir(parents=True, exist_ok=True)
        (self.data_dir / "exec_logs").mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    """Cached settings accessor."""
    settings = Settings()
    settings.ensure_dirs()
    return settings
