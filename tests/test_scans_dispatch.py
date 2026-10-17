"""Scan scheduler dispatch behavior."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest

from bbot_server.modules.agents.agents_models import AgentResponse
from bbot_server.modules.scans.scans_api import ScansApplet


def _agent(agent_id: str, name: str):
    return SimpleNamespace(id=UUID(agent_id), name=name)


@pytest.mark.asyncio
async def test_dispatch_reserves_single_ready_agent_for_two_scans():
    applet = ScansApplet.__new__(ScansApplet)
    applet.log = MagicMock()
    agent = _agent("11111111-1111-1111-1111-111111111111", "runner")
    scans = [
        SimpleNamespace(id="scan-1", name="one", agent_id=None, preset=SimpleNamespace(preset={}), target=SimpleNamespace(target=[], seeds=[], blacklist=[], strict_scope=False)),
        SimpleNamespace(id="scan-2", name="two", agent_id=None, preset=SimpleNamespace(preset={}), target=SimpleNamespace(target=[], seeds=[], blacklist=[], strict_scope=False)),
    ]
    applet.get_queued_scans = AsyncMock(return_value=scans)
    applet.get_online_agents = AsyncMock(return_value=[agent])
    applet.collection = MagicMock()
    applet.collection.update_one = AsyncMock()
    applet.execute_agent_command = AsyncMock(return_value=AgentResponse(error=None))
    applet.emit_activity = AsyncMock()

    await applet._dispatch_queued_scans()

    assert applet.execute_agent_command.await_count == 1


@pytest.mark.asyncio
async def test_pinned_offline_agent_keeps_scan_queued():
    applet = ScansApplet.__new__(ScansApplet)
    applet.log = MagicMock()
    pinned_id = "22222222-2222-2222-2222-222222222222"
    scan = SimpleNamespace(
        id="scan-1",
        name="pinned",
        agent_id=UUID(pinned_id),
        preset=SimpleNamespace(preset={}),
        target=SimpleNamespace(target=[], seeds=[], blacklist=[], strict_scope=False),
    )
    ready = _agent("11111111-1111-1111-1111-111111111111", "runner")
    applet.get_queued_scans = AsyncMock(return_value=[scan])
    applet.get_online_agents = AsyncMock(return_value=[ready])
    applet.root = MagicMock()
    applet.root.get_agent = AsyncMock(return_value=_agent(pinned_id, "offline-runner"))
    applet.execute_agent_command = AsyncMock()

    await applet._dispatch_queued_scans()

    applet.execute_agent_command.assert_not_called()


@pytest.mark.asyncio
async def test_failed_dispatch_persists_failed_status():
    applet = ScansApplet.__new__(ScansApplet)
    applet.log = MagicMock()
    agent = _agent("11111111-1111-1111-1111-111111111111", "runner")
    scan = SimpleNamespace(
        id="scan-1",
        name="one",
        agent_id=None,
        preset=SimpleNamespace(preset={}),
        target=SimpleNamespace(target=[], seeds=[], blacklist=[], strict_scope=False),
    )
    applet.get_queued_scans = AsyncMock(return_value=[scan])
    applet.get_online_agents = AsyncMock(return_value=[agent])
    applet.collection = MagicMock()
    applet.collection.update_one = AsyncMock()
    applet.execute_agent_command = AsyncMock(return_value=AgentResponse(error="agent rejected scan"))
    applet.emit_activity = AsyncMock()

    await applet._dispatch_queued_scans()

    failed_update = next(
        call
        for call in applet.collection.update_one.await_args_list
        if call.args[1].get("$set", {}).get("status") == "FAILED"
    )
    assert failed_update is not None
