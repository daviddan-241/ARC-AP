"""Load, create, and install SKILL.md skills. Real files, real parsing."""
from __future__ import annotations

import logging
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class Skill:
    name: str
    description: str
    instructions: str
    path: str


_FRONT_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?", re.DOTALL)


def parse_skill_md(text: str) -> tuple[str, str, str]:
    """Parse one SKILL.md -> (name, description, instructions)."""
    m = _FRONT_RE.match(text)
    if not m:
        raise ValueError("SKILL.md is missing YAML frontmatter (--- ... ---)")
    front = m.group(1)
    name = ""
    description = ""
    for line in front.splitlines():
        k, _, v = line.partition(":")
        k, v = k.strip().lower(), v.strip().strip("\"'")
        if k == "name":
            name = v
        elif k == "description":
            description = v
    if not name:
        raise ValueError("SKILL.md frontmatter is missing a name")
    instructions = text[m.end():].strip()
    if not instructions:
        raise ValueError("SKILL.md has no instructions body")
    return name, description, instructions


def list_skills(skills_dir: Path) -> list[Skill]:
    """Every valid skill folder under skills_dir (invalid ones are skipped with a log)."""
    skills = []
    if not skills_dir.exists():
        return skills
    for md in sorted(skills_dir.glob("*/SKILL.md")):
        try:
            name, desc, body = parse_skill_md(md.read_text(encoding="utf-8"))
            skills.append(Skill(name, desc, body, str(md.parent)))
        except Exception as exc:
            logger.warning("invalid skill %s: %s", md, exc)
    return skills


def load_skill(skills_dir: Path, name: str) -> Skill:
    """Load one skill by folder name; unknown names raise KeyError."""
    md = skills_dir / name / "SKILL.md"
    if not md.exists():
        raise KeyError(f"no skill named {name!r}")
    n, desc, body = parse_skill_md(md.read_text(encoding="utf-8"))
    return Skill(n, desc, body, str(md.parent))


def write_skill(skills_dir: Path, name: str, description: str, instructions: str) -> Path:
    """Create or replace a skill from text. Returns the SKILL.md path."""
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", name):
        raise ValueError("skill names: lowercase letters, digits, dashes")
    folder = skills_dir / name
    folder.mkdir(parents=True, exist_ok=True)
    md = folder / "SKILL.md"
    md.write_text(
        "---\n"
        f"name: {name}\n"
        f"description: {description}\n"
        "---\n\n"
        f"{instructions.strip()}\n",
        encoding="utf-8",
    )
    return md


def install_from_git(skills_dir: Path, repo_url: str, name: str | None = None) -> list[str]:
    """Clone a git repo and import every SKILL.md found in it. Real clones,
    real validation; returns the names of installed skills."""
    with tempfile.TemporaryDirectory() as tmp:
        r = subprocess.run(["git", "clone", "--depth", "1", repo_url, tmp],
                           capture_output=True, text=True, timeout=120)
        if r.returncode != 0:
            raise RuntimeError(f"git clone failed: {r.stderr.strip()[:300]}")
        installed = []
        for md in sorted(Path(tmp).rglob("SKILL.md")):
            try:
                skill_name, desc, body = parse_skill_md(
                    md.read_text(encoding="utf-8"))
            except Exception as exc:
                logger.warning("skipping %s in repo: %s", md, exc)
                continue
            dest = skills_dir / (name or skill_name)
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(md.parent, dest)
            installed.append(name or skill_name)
        if not installed:
            raise ValueError("repo contains no valid SKILL.md skills")
        return installed
