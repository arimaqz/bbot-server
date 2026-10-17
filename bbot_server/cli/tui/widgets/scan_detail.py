"""
Scan detail panel widget for BBOT Server TUI
"""

from typing import Any

from rich.markup import escape as rich_escape
from textual.widgets import Static
from textual.containers import Container

from bbot_server.cli.tui.utils.formatters import (
    format_timestamp,
    format_duration,
)
from bbot_server.cli.tui.utils.colors import colorize_status
from bbot_server.cli.tui.utils.scan_progress import (
    build_scan_progress,
    format_stage_label,
    format_module_checklist,
)


class ScanDetail(Container):
    """
    Widget for displaying detailed information about a selected scan

    Shows comprehensive scan information including status, timing,
    configuration, dependency progress, and recent agent logs.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._current_scan = None
        self._log_entries: list[Any] = []

    def compose(self):
        """Create child widgets"""
        yield Static("", id="scan-detail-content")

    def update_scan(self, scan) -> None:
        self._current_scan = scan
        self._refresh_content()

    def update_progress(self, scan, log_entries) -> None:
        """Refresh dependency stage and log tail (scan may match current selection)."""
        if scan is not None:
            self._current_scan = scan
        self._log_entries = list(log_entries or [])
        self._refresh_content()

    def _refresh_content(self) -> None:
        try:
            content_widget = self.query_one("#scan-detail-content", Static)
        except Exception:
            return

        scan = self._current_scan

        if not scan:
            content_widget.update("[dim]Select a scan to view details[/dim]")
            return

        lines = []
        scan_id = scan.get("id", "")
        title = rich_escape(str(scan.get("name") or scan_id or "Unknown"))
        lines.append(f"[bold]{title}[/bold]")
        lines.append("")

        progress = build_scan_progress(scan, self._log_entries)
        stage = progress["stage"]
        lines.append(f"Stage: [bold]{format_stage_label(stage)}[/bold]")

        status = scan.get("status", "UNKNOWN")
        lines.append(f"Status: {colorize_status(status, status)}")

        module_states = progress.get("module_states") or {}
        if module_states:
            lines.append("")
            lines.append("[bold]Modules[/bold]")
            lines.extend(format_module_checklist(module_states))

        started_at = scan.get("started_at")
        finished_at = scan.get("finished_at")
        duration_seconds = scan.get("duration_seconds")
        if started_at:
            lines.append("")
            lines.append(f"Started: {format_timestamp(started_at)}")
        if finished_at:
            lines.append(f"Finished: {format_timestamp(finished_at)}")
        if duration_seconds:
            lines.append(f"Duration: {format_duration(duration_seconds)}")

        lines.append("")

        target = scan.get("target")
        if target:
            lines.append("[bold]Target:[/bold]")
            lines.append(f"  Name: {rich_escape(str(target.get('name', '-')))}")
            target_list = target.get("target")
            if isinstance(target_list, list) and target_list:
                shown = ", ".join(rich_escape(str(item)) for item in target_list[:5])
                lines.append(f"  Targets: {shown}")
                if len(target_list) > 5:
                    lines.append(f"           (+{len(target_list) - 5} more)")
            seed_list = target.get("seeds")
            if isinstance(seed_list, list) and seed_list:
                shown = ", ".join(rich_escape(str(item)) for item in seed_list[:5])
                lines.append(f"  Seeds: {shown}")
                if len(seed_list) > 5:
                    lines.append(f"         (+{len(seed_list) - 5} more)")
            lines.append("")

        preset = scan.get("preset")
        if preset:
            lines.append("[bold]Preset:[/bold]")
            lines.append(f"  Name: {rich_escape(str(preset.get('name', '-')))}")
            preset_config = preset.get("preset")
            if isinstance(preset_config, dict) and "modules" in preset_config:
                modules = preset_config["modules"]
                if isinstance(modules, list) and modules:
                    shown = ", ".join(rich_escape(str(module)) for module in modules[:5])
                    lines.append(f"  Modules: {shown}")
                    if len(modules) > 5:
                        lines.append(f"           (+{len(modules) - 5} more)")
            lines.append("")

        tail = progress.get("log_tail") or []
        if tail:
            lines.append("[bold]Recent logs[/bold]")
            for entry in tail:
                phase = entry.get("phase") or ""
                message = rich_escape(str(entry.get("message") or "").strip())
                if len(message) > 72:
                    message = message[:69] + "..."
                phase_text = rich_escape(str(phase)) if phase else ""
                prefix = f"[dim]{phase_text}[/dim] " if phase_text else ""
                lines.append(f"  {prefix}{message}")

        agent_id = scan.get("agent_id")
        lines.append("")
        if agent_id:
            lines.append(f"Agent: {rich_escape(str(agent_id))}")
        else:
            lines.append("Agent: [dim]Not assigned[/dim]")

        lines.append("")
        lines.append(f"[dim]ID: {rich_escape(str(scan_id or '-'))}[/dim]")

        try:
            content_widget.update("\n".join(lines))
        except Exception:
            content_widget.update("[dim]Could not render scan details[/dim]")

    def clear(self) -> None:
        """Clear the detail panel"""
        self._log_entries = []
        self.update_scan(None)
