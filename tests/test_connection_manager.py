"""Agent websocket command/response handling."""

import asyncio
from unittest.mock import AsyncMock

import pytest

from bbot_server.connectionmanager import ConnectionManager
from bbot_server.modules.agents.agents_models import AgentResponse


@pytest.mark.asyncio
async def test_execute_command_returns_agent_response_error(monkeypatch):
    manager = ConnectionManager()
    agent_id = "11111111-1111-1111-1111-111111111111"
    manager.active_connections[agent_id] = AsyncMock()

    expected = AgentResponse(request_id="req-1", response={}, error="start failed")

    async def fake_wait_for(_future, timeout):
        return expected

    monkeypatch.setattr(asyncio, "wait_for", fake_wait_for)

    result = await manager.execute_command(agent_id, "start_scan", timeout=1, scan_id="scan-1")

    assert isinstance(result, AgentResponse)
    assert result.error == "start failed"


@pytest.mark.asyncio
async def test_pending_request_resolves_with_full_agent_response():
    manager = ConnectionManager()
    future = asyncio.get_running_loop().create_future()
    manager.pending_requests["req-1"] = future
    message = AgentResponse(request_id="req-1", response={"status": "error"}, error="start failed")
    manager.pending_requests.pop("req-1").set_result(message)
    result = await future
    assert result.error == "start failed"
    assert result.response == {"status": "error"}
