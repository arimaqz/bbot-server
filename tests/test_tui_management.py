"""TUI management workflows without a running database."""

from types import SimpleNamespace
from pathlib import Path
from uuid import UUID

import pytest
from textual.app import App, ComposeResult
from textual.widgets import DataTable, Input, TextArea

from bbot_server.cli.tui.screens.management import PresetsScreen, AgentsScreen, PresetModal
from bbot_server.cli.tui.screens.api_keys import APIKeysScreen, KeyRevealModal
from bbot_server.cli.tui.screens.settings import SettingsScreen
from bbot_server.cli.tui.app import BBOTServerTUI


class ManagementService:
    def __init__(self):
        self.presets = [
            SimpleNamespace(id="preset-1", name="baseline", description="Initial", preset={"name": "baseline"})
        ]
        self.agents = [
            SimpleNamespace(id="agent-1", name="runner", description="Worker", status="OFFLINE", last_seen=None)
        ]
        self.calls = []

    async def get_presets(self):
        return self.presets

    async def create_preset(self, preset):
        self.calls.append(("create_preset", preset))

    async def update_preset(self, preset_id, preset):
        self.calls.append(("update_preset", preset_id, preset))

    async def delete_preset(self, preset_id):
        self.calls.append(("delete_preset", preset_id))

    async def get_agents(self):
        return self.agents

    async def get_modules(self):
        return []

    async def create_agent(self, name, description):
        self.calls.append(("create_agent", name, description))

    async def delete_agent(self, agent_id):
        self.calls.append(("delete_agent", agent_id))


class ManagementApp(App):
    CSS = """.action-buttons { height: 3; dock: bottom; } DataTable { height: 1fr; } .controls-bar { height: 3; }"""

    def __init__(self, screen_type, service=None, url="http://localhost:8807/v1/"):
        super().__init__()
        self.screen_type = screen_type
        self.data_service = service
        self.config = SimpleNamespace(url=url)

    def compose(self) -> ComposeResult:
        yield self.screen_type(self)


class FakeNameConfig:
    url = "http://localhost:8807/v1/"
    name = "BBOT Server"

    def set_name(self, value):
        self.name = value


@pytest.mark.asyncio
async def test_settings_changes_the_global_display_name():
    config = FakeNameConfig()
    app = ManagementApp(SettingsScreen)
    app.config = config
    app.apply_display_name = lambda value: setattr(app, "title", value)
    async with app.run_test(size=(90, 30)) as pilot:
        screen = app.query_one(SettingsScreen)
        await screen.load_initial_data()
        screen.query_one("#setting-name", Input).value = "Acme Security"
        await pilot.click("#setting-save")
        await pilot.pause()

        assert config.name == "Acme Security"
        assert app.title == "Acme Security"


@pytest.mark.asyncio
async def test_preset_create_update_and_delete():
    service = ManagementService()
    app = ManagementApp(PresetsScreen, service)
    async with app.run_test(size=(110, 45)) as pilot:
        screen = app.query_one(PresetsScreen)
        await screen.load_initial_data()
        assert screen.query_one(DataTable).row_count == 1
        await pilot.click("#preset-new")
        await pilot.pause()
        app.screen.query_one("#preset-editor", TextArea).text = "name: new-preset\nmodules: [nmap]\n"
        await pilot.click("#preset-save")
        await pilot.pause()
        assert ("create_preset", {"name": "new-preset", "modules": ["nmap"]}) in service.calls

        await pilot.click("#preset-edit")
        await pilot.pause()
        assert isinstance(app.screen, PresetModal)
        app.screen.query_one("#preset-editor", TextArea).text = "name: renamed\n"
        await pilot.click("#preset-save")
        await pilot.pause()
        assert ("update_preset", "preset-1", {"name": "renamed"}) in service.calls

        await pilot.click("#preset-delete")
        await pilot.pause()
        await pilot.click("#confirm-btn")
        await pilot.pause()
        assert ("delete_preset", "preset-1") in service.calls


@pytest.mark.asyncio
async def test_agent_create_and_delete():
    service = ManagementService()
    app = ManagementApp(AgentsScreen, service)
    async with app.run_test(size=(110, 45)) as pilot:
        screen = app.query_one(AgentsScreen)
        await screen.load_initial_data()
        assert screen.query_one(DataTable).row_count == 1
        await pilot.click("#agent-new")
        await pilot.pause()
        app.screen.query_one("#agent-name", Input).value = "new-runner"
        app.screen.query_one("#agent-description", Input).value = "Backup"
        await pilot.click("#agent-save")
        await pilot.pause()
        assert ("create_agent", "new-runner", "Backup") in service.calls
        await pilot.click("#agent-delete")
        await pilot.pause()
        await pilot.click("#confirm-btn")
        await pilot.pause()
        assert ("delete_agent", "agent-1") in service.calls


class FakeKeyConfig:
    api_key = None

    def __init__(self):
        self.keys = {UUID("11111111-1111-1111-1111-111111111111"), UUID("22222222-2222-2222-2222-222222222222")}

    def refresh(self):
        pass

    def get_api_keys(self):
        return self.keys

    def get_api_key(self):
        return str(UUID("22222222-2222-2222-2222-222222222222"))

    def add_api_key(self):
        key = UUID("33333333-3333-3333-3333-333333333333")
        self.keys.add(key)
        return key

    def revoke_api_key(self, key):
        self.keys.remove(UUID(key))


@pytest.mark.asyncio
async def test_local_key_management_and_remote_guard(monkeypatch, tmp_path):
    import bbot_server.config as config_module

    config_file = tmp_path / "config.yml"
    config_file.write_text("api_keys: []\n")
    fake = FakeKeyConfig()
    monkeypatch.setattr(config_module, "BBOT_SERVER_CONFIG_PATH", config_file)
    monkeypatch.setattr(config_module, "BBOT_SERVER_CONFIG", fake)
    app = ManagementApp(APIKeysScreen)
    async with app.run_test(size=(110, 45)) as pilot:
        screen = app.query_one(APIKeysScreen)
        await screen.load_initial_data()
        assert screen.query_one(DataTable).row_count == 2
        assert "11111111-1111-1111-1111-111111111111" not in str(screen.query_one(DataTable).rows)
        await pilot.click("#key-add")
        await pilot.pause()
        assert isinstance(app.screen, KeyRevealModal)
        await pilot.click("#key-reveal-done")
        await pilot.pause()
        assert screen.query_one(DataTable).row_count == 3
        await pilot.click("#key-revoke")
        await pilot.pause()
        await pilot.click("#confirm-btn")
        await pilot.pause()
        assert len(fake.keys) == 2

    remote = ManagementApp(APIKeysScreen, url="https://remote.example/v1/")
    async with remote.run_test():
        screen = remote.query_one(APIKeysScreen)
        await screen.load_initial_data()
        with pytest.raises(ValueError, match="server machine"):
            screen._config()


@pytest.mark.asyncio
async def test_full_tui_navigation_has_management_and_reports_tabs():
    from textual.widgets import TabbedContent
    from bbot_server.cli.tui.screens.reports import ReportsScreen
    from bbot_server.cli.tui.screens.modules import ModulesScreen

    class TestTUI(BBOTServerTUI):
        CSS_PATH = str(Path(__file__).resolve().parents[1] / "bbot_server/cli/tui/styles.tcss")

        def on_mount(self):
            self.data_service = ManagementService()

    app = TestTUI(
        None,
        SimpleNamespace(name="BBOT Server", cli=SimpleNamespace(tui_page_size=25), url="http://localhost:8807/v1/"),
    )
    async with app.run_test(size=(120, 45)) as pilot:
        assert app.query_one(PresetsScreen)
        assert app.query_one(AgentsScreen)
        assert app.query_one(APIKeysScreen)
        assert app.query_one(ReportsScreen)
        assert app.query_one(ModulesScreen)
        assert app.query_one(SettingsScreen)
        tabs = app.query_one(TabbedContent)
        # Direct tab changes avoid lazy loading non-target services in this smoke test.
        for tab in ("tab-presets", "tab-modules", "tab-agents", "tab-keys", "tab-reports", "tab-settings"):
            tabs.active = tab
            await pilot.pause()
            assert tabs.active == tab


@pytest.mark.asyncio
async def test_default_theme_and_compact_layout_are_consistent():
    """The default 80-column terminal must not clip cards or scan actions."""
    from textual.widgets import TabbedContent
    from bbot_server.cli.tui.app import BBOT_DARK_THEME, BBOT_LIGHT_THEME

    class TestTUI(BBOTServerTUI):
        CSS_PATH = str(Path(__file__).resolve().parents[1] / "bbot_server/cli/tui/styles.tcss")

        def on_mount(self):
            self.register_theme(BBOT_DARK_THEME)
            self.register_theme(BBOT_LIGHT_THEME)
            self.theme = "bbot-dark"
            self.data_service = ManagementService()

    app = TestTUI(
        None,
        SimpleNamespace(name="BBOT Server", cli=SimpleNamespace(tui_page_size=25), url="http://localhost:8807/v1/"),
    )
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        assert app.theme == "bbot-dark"

        stats_grid = app.query_one("#stats-grid")
        cards = list(stats_grid.query(".stat-card"))
        assert len(cards) == 4
        assert cards[-1].region.right >= stats_grid.region.right - 2

        tabs = app.query_one(TabbedContent)
        tabs.active = "tab-scans"
        await pilot.pause()
        actions = app.query_one("#scan-actions")
        controls = list(actions.children)
        assert len(controls) == 5
        rows = [control.region.y for control in controls]
        assert len(set(rows)) == 2
        assert sorted(rows.count(row) for row in set(rows)) == [2, 3]
        assert all(control.region.bottom <= actions.region.bottom for control in controls)
        assert all(control.region.height == 3 for control in controls)
        assert all(control.region.width >= 14 for control in controls)
        assert all(control.region.right <= actions.region.right for control in controls)
