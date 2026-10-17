"""Forward agent and BBOT logs to the server over the agent websocket."""

import asyncio
import logging
import threading
from collections import deque

from bbot_server.modules.agents.agents_models import AgentResponse
from bbot_server.modules.agents.log_buffer import dependency_phase

log = logging.getLogger("bbot_server.agent.log_forwarder")


class AgentLogHandler(logging.Handler):
    """Thread-safe handler that keeps a small queue of log lines to ship upstream."""

    def __init__(self, maxlen: int = 500):
        super().__init__(level=15)
        self._pending = deque(maxlen=maxlen)
        self._lock = threading.Lock()

    def emit(self, record: logging.LogRecord) -> None:
        if record.name.startswith("bbot_server.agent.log_forwarder"):
            return
        try:
            message = record.getMessage()
        except Exception:
            return
        phase = dependency_phase(message)
        if record.levelno < logging.INFO and phase is None and "depsinstaller" not in record.name:
            return
        if len(message) > 2000:
            message = message[:2000] + "..."
        entry = {
            "timestamp": record.created,
            "level": record.levelname,
            "logger": record.name,
            "message": message,
            "phase": phase,
        }
        with self._lock:
            self._pending.append(entry)

    def drain(self) -> list[dict]:
        with self._lock:
            entries = list(self._pending)
            self._pending.clear()
            return entries

    def requeue(self, entries: list[dict]) -> None:
        with self._lock:
            for entry in entries:
                self._pending.append(entry)


def attach_log_handler() -> AgentLogHandler:
    for logger_name in ("bbot", "bbot_server"):
        logger = logging.getLogger(logger_name)
        for existing in logger.handlers:
            if isinstance(existing, AgentLogHandler):
                return existing
    handler = AgentLogHandler()
    for logger_name in ("bbot", "bbot_server"):
        logger = logging.getLogger(logger_name)
        if logger.level == logging.NOTSET or logger.level > 15:
            logger.setLevel(15)
        logger.addHandler(handler)
    return handler


async def forward_logs(agent, handler: AgentLogHandler) -> None:
    """Send queued log lines while the agent websocket is connected."""
    while True:
        entries = handler.drain()
        websocket = agent.websocket
        if websocket is None:
            handler.requeue(entries)
        else:
            unsent = []
            for index, entry in enumerate(entries):
                scan = getattr(agent, "scan", None)
                entry["scan_id"] = getattr(scan, "id", None)
                entry["scan_name"] = getattr(scan, "name", None)
                payload = AgentResponse(response={"log": entry})
                try:
                    await agent.send_agent_message(payload)
                except Exception:
                    log.exception("Failed to forward an agent log line")
                    unsent.extend(entries[index:])
                    break
            if unsent:
                handler.requeue(unsent)
        await asyncio.sleep(0.3)
