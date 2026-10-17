"""Grouped configuration and advanced data views."""

from textual.app import ComposeResult
from textual.containers import Container
from textual.widgets import TabbedContent, TabPane

from bbot_server.cli.tui.screens.targets import TargetsScreen
from bbot_server.cli.tui.screens.management import PresetsScreen, AgentsScreen
from bbot_server.cli.tui.screens.modules import ModulesScreen
from bbot_server.cli.tui.screens.api_keys import APIKeysScreen
from bbot_server.cli.tui.screens.reports import ReportsScreen
from bbot_server.cli.tui.screens.settings import SettingsScreen
from bbot_server.cli.tui.screens.events import EventsScreen
from bbot_server.cli.tui.screens.technologies import TechnologiesScreen
from bbot_server.cli.tui.screens.activity import ActivityScreen


class SetupScreen(Container):
    """Setup hub: targets, presets, agents, and secondary data tabs."""

    def __init__(self, app):
        super().__init__()
        self.bbot_app = app
        self._has_loaded = False
        self.targets_screen = None
        self.presets_screen = None
        self.modules_screen = None
        self.agents_screen = None
        self.keys_screen = None
        self.reports_screen = None
        self.settings_screen = None
        self.events_screen = None
        self.technologies_screen = None
        self.activity_screen = None

    def compose(self) -> ComposeResult:
        with Container(id="setup-container"):
            with TabbedContent(initial="setup-targets", id="setup-tabs"):
                with TabPane("Targets", id="setup-targets"):
                    self.targets_screen = TargetsScreen(self.bbot_app)
                    yield self.targets_screen
                with TabPane("Presets", id="setup-presets"):
                    self.presets_screen = PresetsScreen(self.bbot_app)
                    yield self.presets_screen
                with TabPane("Modules", id="setup-modules"):
                    self.modules_screen = ModulesScreen(self.bbot_app)
                    yield self.modules_screen
                with TabPane("Agents", id="setup-agents"):
                    self.agents_screen = AgentsScreen(self.bbot_app)
                    yield self.agents_screen
                with TabPane("Reports", id="setup-reports"):
                    self.reports_screen = ReportsScreen(self.bbot_app)
                    yield self.reports_screen
                with TabPane("API Keys", id="setup-keys"):
                    self.keys_screen = APIKeysScreen(self.bbot_app)
                    yield self.keys_screen
                with TabPane("Settings", id="setup-settings"):
                    self.settings_screen = SettingsScreen(self.bbot_app)
                    yield self.settings_screen
                with TabPane("Events", id="setup-events"):
                    self.events_screen = EventsScreen(self.bbot_app)
                    yield self.events_screen
                with TabPane("Technologies", id="setup-technologies"):
                    self.technologies_screen = TechnologiesScreen(self.bbot_app)
                    yield self.technologies_screen
                with TabPane("Activity", id="setup-activity"):
                    self.activity_screen = ActivityScreen(self.bbot_app)
                    yield self.activity_screen

    async def load_initial_data(self) -> None:
        if self._has_loaded:
            return
        self._has_loaded = True
        if self.targets_screen and hasattr(self.targets_screen, "load_initial_data"):
            await self.targets_screen.load_initial_data()

    def on_tabbed_content_tab_activated(self, event: TabbedContent.TabActivated) -> None:
        if event.tabbed_content.id != "setup-tabs":
            return
        tab_to_screen = {
            "setup-targets": self.targets_screen,
            "setup-presets": self.presets_screen,
            "setup-modules": self.modules_screen,
            "setup-agents": self.agents_screen,
            "setup-reports": self.reports_screen,
            "setup-keys": self.keys_screen,
            "setup-settings": self.settings_screen,
            "setup-events": self.events_screen,
            "setup-technologies": self.technologies_screen,
            "setup-activity": self.activity_screen,
        }
        screen = tab_to_screen.get(event.pane.id)
        if screen and hasattr(screen, "load_initial_data"):
            self.bbot_app.run_worker(screen.load_initial_data(), exclusive=True)
