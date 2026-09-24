"""Installed BBOT module browser for the terminal UI."""

from rich.markup import escape as rich_escape
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, DataTable, Select, Static

from bbot_server.cli.tui.widgets.filter_bar import FilterBar


class ModulesScreen(Container):
    """List and inspect modules discovered from the installed BBOT runtime."""

    def __init__(self, app):
        super().__init__()
        self.bbot_app = app
        self.modules = []
        self.visible_modules = []
        self._has_loaded = False

    def compose(self) -> ComposeResult:
        with Container(id="modules-container"):
            with Horizontal(id="module-controls", classes="controls-bar"):
                yield FilterBar(placeholder="Search modules, descriptions, flags, or events...", id="module-filter")
                yield Select(
                    [("All types", "all"), ("Scan", "scan"), ("Output", "output"), ("Internal", "internal")],
                    value="all",
                    allow_blank=False,
                    id="module-type",
                )
                yield Button("Refresh", id="module-refresh", variant="primary")

            yield Static("Loading modules...", id="modules-status", classes="status-bar")

            with Horizontal(id="modules-content", classes="content-area"):
                with Vertical(id="modules-table-container", classes="table-container"):
                    yield DataTable(id="module-table")

                with Vertical(id="module-detail-container", classes="detail-container"):
                    yield Static("[bold]Module Details[/bold]", id="detail-header")
                    with VerticalScroll(classes="detail-panel"):
                        yield Static("[dim]Select a module to view details[/dim]", id="module-detail")

    def on_mount(self) -> None:
        table = self.query_one("#module-table", DataTable)
        table.cursor_type = "row"
        table.zebra_stripes = True
        table.add_columns("Module", "Type", "API Key", "Description")

    async def load_initial_data(self) -> None:
        if self._has_loaded:
            return
        self._has_loaded = True
        await self.refresh_modules()

    async def refresh_modules(self) -> None:
        status = self.query_one("#modules-status", Static)
        status.update("Loading modules...")
        try:
            self.modules = await self.bbot_app.data_service.get_modules()
            self._render_modules()
        except Exception as exc:
            status.update(f"[red]Error loading modules: {rich_escape(str(exc))}[/red]")

    def _render_modules(self) -> None:
        search = self.query_one("#module-filter", FilterBar).value.strip().lower()
        selected_type = self.query_one("#module-type", Select).value

        def matches(module):
            if selected_type != "all" and module["type"] != selected_type:
                return False
            searchable = " ".join(
                [
                    module["name"],
                    module["type"],
                    module.get("description", ""),
                    *module.get("flags", []),
                    *module.get("watched_events", []),
                    *module.get("produced_events", []),
                ]
            ).lower()
            return not search or search in searchable

        self.visible_modules = [module for module in self.modules if matches(module)]
        table = self.query_one("#module-table", DataTable)
        table.clear()
        for module in self.visible_modules:
            table.add_row(
                module["name"],
                module["type"],
                "Yes" if module.get("needs_api_key") else "No",
                module.get("description", ""),
                key=module["name"],
            )

        self.query_one("#modules-status", Static).update(
            f"Showing {len(self.visible_modules)} of {len(self.modules)} modules"
        )
        if self.visible_modules:
            table.move_cursor(row=0, column=0)
            self._update_detail(self.visible_modules[0])
        else:
            self._update_detail(None)

    def _update_detail(self, module) -> None:
        detail = self.query_one("#module-detail", Static)
        if not module:
            detail.update("[dim]No matching module[/dim]")
            return

        def show_list(values):
            return ", ".join(rich_escape(str(value)) for value in values) if values else "None"

        lines = [
            f"[bold]{rich_escape(module['name'])}[/bold]",
            "",
            f"[bold]Type:[/bold] {rich_escape(module['type'])}",
            f"[bold]Needs API Key:[/bold] {'Yes' if module.get('needs_api_key') else 'No'}",
            f"[bold]Description:[/bold] {rich_escape(module.get('description', '') or 'None')}",
            f"[bold]Flags:[/bold] {show_list(module.get('flags', []))}",
            f"[bold]Consumes:[/bold] {show_list(module.get('watched_events', []))}",
            f"[bold]Produces:[/bold] {show_list(module.get('produced_events', []))}",
        ]
        if module.get("author"):
            lines.append(f"[bold]Author:[/bold] {rich_escape(module['author'])}")
        if module.get("created_date"):
            lines.append(f"[bold]Created:[/bold] {rich_escape(module['created_date'])}")

        lines.extend(["", "[bold]Configuration Options[/bold]"])
        options = module.get("options", [])
        if not options:
            lines.append("None")
        for option in options:
            lines.extend(
                [
                    "",
                    f"[bold]{rich_escape(option['name'])}[/bold] ({rich_escape(option['type'])})",
                    f"Default: {rich_escape(option['default'])}",
                    rich_escape(option["description"]),
                ]
            )
        detail.update("\n".join(lines))

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if event.data_table.id != "module-table" or event.cursor_row >= len(self.visible_modules):
            return
        self._update_detail(self.visible_modules[event.cursor_row])

    def on_filter_bar_filter_changed(self, event: FilterBar.FilterChanged) -> None:
        self._render_modules()

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "module-type":
            self._render_modules()

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "module-refresh":
            await self.refresh_modules()
            self.notify("Module list refreshed", timeout=2)
