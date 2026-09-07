"""Test environment: hermetic tmp data dir, test operator password, TEST_MODE on."""
import os
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="arenaos-tests-"))
os.environ["ARENAOS_TEST"] = "1"
os.environ["DATA_DIR"] = str(_TMP)
os.environ["DB_URL"] = f"sqlite:///{(_TMP / 'test.db').as_posix()}"
os.environ["OPERATOR_PASSWORD"] = "test-pass-123"
os.environ["ARENA_TRANSPORT"] = "api"

import pytest  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _init_db():
    """Create all tables once for the whole test session (hermetic tmp DB)."""
    from arenaos.db.database import init_db

    init_db()


@pytest.fixture
def client():
    """FastAPI TestClient with a logged-in operator session."""
    from fastapi.testclient import TestClient
    from arenaos.api.app import create_app

    app = create_app()
    with TestClient(app) as test_client:
        response = test_client.post("/api/auth/login",
                                   json={"password": "test-pass-123"})
        assert response.status_code == 200, response.text
        yield test_client


@pytest.fixture
def sandbox():
    """Fresh ExecutionSandbox on a tmp base dir."""
    from arenaos.executor.sandbox import ExecutionSandbox

    return ExecutionSandbox(base_dir=_TMP / "ws")
