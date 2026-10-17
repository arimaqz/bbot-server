"""Live agent and scan log screen for the BBOT Server TUI."""

from rich.markup import escape as rich_escape
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Button, RichLog, Static

from bbot_server.cli.tui.utils.colors import ERROR, INFO, MUTED, SUCCESS, WARNING
from bbot_server.cli.tui.utils.formatters import format_timestamp_short
from bbot_server.cli.tui.widgets.filter_bar import FilterBar
from bbot_server.modules.agents.log_buffer import dependency_banner


def format_log_line(entry) -> str:
    """Render one agent log entry with Rich markup."""
    data = entry.model_dump() if hasattr(entry, "model_dump") else dict(entry)
    level = str(data.get("level") or "INFO")
    color = ERROR if level in {"ERROR", "CRITICAL"} else WARNING if level in {"WARNING", "HUGEINFO"} else INFO
    if data.get("phase") in {"installing", "progress"}:
        color = WARNING
    elif data.get("phase") == "failed":
        color = ERROR
    elif data.get("phase") == "ready":
        color = SUCCESS
    when = format_timestamp_short(data.get("timestamp"))
    agent = data.get("agent_name") or "agent"
    scan = data.get("scan_name")
    source = f"{agent}/{scan}" if scan else agent
    message = rich_escape(str(data.get("message") or ""))
    return f"[{MUTED}]{when}[/{MUTED}] [{color}]{level:<8}[/{color}] [{MUTED}]{rich_escape(source)}[/{MUTED}] {message}"


class LogsScreen(Container):
    """Tail logs forwarded from scan agents, including dependency installation."""

    def __init__(self, app):
        super().__init__()
        self.bbot_app = app
        self._refresh_timer = None
        self._has_loaded = False
        self._after = 0
        self._paused = False
        self._entries = []

    def compose(self) -> ComposeResult:
        with Container(id="logs-container"):
            with Horizontal(id="logs-controls", classes="controls-bar"):
                yield FilterBar(placeholder="Filter logs by agent, scan, level, or message...", id="logs-filter")
                yield Button("Pause", id="logs-pause", variant="warning")
                yield Button("Clear", id="logs-clear", variant="error")
                yield Button("Refresh", id="logs-refresh", variant="primary")
            yield Static("Waiting for agent logs...", id="logs-status", classes="status-bar")
            yield Static("", id="logs-dependency")
            with Vertical(id="logs-feed-container"):
                yield RichLog(id="logs-view", highlight=True, markup=True, auto_scroll=True, wrap=True)

    async def load_initial_data(self) -> None:
        if self._has_loaded:
            return
        self._has_loaded = True
        await self.refresh_logs()
        self._refresh_timer = self.set_interval(1.0, self._schedule_refresh_logs)

    def _schedule_refresh_logs(self) -> None:
        self.bbot_app.run_worker(self.refresh_logs())

    async def on_unmount(self) -> None:
        if self._refresh_timer:
            self._refresh_timer.stop()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "logs-pause":
            self._paused = not self._paused
            event.button.label = "Resume" if self._paused else "Pause"
            self._update_status()
        elif event.button.id == "logs-clear":
            self.query_one("#logs-view", RichLog).clear()
            self._entries.clear()
            self._update_status()
        elif event.button.id == "logs-refresh":
            self.bbot_app.run_worker(self.refresh_logs())

    def action_focus_filter(self) -> None:
        self.query_one("#logs-filter", FilterBar).focus()

    def on_filter_bar_filter_changed(self, event: FilterBar.FilterChanged) -> None:
        if getattr(event.control, "id", None) not in {None, "logs-filter"}:
            return
        self._render_all()

    async def refresh_logs(self) -> None:
        if not self.bbot_app.data_service or self._paused:
            return
        try:
            entries = await self.bbot_app.data_service.get_agent_logs(limit=500, after=self._after)
        except Exception as exc:
            self.query_one("#logs-status", Static).update(f"[{ERROR}]Error loading logs: {rich_escape(str(exc))}[/{ERROR}]")
            return
        if entries:
            self._after = max(entry.id for entry in entries)
            self._entries.extend(entries)
            self._entries = self._entries[-2000:]
            self._append_visible(entries)
        self._update_status()

    def _matches(self, entry, search: str) -> bool:
        if not search:
            return True
        data = entry.model_dump()
        haystack = " ".join(
            str(data.get(key) or "")
            for key in ("level", "logger", "message", "agent_name", "scan_name")
        ).lower()
        return search in haystack

    def _append_visible(self, entries) -> None:
        search = self.query_one("#logs-filter", FilterBar).value.strip().lower()
        view = self.query_one("#logs-view", RichLog)
        for entry in entries:
            if self._matches(entry, search):
                view.write(format_log_line(entry))

    def _render_all(self) -> None:
        view = self.query_one("#logs-view", RichLog)
        view.clear()
        self._append_visible(self._entries)

    def _update_status(self) -> None:
        state = "paused" if self._paused else "live"
        self.query_one("#logs-status", Static).update(f"[{SUCCESS}]● {state}[/{SUCCESS}] {len(self._entries)} lines")
        banner = dependency_banner([entry.model_dump() for entry in self._entries])
        dependency = self.query_one("#logs-dependency", Static)
        if banner:
            color = ERROR if banner.startswith("Dependency install failed") else WARNING
            dependency.update(f"[{color}]{rich_escape(banner)}[/{color}]")
        else:
            dependency.update("")
