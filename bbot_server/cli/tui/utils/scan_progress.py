"""Scan lifecycle stages and dependency progress for the TUI."""

from __future__ import annotations

import re
from typing import Any

from rich.markup import escape as rich_escape

INSTALLING_MODULE_RE = re.compile(r'installing dependencies for module "([^"]+)"', re.I)
SETUP_OK_RE = re.compile(r'setup succeeded for module "([^"]+)"', re.I)
SETUP_FAIL_RE = re.compile(r'setup failed for module "([^"]+)"', re.I)
SKIP_MODULE_RE = re.compile(r'skipping dependency install for module "([^"]+)"', re.I)


def preset_modules(scan: dict[str, Any] | None) -> list[str]:
    if not scan:
        return []
    preset = scan.get("preset") or {}
    config = preset.get("preset") if isinstance(preset.get("preset"), dict) else {}
    modules = config.get("modules") if isinstance(config, dict) else []
    if isinstance(modules, list):
        return [str(module) for module in modules]
    return []


def scan_lifecycle_stage(scan: dict[str, Any] | None) -> str:
    if not scan:
        return "idle"
    status = str(scan.get("status") or "UNKNOWN").upper()
    if status == "QUEUED":
        return "queued"
    if status in {"STARTING", "SENT_TO_AGENT"}:
        return "starting"
    if status == "RUNNING":
        return "running"
    if status in {"FINISHED", "ABORTED"}:
        return "finished"
    if status == "FAILED":
        return "failed"
    if status == "ABORTING":
        return "aborting"
    return status.lower()


def module_states_from_logs(entries: list[dict[str, Any]], modules: list[str]) -> dict[str, str]:
    states = {module: "pending" for module in modules}
    for entry in entries:
        message = str(entry.get("message") or "")
        for pattern, state in (
            (SETUP_FAIL_RE, "failed"),
            (SETUP_OK_RE, "done"),
            (SKIP_MODULE_RE, "done"),
            (INSTALLING_MODULE_RE, "installing"),
        ):
            match = pattern.search(message)
            if match:
                module = match.group(1)
                if module in states:
                    if state == "installing" and states[module] == "done":
                        continue
                    states[module] = state
    return states


def build_scan_progress(scan: dict[str, Any] | None, log_entries: list[Any]) -> dict[str, Any]:
    entries = [
        entry.model_dump() if hasattr(entry, "model_dump") else dict(entry) for entry in (log_entries or [])
    ]
    modules = preset_modules(scan)
    module_states = module_states_from_logs(entries, modules)
    installing = [name for name, state in module_states.items() if state == "installing"]
    failed = [name for name, state in module_states.items() if state == "failed"]
    done_count = sum(1 for state in module_states.values() if state == "done")
    deps_active = any(entry.get("phase") in {"installing", "progress"} for entry in entries)
    deps_failed = any(entry.get("phase") == "failed" for entry in entries)
    stage = scan_lifecycle_stage(scan)
    if stage in {"queued", "starting"} and (deps_active or installing or (modules and done_count < len(modules))):
        stage = "installing_deps"
    if deps_failed and stage not in {"finished", "failed"}:
        stage = "deps_failed"
    tail = entries[-8:]
    return {
        "stage": stage,
        "modules": modules,
        "module_states": module_states,
        "installing": installing,
        "failed_modules": failed,
        "done_count": done_count,
        "log_tail": tail,
    }


def format_stage_label(stage: str) -> str:
    labels = {
        "idle": "Idle",
        "queued": "Queued",
        "starting": "Starting",
        "installing_deps": "Installing dependencies",
        "deps_failed": "Dependency install failed",
        "running": "Running",
        "aborting": "Aborting",
        "finished": "Finished",
        "failed": "Failed",
    }
    return labels.get(stage, stage.replace("_", " ").title())


def format_module_checklist(module_states: dict[str, str]) -> list[str]:
    lines = []
    for module, state in module_states.items():
        if state == "done":
            icon = "[green]✓[/green]"
        elif state == "installing":
            icon = "[yellow]…[/yellow]"
        elif state == "failed":
            icon = "[red]✗[/red]"
        else:
            icon = "[dim]○[/dim]"
        lines.append(f"  {icon} {rich_escape(module)}")
    return lines


STAGE_LABELS = {
    "idle": "Idle",
    "queued": "Queued",
    "starting": "Starting",
    "installing_deps": "Installing dependencies",
    "installing": "Installing dependencies",
    "deps_failed": "Dependency install failed",
    "running": "Running",
    "aborting": "Aborting",
    "finished": "Finished",
    "failed": "Failed",
}


def format_stage_line(stage: str) -> str:
    return STAGE_LABELS.get(stage, format_stage_label(stage))


def _normalize_entries(log_entries: list[Any]) -> list[dict[str, Any]]:
    return [
        entry.model_dump() if hasattr(entry, "model_dump") else dict(entry) for entry in (log_entries or [])
    ]


def module_install_checklist(
    log_entries: list[Any], scan_id: str | None, modules: list[str]
) -> list[tuple[str, str]]:
    entries = _normalize_entries(log_entries)
    states = module_states_from_logs(entries, modules)
    return [(module, states.get(module, "pending")) for module in modules]


def entries_for_scan(
    log_entries: list[Any], scan_id: str | None, scan_name: str | None
) -> list[dict[str, Any]]:
    entries = _normalize_entries(log_entries)
    if not scan_id and not scan_name:
        return entries
    matched = []
    for entry in entries:
        entry_scan_id = entry.get("scan_id")
        entry_scan_name = entry.get("scan_name")
        if scan_id and entry_scan_id and str(entry_scan_id) == str(scan_id):
            matched.append(entry)
        elif scan_name and entry_scan_name and entry_scan_name == scan_name:
            matched.append(entry)
    return matched if matched else entries[-20:]
