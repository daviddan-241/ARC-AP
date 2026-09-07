"""Granular permissions and the decision policy for sensitive operations."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Awaitable, Callable, Optional


class Permission(str, Enum):
    """Every capability the agent can request, gated individually."""

    FILESYSTEM_READ = "filesystem.read"
    FILESYSTEM_WRITE = "filesystem.write"
    FILESYSTEM_DELETE = "filesystem.delete"
    SHELL_EXECUTE = "shell.execute"
    PROCESS_START = "process.start"
    PROCESS_STOP = "process.stop"
    NETWORK_REQUEST = "network.request"
    BROWSER_USE = "browser.use"
    GIT_READ = "git.read"
    GIT_WRITE = "git.write"
    GIT_PUSH = "git.push"
    DATABASE_READ = "database.read"
    DATABASE_WRITE = "database.write"
    PLUGIN_MANAGE = "plugin.manage"
    PLUGIN_INVOKE = "plugin.invoke"
    CREDENTIAL_USE = "credential.use"
    MEMORY_READ = "memory.read"
    MEMORY_WRITE = "memory.write"
    DEPLOY_MANAGE = "deploy.manage"
    SCHEDULER_MANAGE = "scheduler.manage"
    NOTIFY_SEND = "notify.send"
    SETTINGS_MANAGE = "settings.manage"


class Decision(str, Enum):
    """Outcome of a permission check."""

    ALLOW = "allow"
    DENY = "deny"
    ASK_ONCE = "ask_once"        # user approves once, not remembered
    ASK_TASK = "ask_task"        # user approves for the current task
    ASK_ALWAYS = "ask_always"    # user asked to be prompted every time


@dataclass
class Grant:
    """A stored permission grant (scope = how long it lasts)."""

    permission: Permission
    scope: str  # "once" | "task:<id>" | "session" | "always"
    resource: Optional[str] = None


GrantProvider = Callable[[Permission, Optional[str]], Awaitable[list[Grant]]]


class PermissionDenied(PermissionError):
    """Raised when a permission check resolves to deny."""


class PermissionPolicy:
    """Resolves decisions via an injected async grant provider (wired to the DB + UI).

    Autonomous mode allows everything silently EXCEPT credential.use, which always
    requires an explicit grant — credentials are never auto-spent.
    """

    def __init__(
        self,
        grant_provider: GrantProvider,
        autonomous: bool = False,
        default: Decision = Decision.ASK_ONCE,
    ) -> None:
        self._grants = grant_provider
        self.autonomous = autonomous
        self.default = default

    async def check(self, permission: Permission, resource: str | None = None) -> Decision:
        """Return the decision for a permission on an optional resource."""
        grants = await self._grants(permission, resource)
        for grant in grants:
            if grant.resource and resource and resource != grant.resource:
                continue
            if grant.scope == "deny":
                return Decision.DENY
        for grant in grants:
            if grant.resource and resource and resource != grant.resource:
                continue
            if grant.scope == "always":
                return Decision.ALLOW
            if grant.scope == "session":
                return Decision.ALLOW
            if grant.scope == "once":
                return Decision.ALLOW
        if self.autonomous and permission is not Permission.CREDENTIAL_USE:
            return Decision.ALLOW
        if self.autonomous and permission is Permission.CREDENTIAL_USE and any(
            g.scope != "deny" for g in grants
        ):
            return Decision.ALLOW
        return self.default
