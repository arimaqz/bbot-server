"""Preset and agent management in the terminal UI."""

import yaml
from rich.markup import escape as rich_escape
from textual import work
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, DataTable, Input, Static, TextArea

from bbot_server.cli.tui.screens.confirm_modal import ConfirmModal


class PresetModal(ModalScreen[dict | None]):
    CSS = """
    PresetModal { align: center middle; }
    #preset-dialog { width: 82; height: 85%; padding: 1 2; border: thick $primary; background: $surface; }
    #preset-editor { height: 1fr; }
    #preset-buttons { height: 3; align: center middle; }
    #preset-buttons Button { margin: 0 1; }
    """

    def __init__(self, preset=None):
        super().__init__()
        self.preset = preset

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="preset-dialog"):
            yield Static("[bold]Edit Preset[/bold]" if self.preset else "[bold]New Preset[/bold]")
            yield Static("Preset YAML (name and scan configuration)")
            yield TextArea(
                yaml.safe_dump(self.preset.preset, sort_keys=False) if self.preset else "name: \nmodules: []\n",
                id="preset-editor",
            )
            with Horizontal(id="preset-buttons"):
                yield Button("Save", id="preset-save", variant="success")
                yield Button("Cancel", id="preset-dismiss")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "preset-dismiss":
            self.dismiss(None)
        elif event.button.id == "preset-save":
            try:
                value = yaml.safe_load(self.query_one("#preset-editor", TextArea).text)
            except yaml.YAMLError as exc:
                self.notify(f"Invalid YAML: {exc}", severity="error")
                return
            if not isinstance(value, dict) or not isinstance(value.get("name"), str) or not value["name"].strip():
                self.notify("Preset must contain a nonempty name", severity="warning")
                return
            self.dismiss(value)


class AgentModal(ModalScreen[dict | None]):
    CSS = """
    AgentModal { align: center middle; }
    #agent-dialog { width: 68; height: auto; padding: 1 2; border: thick $primary; background: $surface; }
    #agent-dialog Input { margin: 1 0; }
    #agent-buttons { height: 3; align: center middle; }
    """

    def compose(self) -> ComposeResult:
        with Container(id="agent-dialog"):
            yield Static("[bold]Register Agent[/bold]")
            yield Input(placeholder="Agent name", id="agent-name")
            yield Input(placeholder="Description (optional)", id="agent-description")
            with Horizontal(id="agent-buttons"):
                yield Button("Create", id="agent-save", variant="success")
                yield Button("Cancel", id="agent-dismiss")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "agent-dismiss":
            self.dismiss(None)
        elif event.button.id == "agent-save":
            name = self.query_one("#agent-name", Input).value.strip()
            if not name:
                self.notify("Agent name is required", severity="warning")
                return
            self.dismiss({"name": name, "description": self.query_one("#agent-description", Input).value.strip()})


class ManagementScreen(Container):
    """Common table and action handling for preset and agent records."""

    kind = ""
    columns = ()

    def __init__(self, app):
        super().__init__()
        self.bbot_app = app
        self.records = {}
        self._has_loaded = False

    def compose(self) -> ComposeResult:
        with Container():
            with Horizontal(classes="controls-bar"):
                yield Button("Refresh", id=f"{self.kind}-refresh", variant="primary")
            yield Static("Loading...", id=f"{self.kind}-status", classes="status-bar")
            yield DataTable(id=f"{self.kind}-table")
            with Horizontal(classes="action-buttons"):
                yield Button(f"New {self.kind.title()}", id=f"{self.kind}-new", variant="success")
                if self.kind == "preset":
                    yield Button("Edit", id="preset-edit", variant="warning")
                yield Button("Delete", id=f"{self.kind}-delete", variant="error")

    def on_mount(self):
        table = self.query_one(DataTable)
        table.cursor_type = "row"
        table.add_columns(*self.columns)

    async def load_initial_data(self):
        if not self._has_loaded:
            self._has_loaded = True
            await self.refresh_records()

    async def refresh_records(self):
        status = self.query_one(f"#{self.kind}-status", Static)
        try:
            items = await (
                self.bbot_app.data_service.get_presets()
                if self.kind == "preset"
                else self.bbot_app.data_service.get_agents()
            )
            table = self.query_one(DataTable)
            table.clear()
            self.records = {str(item.id): item for item in items}
            for item in items:
                table.add_row(*self.row(item), key=str(item.id))
            status.update(f"{len(items)} {self.kind}s")
        except Exception as exc:
            status.update(f"Error loading {self.kind}s: {rich_escape(str(exc))}")

    def selected(self):
        table = self.query_one(DataTable)
        if not table.row_count:
            return None
        return self.records.get(str(table.coordinate_to_cell_key(table.cursor_coordinate)[0].value))

    async def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == f"{self.kind}-refresh":
            await self.refresh_records()
        elif event.button.id == f"{self.kind}-new":
            self._edit_record()
        elif event.button.id == "preset-edit":
            record = self.selected()
            if record:
                self._edit_record(record)
        elif event.button.id == f"{self.kind}-delete":
            record = self.selected()
            if record:
                self._delete_record(record)

    @work(exclusive=True)
    async def _edit_record(self, record=None):
        modal = PresetModal(record) if self.kind == "preset" else AgentModal()
        value = await self.app.push_screen_wait(modal)
        if value is None:
            return
        try:
            service = self.bbot_app.data_service
            if self.kind == "preset":
                if record:
                    await service.update_preset(str(record.id), value)
                else:
                    await service.create_preset(value)
            else:
                await service.create_agent(**value)
            await self.refresh_records()
            self.notify(f"{self.kind.title()} saved")
        except Exception as exc:
            self.notify(f"Could not save {self.kind}: {exc}", severity="error", timeout=6)

    @work(exclusive=True)
    async def _delete_record(self, record):
        if not await self.app.push_screen_wait(
            ConfirmModal(f"Delete {self.kind.title()}", f"Delete '{rich_escape(record.name)}'?", "Delete", danger=True)
        ):
            return
        try:
            service = self.bbot_app.data_service
            if self.kind == "preset":
                await service.delete_preset(str(record.id))
            else:
                await service.delete_agent(str(record.id))
            await self.refresh_records()
            self.notify(f"{self.kind.title()} deleted")
        except Exception as exc:
            self.notify(f"Could not delete {self.kind}: {exc}", severity="error", timeout=6)


class PresetsScreen(ManagementScreen):
    kind = "preset"
    columns = ("Name", "Description", "ID")

    def row(self, item):
        return item.name, item.description, str(item.id)


class AgentsScreen(ManagementScreen):
    kind = "agent"
    columns = ("Name", "Status", "Last seen", "Description", "ID")

    def row(self, item):
        from datetime import datetime, timezone

        last_seen = (
            datetime.fromtimestamp(item.last_seen, timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
            if item.last_seen
            else "Never"
        )
        return item.name, item.status, last_seen, item.description, str(item.id)
