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

    # Deploy manager.
    render_api_token: str = ""

    # Model transport: "web" (drive arena.ai in a logged-in browser) or "api".
    arena_transport: str = "web"

    # Autonomous mode: allow all permissions except credential.use without asking.
    autonomous_mode: bool = True

    def resolved_db_url(self) -> str:
        """Return the effective database URL (SQLite default)."""
        return self.db_url or f"sqlite:///{(self.data_dir / 'arenaos.db').as_posix()}"

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
