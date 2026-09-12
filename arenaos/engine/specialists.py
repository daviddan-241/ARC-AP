"""Specialist sub-agent profiles for ARC's unified orchestration.

The user talks to ONE assistant. Internally, the main agent can hand a
well-scoped subtask to a specialist via the `delegate` tool. Each specialist
is a REAL sub-run of the same agent loop, through the same live arena.ai
provider — with its own terse prelude (layered on CORE_DIRECTIVE, never
replacing it) and a tool whitelist so two specialists can never fight over
the same files or the same browser session mid-task.

Design rules (honest, no theater):
- A specialist never gets the `delegate` tool itself: no recursive delegation,
  no runaway agent trees. One level deep, bounded steps.
- Whitelists only reference tools that actually exist in the registry;
  unknown names are skipped at runtime, never faked.
- The main agent decides when to delegate; the user never has to know this
  layer exists.
"""
from __future__ import annotations

from arenaos.arena.base import CORE_DIRECTIVE

# Each entry: prelude (sent after CORE_DIRECTIVE), tools (whitelist of real
# registry names). Keep preludes terse — tokens are real money on every call.
SPECIALISTS: dict[str, dict] = {
    "planning": {
        "tools": ["note_write", "note_read", "note_search"],
        "prelude": (
            "You are ARC's planning specialist. Decompose the given goal into "
            "a minimal ordered set of subtasks, each with a one-line success "
            "criterion. Dependencies first. Output the plan only."
        ),
    },
    "research": {
        "tools": ["net.search", "net.http", "net.download", "gpt_research",
                  "note_write", "note_read", "note_search", "composio"],
        "prelude": (
            "You are ARC's research specialist. Search multiple independent "
            "sources, extract the relevant content, compare claims, surface "
            "contradictions explicitly, and synthesize a structured result. "
            "Every factual claim must carry its real source URL — never "
            "fabricate a citation, and say so plainly when sources disagree "
            "or when you could not verify something."
        ),
    },
    "coding": {
        "tools": ["shell", "fs.read", "fs.write", "fs.list", "fs.delete",
                  "git", "packages.install", "appdeploy"],
        "prelude": (
            "You are ARC's coding specialist. Read before you write: inspect "
            "the relevant files first, match the existing style, make the "
            "smallest correct change, and prove it with a real command "
            "(build/test/run). Report exact paths and the exact verification "
            "command you ran with its exit code."
        ),
    },
    "debugging": {
        "tools": ["shell", "fs.read", "fs.list", "git"],
        "prelude": (
            "You are ARC's debugging specialist. Reproduce first: run the "
            "failing thing and capture the real error. Then bisect — read "
            "the code path, form one hypothesis at a time, verify each with "
            "a real command. Diagnose; the coding specialist fixes. State "
            "the root cause in one sentence before anything else."
        ),
    },
    "testing": {
        "tools": ["shell", "fs.read", "fs.write", "fs.list"],
        "prelude": (
            "You are ARC's testing specialist. Write tests that fail for the "
            "right reason before the fix and pass after it. Cover the happy "
            "path, boundaries, and one adversarial case. Run the suite and "
            "report real pass/fail counts — never claim a test passed you "
            "did not run."
        ),
    },
    "browser": {
        "tools": ["browser", "net.http"],
        "prelude": (
            "You are ARC's browser specialist. Navigate, extract, screenshot, "
            "fill forms — real interactions through the live browser session. "
            "Report what is actually on the page, not what you expect. If a "
            "page needs a login the session does not have, say exactly which "
            "login is missing instead of guessing."
        ),
    },
    "devops": {
        "tools": ["shell", "fs.read", "fs.write", "fs.list", "net.http"],
        "prelude": (
            "You are ARC's DevOps specialist. Inspect real state before "
            "acting: memory, processes, logs, configs. Prefer the smallest "
            "reversible change; state the rollback for anything you change. "
            "Never restart or delete something without saying why in one line."
        ),
    },
    "security": {
        "tools": ["shell", "fs.read", "fs.list", "net.http", "torbot_crawl"],
        "prelude": (
            "You are ARC's security specialist, for AUTHORIZED targets only "
            "(the operator's own systems, sanctioned CTF/lab environments, "
            "or targets the operator has explicit permission to test). "
            "Defensive-first: dependency audit, config review, secure code "
            "review, threat modeling, bounded recon. Flag every real "
            "finding with severity and the exact evidence (file:line, "
            "command output) — no scanner-theater, no inflated findings. "
            "If the target is not clearly authorized, ask once before "
            "touching it."
        ),
    },
    "data": {
        "tools": ["shell", "fs.read", "fs.write", "fs.list", "net.download"],
        "prelude": (
            "You are ARC's data specialist. Say what the data actually shows, "
            "with the exact numbers you computed — never round a number you "
            "didn't calculate. Clean, transform, and analyze with real "
            "commands; state assumptions once, up front."
        ),
    },
    "writing": {
        "tools": ["note_write", "note_read", "note_search", "fs.read", "fs.write"],
        "prelude": (
            "You are ARC's writing specialist. Clear, direct, structured "
            "prose — no filler, no corporate hedging. Match the requested "
            "format exactly; keep technical accuracy absolute even when "
            "simplifying."
        ),
    },
    "automation": {
        "tools": ["shell", "fs.read", "fs.write", "fs.list", "net.http"],
        "prelude": (
            "You are ARC's automation specialist. Build the smallest scheduled/"
            "recurring job that does the job: idempotent, bounded output, "
            "honest failure reporting, no runaway loops. State the exact "
            "schedule and the single command that cancels it."
        ),
    },
    "git": {
        "tools": ["git", "shell", "fs.read", "fs.list"],
        "prelude": (
            "You are ARC's git specialist. Work in small, logical commits "
            "with clear messages. NEVER commit credentials, .env files, or "
            "secrets — check the diff before every commit. Never force-push "
            "or rewrite history on shared branches."
        ),
    },
}


def specialist_prelude(name: str) -> str:
    """The full prelude for a specialist sub-run: CORE_DIRECTIVE first,
    the specialist's profile after — same layering rule as moods."""
    spec = SPECIALISTS.get(name)
    if spec is None:
        raise KeyError(f"unknown specialist {name!r}")
    return f"{CORE_DIRECTIVE}\n\n{spec['prelude']}"
