# ARC — Autonomous Reasoning & Compute

A mobile-first AI operating system control plane. One unified assistant ("ARC") backed by
a model council of open-weight models (Qwen / Dolphin / DeepSeek) via any Ollama endpoint
(self-hosted native API or Ollama Cloud / OpenAI-compatible). Real execution, honest states.

## What's inside
- **FastAPI control plane** — `/health`, `/status`, `/capabilities`, `/models`,
  `/chat` + `/chat/stream` (NDJSON activity + token events), `/research`, `/browse`,
  `/terminal`, `/tasks` (background worker that keeps going until you stop it),
  `/crypto` (REAL wallet generation, ERC-20 coin kits, live on-chain balances),
  `/settings` (write-only secrets), `/sessions`, `/files`, `/knowledge/*`,
  `/projects`, `/github`, `/security-lab`, `/colab` (real Google Colab bridge — run colab/ARC_Colab_Agent.ipynb in Colab to bring a GPU runtime online as an ARC worker).
- **IRES Ω engine** — Understand → Plan → Capability check → Tool selection → Execution →
  Validation → Error recovery → Synthesis → Response → Workflow memory.
  Activity stream (Pondering / Scouting / Computing / Forging / Studying / Weaving).
- **Model council** — planner → specialist → critic → synthesizer for hard tasks;
  single-model fast path otherwise; automatic fallback; internal deliberations stay private.
- **Mobile UI** — dark mission-control, small sidebar with recent chats, settings sheet,
  question cards, task cards with live progress + stop button, built-in browser panel
  (shown only when you ask), capability matrix with REAL states.

## Environment
| Variable | Purpose |
|---|---|
| `OLLAMA_BASE_URL` | Native Ollama or OpenAI-compatible endpoint (default `http://127.0.0.1:11434`) |
| `OLLAMA_API_KEY` | Bearer token when the endpoint needs auth (e.g. Ollama Cloud) |
| `ARC_MODEL_PRIMARY` / `ARC_MODEL_REASONING` / `ARC_MODEL_CRITIC` | Model overrides; otherwise auto-detected by family (qwen / deepseek / dolphin) |
| `ARC_API_KEY` | Bearer auth for this API (mobile app → ARC) |
| `ARC_ADMIN_KEY` | Admin diagnostics (model names, latency detail) |
| `ARC_DATA_DIR` | Persistent workspace (default `/workspace`) |
| `GITHUB_TOKEN` | Enables the GitHub endpoint |
| `DATABASE_URL` | Optional PostgreSQL (filesystem store is the default) |

Runtime overrides can also be set from the in-app Settings screen (server-side only;
API keys are write-only and never returned to the frontend).

## Run locally
```bash
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
# UI at http://localhost:8000/
```

## Deploy (Render)
```bash
render blueprint launch   # uses render.yaml
# or: connect repo → Docker web service → set OLLAMA_BASE_URL + ARC_API_KEY
```
Note: Render free web services have 512MB RAM and sleep when idle — they cannot host the
models themselves. Point `OLLAMA_BASE_URL` at Ollama Cloud (https://ollama.com, has
Qwen and DeepSeek families) or your own always-on Ollama host.

## Honesty rules (built in)
- Capability matrix reports REAL states only (READY / DEGRADED / NOT_CONFIGURED / OFFLINE / ERROR).
- No fake inference, no fabricated balances, trades, or deployments.
- Private keys and API keys never leave the server.
- Background tasks run while the service is awake and report real step results.
