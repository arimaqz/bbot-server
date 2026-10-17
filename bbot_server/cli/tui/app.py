"""
Main Textual application for BBOT Server TUI
"""

from typing import Iterable

from textual.app import App, ComposeResult, SystemCommand
from textual.binding import Binding
from textual.screen import Screen
from textual.theme import Theme
from textual.widgets import Header as TextualHeader, Footer, TabbedContent, TabPane

# BBOT Dark Theme - uses Textual's design system
# Custom colors (severity, status) are defined in styles.tcss as CSS variables
BBOT_DARK_THEME = Theme(
    name="bbot-dark",
    primary="#FF8400",  # BBOT signature orange
    secondary="#808080",  # Grey
    accent="#ffa62b",  # Lighter orange for accents
    foreground="#e0e0e0",  # Light text
    background="#000000",  # True black background
    surface="#121212",  # Widget backgrounds (very dark)
    panel="#1a1a1a",  # Panel backgrounds (slightly lighter)
    warning="#ffa62b",  # Orange-yellow warnings
    error="#f44336",  # Red errors
    success="#4caf50",  # Bright green (readable on dark)
    dark=True,
)

# BBOT Light Theme - light mode variant
BBOT_LIGHT_THEME = Theme(
    name="bbot-light",
    primary="#FF8400",  # BBOT signature orange
    secondary="#606060",  # Darker grey for light mode
    accent="#e67600",  # Darker orange for accents on light
    foreground="#1a1a1a",  # Dark text
    background="#ffffff",  # White background
    surface="#f5f5f5",  # Widget backgrounds (light grey)
    panel="#eeeeee",  # Panel backgrounds
    warning="#e67600",  # Darker orange warnings
    error="#d32f2f",  # Darker red errors
    success="#388e3c",  # Darker green (readable on light)
    dark=False,
)


from bbot_server.cli.tui.screens.dashboard import DashboardScreen
from bbot_server.cli.tui.screens.scans import ScansScreen
from bbot_server.cli.tui.screens.assets import AssetsScreen
from bbot_server.cli.tui.screens.findings import FindingsScreen
from bbot_server.cli.tui.screens.logs import LogsScreen
from bbot_server.cli.tui.screens.setup import SetupScreen
from bbot_server.cli.tui.screens.help_modal import HelpModal
from bbot_server.cli.tui.utils.keybindings import PRIMARY_BINDINGS, SETUP_BINDINGS, SCAN_BINDINGS


def _bindings_from_defs(*groups):
    bindings = []
    seen = set()
    for group in groups:
        for item in group:
            if item.action in seen:
                continue
            seen.add(item.action)
            bindings.append(Binding(item.key, item.action, item.description, priority=item.priority))
    return bindings


class BBOTServerTUI(App):
    """
    Main Textual TUI Application for BBOT Server

    Provides a full-featured terminal user interface for monitoring and managing
    BBOT security scans, assets, findings, and agents with real-time updates.
    """

    TITLE = "BBOT Server"
    CSS_PATH = "styles.tcss"

    BINDINGS = _bindings_from_defs(PRIMARY_BINDINGS, SETUP_BINDINGS, SCAN_BINDINGS)

    def __init__(self, bbot_server, config):
        """
        Initialize the TUI application

        Args:
            bbot_server: BBOTServer HTTP client instance
            config: BBOT server configuration
        """
        super().__init__()
        self.bbot_server = bbot_server
        self.config = config
        self.title = config.name

        # TUI settings
        self.items_per_page = config.cli.tui_page_size

        # Services will be initialized after app starts
        self.data_service = None
        self.websocket_service = None
        self.state_service = None

        # Store screen instances
        self.dashboard_screen = None
        self.scans_screen = None
        self.assets_screen = None
        self.findings_screen = None
        self.logs_screen = None
        self.setup_screen = None

        # Nested setup screens (mirrored for convenience)
        self.targets_screen = None
        self.activity_screen = None
        self.presets_screen = None
        self.modules_screen = None
        self.agents_screen = None
        self.keys_screen = None
        self.reports_screen = None
        self.settings_screen = None
        self.events_screen = None
        self.technologies_screen = None

    def _mirror_setup_screens(self) -> None:
        if not self.setup_screen:
            return
        self.targets_screen = self.setup_screen.targets_screen
        self.presets_screen = self.setup_screen.presets_screen
        self.modules_screen = self.setup_screen.modules_screen
        self.agents_screen = self.setup_screen.agents_screen
        self.keys_screen = self.setup_screen.keys_screen
        self.reports_screen = self.setup_screen.reports_screen
        self.settings_screen = self.setup_screen.settings_screen
        self.events_screen = self.setup_screen.events_screen
        self.technologies_screen = self.setup_screen.technologies_screen
        self.activity_screen = self.setup_screen.activity_screen

    def compose(self) -> ComposeResult:
        """Create child widgets for the app"""
        yield TextualHeader()

        with TabbedContent(initial="tab-dashboard", id="main-tabs"):
            with TabPane("Dashboard", id="tab-dashboard"):
                self.dashboard_screen = DashboardScreen(self)
                yield self.dashboard_screen

            with TabPane("Scans", id="tab-scans"):
                self.scans_screen = ScansScreen(self)
                yield self.scans_screen

            with TabPane("Findings", id="tab-findings"):
                self.findings_screen = FindingsScreen(self)
                yield self.findings_screen

            with TabPane("Assets", id="tab-assets"):
                self.assets_screen = AssetsScreen(self)
                yield self.assets_screen

            with TabPane("Logs", id="tab-logs"):
                self.logs_screen = LogsScreen(self)
                yield self.logs_screen

            with TabPane("Setup", id="tab-setup"):
                self.setup_screen = SetupScreen(self)
                yield self.setup_screen

        self._mirror_setup_screens()
        yield Footer()

    def on_mount(self) -> None:
        """Called when app is mounted - initialize services"""
        import logging
        from logging.handlers import RotatingFileHandler
        from pathlib import Path
        from bbot_server.cli.tui.services.data_service import DataService
        from bbot_server.cli.tui.services.websocket_service import WebSocketService
        from bbot_server.cli.tui.services.state_service import StateService

        self.register_theme(BBOT_DARK_THEME)
        self.register_theme(BBOT_LIGHT_THEME)
        self.theme = "bbot-dark"

        class SlowRequestFilter(logging.Filter):
            def filter(self, record):
                if "taking a while" in record.getMessage():
                    return False
                return True

        log_dir = Path.home() / ".bbot_server"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "tui.log"
        file_handler = RotatingFileHandler(log_file, maxBytes=10 * 1024 * 1024, backupCount=1)
        file_handler.setLevel(logging.DEBUG)
        formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        file_handler.setFormatter(formatter)

        root_logger = logging.getLogger()
        root_logger.handlers.clear()
        root_logger.addHandler(file_handler)
        root_logger.setLevel(logging.DEBUG)

        slow_filter = SlowRequestFilter()
        root_logger.addFilter(slow_filter)
        for handler in root_logger.handlers:
            handler.addFilter(slow_filter)

        http_logger = logging.getLogger("bbot_server.interfaces.http")
        http_logger.addFilter(slow_filter)
        for handler in http_logger.handlers:
            handler.addFilter(slow_filter)

        self.log.info(f"TUI logging to: {log_file}")

        self.data_service = DataService(self.bbot_server)
        self.websocket_service = WebSocketService(self.bbot_server)
        self.state_service = StateService()

        self.call_later(self._initial_refresh)

    async def _initial_refresh(self) -> None:
        """Trigger initial data load for the dashboard (initial tab)"""
        if self.dashboard_screen:
            await self.dashboard_screen.load_initial_data()

    def on_tabbed_content_tab_activated(self, event) -> None:
        """Handle tab changes - lazy load data on first visit"""
        if event.tabbed_content.id != "main-tabs":
            return

        tab_to_screen = {
            "tab-dashboard": self.dashboard_screen,
            "tab-scans": self.scans_screen,
            "tab-assets": self.assets_screen,
            "tab-findings": self.findings_screen,
            "tab-logs": self.logs_screen,
            "tab-setup": self.setup_screen,
        }

        screen = tab_to_screen.get(event.pane.id)
        if screen and hasattr(screen, "load_initial_data"):
            self.run_worker(screen.load_initial_data(), exclusive=True)

    def _activate_setup_pane(self, pane_id: str) -> None:
        tabs = self.query_one("#main-tabs", TabbedContent)
        tabs.active = "tab-setup"
        if self.setup_screen:
            setup_tabs = self.setup_screen.query_one("#setup-tabs", TabbedContent)
            setup_tabs.active = pane_id

    async def action_quit(self) -> None:
        """Override quit to ensure cleanup"""
        screens_with_timers = [
            self.dashboard_screen,
            self.scans_screen,
            self.assets_screen,
            self.findings_screen,
            self.logs_screen,
            self.events_screen,
            self.technologies_screen,
            self.targets_screen,
        ]

        for screen in screens_with_timers:
            if screen and hasattr(screen, "_refresh_timer") and screen._refresh_timer:
                screen._refresh_timer.stop()

        if self.activity_screen:
            if hasattr(self.activity_screen, "_start_timer") and self.activity_screen._start_timer:
                self.activity_screen._start_timer.stop()
            await self.activity_screen.stop_streaming()

        if self.websocket_service:
            await self.websocket_service.shutdown()

        self.exit()

    def action_show_dashboard(self) -> None:
        self.query_one("#main-tabs", TabbedContent).active = "tab-dashboard"

    def action_show_scans(self) -> None:
        self.query_one("#main-tabs", TabbedContent).active = "tab-scans"

    def action_show_assets(self) -> None:
        self.query_one("#main-tabs", TabbedContent).active = "tab-assets"

    def action_show_findings(self) -> None:
        self.query_one("#main-tabs", TabbedContent).active = "tab-findings"

    def action_show_logs(self) -> None:
        self.query_one("#main-tabs", TabbedContent).active = "tab-logs"

    def action_show_setup(self) -> None:
        self.query_one("#main-tabs", TabbedContent).active = "tab-setup"

    def action_show_events(self) -> None:
        self._activate_setup_pane("setup-events")

    def action_show_technologies(self) -> None:
        self._activate_setup_pane("setup-technologies")

    def action_show_targets(self) -> None:
        self._activate_setup_pane("setup-targets")

    def action_show_activity(self) -> None:
        self._activate_setup_pane("setup-activity")

    def action_show_presets(self) -> None:
        self._activate_setup_pane("setup-presets")

    def action_show_modules(self) -> None:
        self._activate_setup_pane("setup-modules")

    def action_show_agents(self) -> None:
        self._activate_setup_pane("setup-agents")

    def action_show_keys(self) -> None:
        self._activate_setup_pane("setup-keys")

    def action_show_reports(self) -> None:
        self._activate_setup_pane("setup-reports")

    def action_show_settings(self) -> None:
        self._activate_setup_pane("setup-settings")

    def action_new_scan(self) -> None:
        self.action_show_scans()
        if self.scans_screen:
            self.scans_screen.action_new_scan()

    def action_manage_scan(self) -> None:
        tabs = self.query_one("#main-tabs", TabbedContent)
        if tabs.active != "tab-scans" or not self.scans_screen:
            return
        self.scans_screen.action_manage_scan()

    def action_focus_filter(self) -> None:
        tabs = self.query_one("#main-tabs", TabbedContent)
        screen_by_tab = {
            "tab-scans": self.scans_screen,
            "tab-findings": self.findings_screen,
            "tab-assets": self.assets_screen,
            "tab-logs": self.logs_screen,
        }
        screen = screen_by_tab.get(tabs.active)
        if tabs.active == "tab-setup" and self.setup_screen:
            setup_tabs = self.setup_screen.query_one("#setup-tabs", TabbedContent)
            setup_by_tab = {
                "setup-events": self.events_screen,
                "setup-technologies": self.technologies_screen,
                "setup-targets": self.targets_screen,
                "setup-activity": self.activity_screen,
            }
            screen = setup_by_tab.get(setup_tabs.active)
        if screen and hasattr(screen, "action_focus_filter"):
            screen.action_focus_filter()

    def action_refresh(self) -> None:
        tabs = self.query_one("#main-tabs", TabbedContent)
        active = tabs.active
        if active == "tab-dashboard" and self.dashboard_screen:
            self.run_worker(self.dashboard_screen.action_refresh())
        elif active == "tab-scans" and self.scans_screen:
            self.run_worker(self.scans_screen.action_refresh())

    def apply_display_name(self, name: str) -> None:
        """Refresh visible branding immediately after a settings change."""
        self.title = name
        if self.dashboard_screen:
            self.dashboard_screen.query_one("#dashboard-title").update(f"[bold]{name} Dashboard[/bold]")

    def action_show_help(self) -> None:
        self.push_screen(HelpModal())

    def get_system_commands(self, screen: Screen) -> Iterable[SystemCommand]:
        """Add BBOT theme shortcuts to the system menu"""
        yield from super().get_system_commands(screen)
        yield SystemCommand(f"{self.config.name} Dark Theme", "Switch to the dark theme", self.action_theme_bbot_dark)
        yield SystemCommand(
            f"{self.config.name} Light Theme", "Switch to the light theme", self.action_theme_bbot_light
        )

    def action_theme_bbot_dark(self) -> None:
        self.theme = "bbot-dark"

    def action_theme_bbot_light(self) -> None:
        self.theme = "bbot-light"
