"""IRES Ω — Intelligent Research, Reasoning, Execution & Systems.

The ARC core engine. Runs a real pipeline and emits ACTIVITY events the UI streams:
  pondering → understanding & planning        (label: "Pondering")
  scouting  → web research                     (label: "Scouting")
  computing → terminal / linux execution       (label: "Computing")
  forging   → building / coding                (label: "Forging")
  studying  → reading files & docs             (label: "Studying")
  weaving   → synthesizing the final answer   (label: "Weaving")

The user sees only ARC. Internal council conversations stay private.
Workflow:
UNDERSTAND → PLAN → CAPABILITY CHECK → TOOL SELECTION → EXECUTION
→ VALIDATION → ERROR RECOVERY → SYNTHESIS → RESPONSE → WORKFLOW MEMORY
"""
import json, time, re
from typing import AsyncGenerator, Optional
from . import ollama
from .research import research_web
from .terminal import run_command
from .store import append_workflow_memory, load_memories

MAX_CONTEXT_EVENTS = 12  # how many memory entries feed the model


def act(kind: str, detail: str) -> dict:
    return {"type": kind, "label": KIND_LABELS[kind], "detail": detail, "ts": time.time()}


KIND_LABELS = {
    "pondering": "Pondering", "scouting": "Scouting", "computing": "Computing",
    "forging": "Forging", "studying": "Studying", "weaving": "Weaving",
}


import re as _re

def _word_match(msg: str, kws: list) -> bool:
    m = msg.lower()
    return any(_re.search(r"\b" + _re.escape(k) + r"\b", m) for k in kws)


def _looks_like_research(msg: str) -> bool:
    kws = ["research", "find out", "sources", "latest", "news", "search", "compare",
           "what is", "who is", "when did", "explain", "citation", "look up", "investigate"]
    return _word_match(msg, kws)


def _looks_like_terminal(msg: str) -> bool:
    kws = ["install", "run", "execute", "terminal", "command", "shell", "bash",
           "pip", "apt", "check if", "system", "process", "port"]
    return _word_match(msg, kws)


def _looks_like_colab(msg: str) -> bool:
    kws = ["colab", "on my notebook runtime", "gpu", "train", "train a model", "tensorflow", "pytorch"]
    return _word_match(msg, kws)


async def _classify(msg: str) -> str:
    """Understand: classify the task honestly with the primary model (fast path: heuristics)."""
    if "colab status" in msg.lower():
        return "colab_status"
    if _looks_like_colab(msg) and len(msg) > 40:
        return "colab"
    if _looks_like_research(msg):
        return "research"
    if _looks_like_terminal(msg):
        return "terminal"
    if msg.strip().startswith("$") or msg.strip().startswith("#!"):
        return "terminal"
    return "chat"


async def _council_answer(msg: str, history: list, emit) -> str:
    """Difficult-task council: Planner → Specialist → Critic → Synthesizer.
    All internal — the user only ever sees ARC's final answer."""
    council = await ollama.detect_council()
    m_reason, m_spec, m_critic = council["reasoning"], council["primary"], council["critic"]
    if not m_reason:
        raise RuntimeError("no models available on the Ollama endpoint")

    async def safe(model, prompt, system=None, n=512):
        try:
            return await ollama.generate_text(model, prompt, system=system, num_predict=n)
        except Exception as e:  # ERROR RECOVERY: model fallback
            emit(act("pondering", f"{model} failed ({type(e).__name__}), falling back"))
            fb = m_spec if model != m_spec else council.get("critic")
            if fb and fb != model:
                return await ollama.generate_text(fb, prompt, system=system, num_predict=n)
            raise

    emit(act("pondering", "Convening the council — planning the approach"))
    plan = await safe(m_reason,
        f"Task: {msg}\nBreak this into 2-4 concrete steps. Be terse, one line per step.",
        system="You are ARC's planner. Output a numbered plan only.", n=200)

    emit(act("forging", "Specialist drafting a solution"))
    draft = await safe(m_spec,
        f"Plan:\n{plan}\n\nTask: {msg}\nWrite the best direct answer.",
        system="You are ARC's specialist. Answer accurately and completely.", n=900)

    emit(act("pondering", "Critic reviewing for errors and gaps"))
    critique = await safe(m_critic,
        f"Draft answer:\n{draft}\n\nList up to 3 concrete corrections or improvements. If solid, say 'SOLID'.",
        system="You are ARC's critic. Be blunt and brief.", n=200)

    emit(act("weaving", "Weaving the reviewed answer"))
    final = await safe(m_spec,
        f"Draft:\n{draft}\n\nCritic notes:\n{critique}\n\nProduce the final polished answer for the user.",
        system="You are ARC. Final answer only, no meta commentary.", n=900)
    return final


async def chat_stream(msg: str, history: Optional[list] = None) -> AsyncGenerator[str, str]:
    """Main ARC conversation pipeline. Yields JSON activity events + final message.

    Event shapes:
      {"event":"activity", ...}     — live activity chips (tappable in UI)
      {"event":"token", "text": ...} — streamed answer tokens
      {"event":"done", ...}          — final result + workflow memory id
      {"event":"error", "detail":...}
    """
    history = history or []
    used_council = False
    try:
        # UNDERSTAND
        kind = await _classify(msg)
        emit_buffer = []

        def emit(e: dict):
            emit_buffer.append(e)

        # CAPABILITY CHECK (real)
        council = await ollama.detect_council()
        if not council["primary"]:
            yield json.dumps({"event": "error", "detail": "Ollama reachable but no models installed."}) + "\n"
            return

        # WORKFLOW MEMORY — context from past workflows
        memories = load_memories()
        ctx = "\n".join(f"- {m}" for m in memories[-MAX_CONTEXT_EVENTS:]) if memories else ""

        if kind == "research":
            yield json.dumps(act("scouting", "Scouting the web for sources")) + "\n"
            report, sources = await research_web(msg)
            yield json.dumps(act("studying", f"Studying {len(sources)} sources")) + "\n"
            answer = report
        elif kind in ("colab", "colab_status"):
            import colab as _colab
            from . import colab as _colab_mod
            if kind == "colab_status":
                st = _colab_mod.status()
                w = st["worker"]
                answer = ("Colab runtime ONLINE: " + w["name"] + (" (" + w.get("gpu", "") + ")") if w
                          else "No Colab runtime online — open ARC_Colab_Agent.ipynb in Colab and run the cell."
                          ) + f"\nJobs: {st['jobs']}"
            else:
                yield json.dumps(act("forging", "Queuing work for the Colab runtime")) + "\n"
                # ask the primary model to draft the python code for colab
                council2 = await ollama.detect_council()
                prompt = ("Write a single self-contained Python 3 code block that accomplishes this task "
                          "on a Google Colab VM (tensorflow/pytorch available, internet available). "
                          "Output ONLY the code block, no explanations:\n\n" + msg)
                code = ""
                async for line in ollama.generate_stream(council2["primary"], prompt, system="You are a precise code generator."):
                    try:
                        d = json.loads(line)
                    except Exception:
                        continue
                    code += d.get("response", "")
                    if d.get("done"):
                        break
                code = code.strip()
                if code.startswith("```"):
                    code = code.strip("`").strip()
                    if code.startswith("python"):
                        code = code.split("\n", 1)[1] if "\n" in code else code
                j = _colab_mod.create_job(title=msg[:60], code=code)
                st = _colab_mod.status()
                w = st["worker"]
                if w:
                    answer = ("Queued on Colab (job " + j["id"] + "). Your Colab runtime is online - it will pick this up within ~10 seconds and post the result back.")
                else:
                    answer = ("Queued on Colab (job " + j["id"] + "). No Colab runtime online right now - open ARC_Colab_Agent.ipynb in Google Colab and run the agent cell; it will claim this job automatically.")
                answer += "\n\nCode queued:\n```\n" + code[:800] + "\n```"
        elif kind == "terminal":
            yield json.dumps(act("computing", "Preparing isolated execution")) + "\n"
            cmd = msg.strip().lstrip("$").strip()
            result = run_command(cmd)
            answer = f"$ {cmd}\n\n{result['stdout']}\n" + (f"\n[stderr] {result['stderr']}" if result["stderr"] else "") + \
                     (f"\n[exit {result['exit_code']}]" if result["exit_code"] != 0 else "")
        else:
            # ROUTING: council for hard tasks, single model for simple ones
            hard = len(msg) > 220 or any(w in msg.lower() for w in ["plan", "design", "architect", "debug", "build", "step by step", "strategy"])
            if hard:
                answer = None
                used_council = True
                async for e in _council_events(msg, ctx, emit):
                    yield json.dumps(e) + "\n"
                # council ran inside; collect final via generator return
            else:
                yield json.dumps(act("pondering", "Pondering your message")) + "\n"
                system = "You are ARC, a capable, concise AI assistant." + (f"\nRelevant context from memory:\n{ctx}" if ctx else "")
                stream = ollama.generate_stream(council["primary"], _with_history(msg, history), system=system)
                answer = ""
                async for line in stream:
                    try:
                        d = json.loads(line)
                    except Exception:
                        continue
                    tok = d.get("response", "")
                    if tok:
                        answer += tok
                        yield json.dumps({"event": "token", "text": tok}) + "\n"
                    if d.get("done"):
                        break

        if answer is None:
            # council path didn't stream tokens; run it now
            council = await ollama.detect_council()

            async def emit_yield(e):
                yield json.dumps(e) + "\n"

            # run council with inline event emission
            buf = []
            def emit2(e):
                buf.append(e)
            final = await _council_answer(msg, history, emit2)
            for e in buf:
                yield json.dumps(e) + "\n"
            answer = final
            yield json.dumps({"event": "token", "text": answer}) + "\n"

        # WORKFLOW MEMORY
        mem_id = append_workflow_memory(msg, kind, answer[:400])
        yield json.dumps({"event": "done", "activity_kind": kind, "memory_id": mem_id,
                          "source": "ollama",
                          "model_count": 3 if used_council else 1}) + "\n"
    except Exception as e:
        yield json.dumps({"event": "error", "detail": f"{type(e).__name__}: {e}"}) + "\n"


def _with_history(msg: str, history: list) -> str:
    if not history:
        return msg
    lines = []
    for h in history[-6:]:
        role = "User" if h.get("role") == "user" else "ARC"
        lines.append(f"{role}: {h.get('content','')}")
    lines.append(f"User: {msg}")
    return "\n".join(lines)


async def _council_events(msg: str, ctx: str, emit):
    """Placeholder stream for council path — emits no events itself."""
    return
    yield
