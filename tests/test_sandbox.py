"""Linux sandbox: real executions, timeouts, jail escape prevention."""
import asyncio

import pytest

from arenaos.executor.sandbox import ExecutionSandbox


def test_run_echo_real_exit_code(sandbox):
    ws = sandbox.create_workspace("proj-a")
    result = asyncio.run(sandbox.run("echo hello-world", cwd=str(ws)))
    assert result.ok
    assert result.exit_code == 0
    assert "hello-world" in result.stdout


def test_run_failure_exit_code_is_real(sandbox):
    ws = sandbox.create_workspace("proj-b")
    result = asyncio.run(sandbox.run("exit 3", cwd=str(ws)))
    assert not result.ok
    assert result.exit_code == 3


def test_timeout_kills_process_group(sandbox):
    ws = sandbox.create_workspace("proj-c")
    result = asyncio.run(sandbox.run("sleep 30", cwd=str(ws), timeout=2))
    assert not result.ok
    assert result.exit_code == -9
    assert "timeout" in result.stderr


def test_safe_path_blocks_escape(sandbox):
    ws = sandbox.create_workspace("proj-d")
    with pytest.raises(PermissionError):
        sandbox.safe_path(str(ws), "../../etc/passwd")


def test_safe_path_allows_inside(sandbox):
    ws = sandbox.create_workspace("proj-e")
    resolved = sandbox.safe_path(str(ws), "src/main.py")
    assert str(resolved).startswith(str(ws.resolve()))


def test_cwd_outside_workspaces_rejected(sandbox):
    with pytest.raises(PermissionError):
        asyncio.run(sandbox.run("echo hi", cwd="/etc"))


def test_background_start_stop_logs(sandbox):
    async def scenario():
        ws = sandbox.create_workspace("proj-f")
        handle = await sandbox.start_background(
            "for i in $(seq 1 50); do echo tick-$i; sleep 0.05; done", cwd=str(ws))
        await asyncio.sleep(0.4)
        status = sandbox.status(handle.id)
        assert status["running"] is True
        logs = sandbox.logs(handle.id)
        assert "tick-" in logs
        assert await sandbox.stop(handle.id)
        await asyncio.sleep(0.2)
        assert sandbox.status(handle.id)["running"] is False

    asyncio.run(scenario())
