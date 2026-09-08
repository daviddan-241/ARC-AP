"""Example real plugin: exposes live platform stats via a registered API route."""
from fastapi import APIRouter


def register(context) -> dict:
    """context = {"app": FastAPI instance, "state": app.state}"""
    app = context["app"]
    state = context["state"]

    router = APIRouter(prefix="/plugin", tags=["plugins"])

    @router.get("/context-stats")
    def context_stats() -> dict:
        memory_count = 0
        try:
            memory_count = len(state.memory.search("", limit=500))
        except Exception:
            pass
        credential_count = 0
        try:
            credential_count = len(state.secrets.list())
        except Exception:
            pass
        return {
            "plugin": "context-stats",
            "version": "1.0.0",
            "memories": memory_count,
            "credentials": credential_count,
            "conversation_id": getattr(state, "current_conversation_id", None),
        }

    app.include_router(router)
    return {"route": "/plugin/context-stats"}
