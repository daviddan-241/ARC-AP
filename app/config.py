"""ARC configuration — everything from environment variables, never hardcoded models."""
import os
from functools import lru_cache


class Settings:
    """Central settings. Falls back to sensible defaults; never fabricates state."""

    # --- Ollama ---
    OLLAMA_BASE_URL: str = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    # Model selection comes from env; if unset, auto-detected at runtime.
    ARC_MODEL_PRIMARY: str = os.environ.get("ARC_MODEL_PRIMARY", "")
    ARC_MODEL_REASONING: str = os.environ.get("ARC_MODEL_REASONING", "")
    ARC_MODEL_CRITIC: str = os.environ.get("ARC_MODEL_CRITIC", "")

    # --- Security ---
    ARC_API_KEY: str = os.environ.get("ARC_API_KEY", "")
    ARC_ADMIN_KEY: str = os.environ.get("ARC_ADMIN_KEY", "")  # diagnostics/capabilities detail

    # --- Persistence ---
    DATABASE_URL: str = os.environ.get("DATABASE_URL", "")  # PostgreSQL when configured
    ARC_DATA_DIR: str = os.environ.get("ARC_DATA_DIR", "/workspace")

    # --- Research ---
    RESEARCH_MAX_SOURCES: int = int(os.environ.get("RESEARCH_MAX_SOURCES", "8"))

    # --- Terminal ---
    TERMINAL_TIMEOUT: int = int(os.environ.get("TERMINAL_TIMEOUT", "60"))


@lru_cache
def get_settings() -> Settings:
    return Settings()
