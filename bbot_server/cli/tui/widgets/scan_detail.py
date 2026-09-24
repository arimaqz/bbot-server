"""
Scan detail panel widget for BBOT Server TUI
"""

from textual.widgets import Static
from textual.containers import Container

from bbot_server.cli.tui.utils.formatters import (
    format_timestamp,
    format_duration,
)
from bbot_server.cli.tui.utils.colors import colorize_status


class ScanDetail(Container):
    """
    Widget for displaying detailed information about a selected scan

    Shows comprehensive scan information including status, timing,
    configuration, and statistics.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._current_scan = None

    def compose(self):
        """Create child widgets"""
        yield Static("", id="scan-detail-content")

    def update_scan(self, scan) -> None:
        self._current_scan = scan
        content_widget = self.query_one("#scan-detail-content", Static)

        if not scan:
            content_widget.update("[dim]Select a scan to view details[/dim]")
            return

        lines = []
        scan_id = scan.get("id", "")
        lines.append(f"[bold]{scan.get('name') or scan_id or 'Unknown'}[/bold]")
        lines.append("")

        status = scan.get("status", "UNKNOWN")
        lines.append(f"Status: {colorize_status(status, status)}")

        started_at = scan.get("started_at")
        finished_at = scan.get("finished_at")
        duration_seconds = scan.get("duration_seconds")
        if started_at:
            lines.append(f"Started: {format_timestamp(started_at)}")
        if finished_at:
            lines.append(f"Finished: {format_timestamp(finished_at)}")
        if duration_seconds:
            lines.append(f"Duration: {format_duration(duration_seconds)}")

        lines.append("")

        target = scan.get("target")
        if target:
            lines.append("[bold]Target:[/bold]")
            lines.append(f"  Name: {target.get('name', '-')}")
            target_list = target.get("target")
            if isinstance(target_list, list) and target_list:
                lines.append(f"  Targets: {', '.join(target_list[:5])}")
                if len(target_list) > 5:
                    lines.append(f"           (+{len(target_list) - 5} more)")
            seed_list = target.get("seeds")
            if isinstance(seed_list, list) and seed_list:
                lines.append(f"  Seeds: {', '.join(seed_list[:5])}")
                if len(seed_list) > 5:
                    lines.append(f"         (+{len(seed_list) - 5} more)")
            lines.append("")

        preset = scan.get("preset")
        if preset:
            lines.append("[bold]Preset:[/bold]")
            lines.append(f"  Name: {preset.get('name', '-')}")
            preset_config = preset.get("preset")
            if isinstance(preset_config, dict) and "modules" in preset_config:
                modules = preset_config["modules"]
                if isinstance(modules, list) and modules:
                    lines.append(f"  Modules: {', '.join(modules[:5])}")
                    if len(modules) > 5:
                        lines.append(f"           (+{len(modules) - 5} more)")
            lines.append("")

        agent_id = scan.get("agent_id")
        if agent_id:
            lines.append(f"Agent: {agent_id}")
        else:
            lines.append("Agent: [dim]Not assigned[/dim]")

        lines.append("")
        lines.append(f"[dim]ID: {scan_id or '-'}[/dim]")

        content_widget.update("\n".join(lines))

    def clear(self) -> None:
        """Clear the detail panel"""
        self.update_scan(None)
