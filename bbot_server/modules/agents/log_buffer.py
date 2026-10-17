"""In-memory agent log buffer and dependency-install classification."""

import time
from collections import deque


def dependency_phase(message: str) -> str | None:
    """Classify a log line that belongs to BBOT module dependency installation."""
    text = (message or "").lower()
    if "failed to install dependencies" in text or "setup failed for module" in text or "needs root privileges" in text:
        return "failed"
    if "loaded" in text and "scan modules" in text:
        return "ready"
    if "installing module dependencies" in text or "installing dependencies for module" in text:
        return "installing"
    if "setup succeeded for module" in text or "skipping dependency install" in text:
        return "progress"
    return None


def dependency_banner(entries, now: float | None = None) -> str | None:
    """Return a short UI status while dependencies are installing, or None when idle."""
    phased = [entry for entry in entries if entry.get("phase")]
    if not phased:
        return None
    latest = phased[-1]
    phase = latest.get("phase")
    message = latest.get("message", "")
    age = (time.time() if now is None else now) - float(latest.get("timestamp") or 0)
    agent = latest.get("agent_name") or "agent"
    scan = latest.get("scan_name")
    prefix = f"{scan} on {agent}" if scan else agent
    if phase == "failed" and age < 180:
        return f"Dependency install failed ({prefix}): {message}"
    if phase in {"installing", "progress"} and age < 180:
        return f"Installing dependencies ({prefix}): {message}"
    if phase == "ready" and age < 12:
        return f"Dependencies ready ({prefix}): {message}"
    return None


class AgentLogBuffer:
    """Ring buffer of recent agent log lines for the API process."""

    def __init__(self, maxlen: int = 2000):
        self._entries = deque(maxlen=maxlen)
        self._next_id = 1

    def append(self, entry: dict) -> dict:
        message = str(entry.get("message") or "")
        phase = entry.get("phase") or dependency_phase(message)
        item = {
            "id": self._next_id,
            "timestamp": float(entry.get("timestamp") or time.time()),
            "level": str(entry.get("level") or "INFO"),
            "logger": str(entry.get("logger") or ""),
            "message": message[:4000],
            "agent_id": str(entry.get("agent_id") or ""),
            "agent_name": str(entry.get("agent_name") or ""),
            "scan_id": entry.get("scan_id"),
            "scan_name": entry.get("scan_name"),
            "phase": phase,
            "dependency": phase is not None,
        }
        self._next_id += 1
        self._entries.append(item)
        return item

    def recent(self, limit: int = 500, after: int = 0) -> list[dict]:
        limit = max(1, min(int(limit or 500), 2000))
        after = int(after or 0)
        matched = [entry for entry in self._entries if entry["id"] > after]
        return matched[-limit:]
