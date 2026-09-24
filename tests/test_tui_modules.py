from types import SimpleNamespace

import pytest
from textual.app import App, ComposeResult
from textual.widgets import DataTable, Select, Static

from bbot_server.cli.tui.screens.modules import ModulesScreen
from bbot_server.cli.tui.services.data_service import DataService
from bbot_server.cli.tui.widgets.filter_bar import FilterBar


MODULES = [
    {
        "name": "nuclei",
        "type": "scan",
        "needs_api_key": False,
        "description": "Template-based vulnerability scanner",
        "flags": ["active", "web"],
        "watched_events": ["HTTP_RESPONSE"],
        "produced_events": ["FINDING", "VULNERABILITY"],
        "options": [
            {
                "name": "modules.nuclei.tags",
                "type": "str",
                "description": "Only run templates with these tags",
                "default": "",
            }
        ],
    },
    {
        "name": "stdout",
        "type": "output",
        "needs_api_key": False,
        "description": "Write events to standard output",
        "flags": [],
        "watched_events": ["*"] ,
        "produced_events": [],
        "options": [],
    },
    {
        "name": "speculate",
        "type": "internal",
        "needs_api_key": False,
        "description": "Derive related events",
        "flags": [],
        "watched_events": ["DNS_NAME"],
        "produced_events": ["IP_ADDRESS"],
        "options": [],
    },
]


class ModuleService:
    async def get_modules(self):
        return MODULES


class ModuleApp(App):
    CSS = """
    .controls-bar { height: 3; }
    .content-area { height: 1fr; }
    .table-container { width: 2fr; }
    .detail-container { width: 1fr; }
    .detail-panel { height: 1fr; }
    """

    def __init__(self):
        super().__init__()
        self.data_service = ModuleService()
        self.config = SimpleNamespace()

    def compose(self) -> ComposeResult:
        yield ModulesScreen(self)


def test_runtime_module_metadata_is_available():
    modules = DataService._get_modules()
    by_name = {module["name"]: module for module in modules}

    assert len(modules) > 100
    assert by_name["nuclei"]["type"] == "scan"
    assert by_name["nuclei"]["description"]
    assert "watched_events" in by_name["nuclei"]
    assert any(module["type"] == "output" for module in modules)


@pytest.mark.asyncio
async def test_modules_screen_lists_filters_and_describes_runtime_modules():
    app = ModuleApp()
    async with app.run_test(size=(120, 40)) as pilot:
        screen = app.query_one(ModulesScreen)
        await screen.load_initial_data()
        await pilot.pause()

        table = screen.query_one("#module-table", DataTable)
        assert table.row_count == 3

        screen.query_one("#module-filter", FilterBar).value = "vulnerability"
        await pilot.pause()
        assert table.row_count == 1
        assert table.get_row_at(0)[0] == "nuclei"

        screen.query_one("#module-filter", FilterBar).value = ""
        screen.query_one("#module-type", Select).value = "output"
        await pilot.pause()
        assert table.row_count == 1
        assert table.get_row_at(0)[0] == "stdout"

        screen.query_one("#module-type", Select).value = "scan"
        await pilot.pause()
        detail = screen.query_one("#module-detail", Static).render().plain
        assert "nuclei" in detail
        assert "modules.nuclei.tags" in detail
