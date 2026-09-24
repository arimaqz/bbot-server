"""Scoped target/domain summaries and exports."""

from textual import work
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, VerticalScroll
from textual.widgets import Button, Input, Select, Static
from rich.markup import escape as rich_escape

from bbot_server.reporting import SEVERITIES, report_display_path, report_path, write_report


FORMATS = [(format.upper(), format) for format in ("html", "pdf", "csv", "json")]


class ReportsScreen(Container):
    DEFAULT_CSS = """
    #reports-content { width: 100%; padding: 1 2; }
    #reports-content .controls-bar { width: 100%; height: 4; }
    #report-target { width: 100%; }
    #report-domain { width: 60%; }
    #report-format { width: 20; }
    #reports-content Button { width: auto; min-width: 14; }
    #report-summary { margin: 1 0; padding: 1; border: solid $secondary; height: auto; }
    """

    def __init__(self, app):
        super().__init__()
        self.bbot_app = app
        self.targets = {}
        self._has_loaded = False

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="reports-content"):
            yield Static("[bold]Scoped security summary[/bold]", classes="section-title")
            yield Static("Choose one target or enter a domain. Findings reflect current inventory across scans.")
            yield Select([], prompt="Select target", id="report-target")
            with Horizontal(classes="controls-bar"):
                yield Input(placeholder="Or enter a domain", id="report-domain")
                yield Button("View Summary", id="report-view", variant="primary")
            yield Static("Select a scope to view its summary.", id="report-summary")
            with Horizontal(classes="controls-bar"):
                yield Select(FORMATS, value="html", allow_blank=False, id="report-format")
                yield Button("Export", id="report-export", variant="success")

    async def load_initial_data(self):
        if self._has_loaded:
            return
        self._has_loaded = True
        try:
            targets = await self.bbot_app.data_service.get_targets()
            self.targets = {str(target.id): target for target in targets}
            self.query_one("#report-target", Select).set_options([(t.name, str(t.id)) for t in targets])
        except Exception as exc:
            self.notify(f"Could not load targets: {exc}", severity="error")

    def scope(self):
        target_id = self.query_one("#report-target", Select).value
        domain = self.query_one("#report-domain", Input).value.strip()
        if domain and target_id is not Select.NULL:
            raise ValueError("Choose a target or enter a domain, not both")
        if domain:
            return {"domain": domain}
        if target_id is not Select.NULL and target_id in self.targets:
            return {"target": self.targets[target_id].model_dump(mode="json")}
        raise ValueError("Choose a target or enter a domain")

    async def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "report-view":
            self._view()
        elif event.button.id == "report-export":
            self._export()

    @work(exclusive=True)
    async def _view(self):
        try:
            snapshot = await self.bbot_app.data_service.get_scope_report(**self.scope())
            counts = snapshot["severity_counts"]
            total = sum(counts.values())
            breakdown = "   ·   ".join(f"{level.title()}: {counts[level]}" for level in SEVERITIES)
            technologies = (
                ", ".join(
                    f"{rich_escape(item['name'])} ({item['host_count']} hosts)"
                    for item in snapshot["technologies"][:5]
                )
                or "None recorded"
            )
            self.query_one("#report-summary", Static).update(
                f"[bold]{rich_escape(snapshot['scope'])}[/bold]   |   {snapshot['assets']} assets   |   {total} active findings\n"
                f"{breakdown}\nTop technologies: {technologies}\n\n"
                "Reports include discovered assets with their open ports, technologies, findings, and scope details."
            )
        except Exception as exc:
            self.notify(f"Could not load summary: {exc}", severity="error", timeout=6)

    @work(exclusive=True)
    async def _export(self):
        try:
            snapshot = await self.bbot_app.data_service.get_scope_report(**self.scope())
            format = self.query_one("#report-format", Select).value
            path = report_path(snapshot["scan"]).with_suffix(f".{format}")
            write_report(snapshot, format, path)
            self.notify(f"Saved report: {report_display_path(path)}", timeout=10)
        except Exception as exc:
            self.notify(f"Could not export report: {exc}", severity="error", timeout=6)
