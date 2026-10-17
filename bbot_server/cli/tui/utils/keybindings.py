"""
Keyboard binding definitions for BBOT Server TUI

Centralizes all keyboard shortcuts and their descriptions for
consistency across the application.
"""

from dataclasses import dataclass
from typing import List


@dataclass
class KeyBinding:
    """Represents a keyboard binding"""

    key: str
    action: str
    description: str
    priority: bool = False


PRIMARY_BINDINGS: List[KeyBinding] = [
    KeyBinding("q", "quit", "Quit", priority=True),
    KeyBinding("d", "show_dashboard", "Dashboard"),
    KeyBinding("s", "show_scans", "Scans"),
    KeyBinding("f", "show_findings", "Findings"),
    KeyBinding("a", "show_assets", "Assets"),
    KeyBinding("l", "show_logs", "Logs"),
    KeyBinding("comma", "show_setup", "Setup"),
    KeyBinding("?", "show_help", "Help"),
]

SETUP_BINDINGS: List[KeyBinding] = [
    KeyBinding("e", "show_events", "Events (Setup)"),
    KeyBinding("t", "show_technologies", "Technologies (Setup)"),
    KeyBinding("r", "show_targets", "Targets (Setup)"),
    KeyBinding("v", "show_activity", "Activity (Setup)"),
    KeyBinding("p", "show_presets", "Presets (Setup)"),
    KeyBinding("m", "show_modules", "Modules (Setup)"),
    KeyBinding("g", "show_agents", "Agents (Setup)"),
    KeyBinding("k", "show_keys", "API Keys (Setup)"),
    KeyBinding("o", "show_reports", "Reports (Setup)"),
    KeyBinding("u", "show_settings", "Settings (Setup)"),
]

SCAN_BINDINGS: List[KeyBinding] = [
    KeyBinding("n", "new_scan", "New scan"),
    KeyBinding("enter", "manage_scan", "Manage scan"),
    KeyBinding("/", "focus_filter", "Filter"),
    KeyBinding("refresh", "refresh", "Refresh"),
]

# Legacy alias
GLOBAL_BINDINGS = PRIMARY_BINDINGS


def get_bindings_for_screen(screen_name: str) -> List[KeyBinding]:
    screen_bindings = {
        "scans": SCAN_BINDINGS,
        "dashboard": [KeyBinding("refresh", "refresh", "Refresh")],
    }
    return screen_bindings.get(screen_name, [])


def format_key_hint(bindings: List[KeyBinding], max_hints: int = 8) -> str:
    hints = []
    for binding in bindings[:max_hints]:
        key = binding.key
        if key == "enter":
            key = "↵"
        elif key == "space":
            key = "␣"
        elif key == "escape":
            key = "Esc"
        hints.append(f"{key}:{binding.description}")
    return " ".join(hints)


def get_help_text(screen_name: str = None) -> str:
    lines = ["Primary navigation", "=" * 40, ""]
    for binding in PRIMARY_BINDINGS:
        lines.append(f"  {binding.key:15} {binding.description}")

    lines.extend(["", "Scans screen", "=" * 40, ""])
    for binding in SCAN_BINDINGS:
        lines.append(f"  {binding.key:15} {binding.description}")

    lines.extend(["", "Setup tab (open with comma key)", "=" * 40, ""])
    for binding in SETUP_BINDINGS:
        lines.append(f"  {binding.key:15} {binding.description}")

    lines.extend(
        [
            "",
            "Tips",
            "=" * 40,
            "  Enter on Dashboard rows opens Scans or Findings.",
            "  Scan details show dependency progress and recent logs.",
            "  Cancel/Delete live under Manage scan (Enter on Scans).",
        ]
    )
    return "\n".join(lines)
