"""Skill tools: list, use, create, and install SKILL.md skills — the agent's
reusable expert playbooks (recon, research, tor crawling, vault, trading)."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from arenaos.core.permissions import Permission
from arenaos.skills import loader
from arenaos.tools.base import BaseTool, ToolContext, ToolResult


def _skills_dir(ctx: ToolContext) -> Path:
    from arenaos.core.config import get_settings
    d = Path(get_settings().data_dir) / "skills"
    d.mkdir(parents=True, exist_ok=True)
    return d


class SkillListArgs(BaseModel):
    pass


class SkillListTool(BaseTool):
    """Every skill installed in the agent, with descriptions."""

    name = "skill_list"
    description = (
        "List installed skills — reusable expert playbooks the agent can "
        "follow (deep-research, recon, onion-crawl, trade-research, "
        "vault-notes, and any you created/installed)."
    )
    required_permissions = ()
    args_model = SkillListArgs

    async def execute(self, args: SkillListArgs, ctx: ToolContext) -> ToolResult:
        skills = loader.list_skills(_skills_dir(ctx))
        if not skills:
            return ToolResult(ok=True, output="(no skills installed)")
        out = [f"{s.name} — {s.description}" for s in skills]
        return ToolResult(ok=True, output="\n".join(out))


class SkillUseArgs(BaseModel):
    name: str = Field(description="skill folder name from skill_list")


class SkillUseTool(BaseTool):
    """Load one skill's instructions and FOLLOW them with real tools."""

    name = "skill_use"
    description = (
        "Load a skill by name and follow its instructions exactly with your "
        "real tools (e.g. skill_use{name:recon}, skill_use{name:deep-research}). "
        "Run skill_list first to see what's installed."
    )
    required_permissions = ()
    args_model = SkillUseArgs

    async def execute(self, args: SkillUseArgs, ctx: ToolContext) -> ToolResult:
        try:
            skill = loader.load_skill(_skills_dir(ctx), args.name)
        except KeyError as exc:
            return ToolResult(ok=False, error=str(exc))
        return ToolResult(ok=True, output=(
            f"SKILL ACTIVE: {skill.name}\n{skill.description}\n\n"
            "Follow these instructions now, step by step:\n\n"
            f"{skill.instructions}"))


class SkillCreateArgs(BaseModel):
    name: str = Field(description="lowercase-with-dashes skill name")
    description: str = Field(description="one-line summary")
    instructions: str = Field(description="markdown playbook the agent follows")


class SkillCreateTool(BaseTool):
    """Forge a new skill from plain text — the agent writes its own playbooks."""

    name = "skill_create"
    description = (
        "Create or replace a skill from a name, description, and markdown "
        "instructions. The agent self-extends its own skill library."
    )
    required_permissions = ()
    args_model = SkillCreateArgs

    async def execute(self, args: SkillCreateArgs, ctx: ToolContext) -> ToolResult:
        try:
            md = loader.write_skill(_skills_dir(ctx), args.name,
                                    args.description, args.instructions)
        except ValueError as exc:
            return ToolResult(ok=False, error=str(exc))
        return ToolResult(ok=True, output=f"skill created: {md}")


class SkillInstallArgs(BaseModel):
    repo_url: str = Field(description="git repo containing SKILL.md folders")
    name: str | None = Field(default=None, description="optional single skill name")


class SkillInstallTool(BaseTool):
    """Install skills from a git repo — real clone, real validation."""

    name = "skill_install"
    description = (
        "Clone a git repo and import every valid SKILL.md in it (works with "
        "the Anthropic skills format and any repo of playbooks)."
    )
    required_permissions = (Permission.NETWORK_REQUEST,)
    args_model = SkillInstallArgs

    async def execute(self, args: SkillInstallArgs, ctx: ToolContext) -> ToolResult:
        try:
            installed = loader.install_from_git(
                _skills_dir(ctx), args.repo_url, args.name)
        except Exception as exc:
            return ToolResult(ok=False, error=str(exc))
        return ToolResult(ok=True,
                          output=f"installed skills: {', '.join(installed)}")
