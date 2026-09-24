from datetime import datetime

import pytest
from textual.app import App, ComposeResult

from bbot_server.cli.tui.widgets.target_table import TargetTable


class TargetTableApp(App):
    def compose(self) -> ComposeResult:
        yield TargetTable(id="target-table")


@pytest.mark.asyncio
async def test_target_table_displays_dictionary_api_results():
    created = 1_700_000_000.0
    target = {
        "id": "target-1",
        "name": "example-target",
        "description": "Example target",
        "target_size": 1,
        "default": True,
        "created": created,
    }

    app = TargetTableApp()
    async with app.run_test() as pilot:
        table = app.query_one("#target-table", TargetTable)
        table.update_targets([target])
        await pilot.pause()

        row = table.get_row_at(0)
        assert row[0] == "example-target"
        assert row[1] == "Example target"
        assert row[2] == "1"
        assert row[3] == "Yes"
        assert str(datetime.fromtimestamp(created).year) in str(row[4])
        assert "1970" not in str(row[4])
