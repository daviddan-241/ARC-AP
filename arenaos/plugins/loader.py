"""Plugin loader: discovers real plugins from the repo's plugins/ directory.

A plugin is a directory with:
- manifest.json  → {"name", "version", "description", "permissions": []}
- plugin.py      → must expose `def register(context) -> dict` returning metadata.

Registration runs once at app startup inside try/except: a broken plugin is
recorded with status="error" and skipped — it can never take the app down.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

from arenaos.core.logging import get_logger
from arenaos.db.database import session_scope
from arenaos.db.models import Plugin

logger = get_logger(__name__)


class PluginLoader:
    def __init__(self, plugins_dir: Path) -> None:
        self.plugins_dir = Path(plugins_dir)
        self.loaded: list[dict[str, Any]] = []

    def discover(self) -> list[Path]:
        """Return plugin dirs that actually have a manifest and a module."""
        if not self.plugins_dir.is_dir():
            return []
        found = []
        for child in sorted(self.plugins_dir.iterdir()):
            if not child.is_dir():
                continue
            if (child / "manifest.json").is_file() and (child / "plugin.py").is_file():
                found.append(child)
        return found

    def load_all(self, context: dict[str, Any]) -> list[dict[str, Any]]:
        """Discover, register, and persist every plugin. Never raises."""
        results: list[dict[str, Any]] = []
        for plugin_dir in self.discover():
            try:
                results.append(self._load_one(plugin_dir, context))
            except Exception as exc:
                logger.warning(f"plugin {plugin_dir.name} failed: {exc}")
                results.append({"name": plugin_dir.name, "status": "error", "error": str(exc)})
        self.loaded = results
        return results

    def _load_one(self, plugin_dir: Path, context: dict[str, Any]) -> dict[str, Any]:
        manifest = json.loads((plugin_dir / "manifest.json").read_text())
        name = str(manifest.get("name", plugin_dir.name))[:128]
        version = str(manifest.get("version", "0.0.0"))[:32]

        spec = importlib.util.spec_from_file_location(f"arenaos_plugin_{name}", plugin_dir / "plugin.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)  # noqa: WPS433 — plugin sandboxing is process-level
        if not hasattr(module, "register"):
            raise ValueError("plugin.py must expose register(context)")

        returned = module.register(context) or {}
        info = {"name": name, "version": version, "status": "installed",
                "description": manifest.get("description", ""),
                "permissions": manifest.get("permissions", []),
                "returned": returned}
        self._upsert(info)
        logger.info(f"plugin loaded: {name} v{version}")
        return info

    def _upsert(self, info: dict[str, Any]) -> None:
        with session_scope() as session:
            existing = session.query(Plugin).filter_by(name=info["name"]).first()
            if existing:
                existing.version = info["version"]
                existing.status = info["status"]
                existing.manifest = info
                existing.permissions = info["permissions"]
            else:
                session.add(Plugin(name=info["name"], version=info["version"],
                                  manifest=info, status=info["status"],
                                  permissions=info["permissions"]))
            session.commit()


def load_plugins(context: dict[str, Any], plugins_dir: Path | None = None) -> list[dict[str, Any]]:
    """Entry point used by create_app."""
    from arenaos.core.config import BASE_DIR
    loader = PluginLoader(plugins_dir or BASE_DIR / "plugins")
    try:
        return loader.load_all(context)
    except Exception as exc:  # absolute safety net at startup
        logger.warning("plugin loading skipped: %s", exc)
        return []
