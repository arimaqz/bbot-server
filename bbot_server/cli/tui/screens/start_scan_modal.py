"""Start a scan using an existing target and preset."""

from textual.app import ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Checkbox, Input, Select, Static


class StartScanModal(ModalScreen[dict | None]):
    CSS = """
    StartScanModal { align: center middle; }
    #start-scan-dialog { width: 72; height: auto; max-height: 90%; padding: 1 2; border: thick $primary; background: $surface; }
    #start-scan-dialog Static { margin: 1 0 0 0; }
    #start-scan-dialog Select, #start-scan-dialog Input { width: 100%; }
    #start-scan-buttons { height: 3; margin-top: 1; align: center middle; }
    #start-scan-buttons Button { margin: 0 1; }
    """

    def __init__(self, targets, presets):
        super().__init__()
        self.targets = targets
        self.presets = presets

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="start-scan-dialog"):
            yield Static("[bold]Start a scan[/bold]")
            yield Static("Target")
            yield Select([(t.name, str(t.id)) for t in self.targets], prompt="Choose a target", id="scan-target")
            yield Static("Preset")
            yield Select([(p.name, str(p.id)) for p in self.presets], prompt="Choose a preset", id="scan-preset")
            yield Static("Scan name (optional)")
            yield Input(placeholder="Generate a name automatically", id="scan-name")
            yield Checkbox("Include currently known assets as seeds", id="scan-seeds")
            with Horizontal(id="start-scan-buttons"):
                yield Button("Start", id="start-scan-submit", variant="success")
                yield Button("Cancel", id="start-scan-dismiss")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "start-scan-dismiss":
            self.dismiss(None)
        elif event.button.id == "start-scan-submit":
            target = self.query_one("#scan-target", Select).value
            preset = self.query_one("#scan-preset", Select).value
            if target is Select.NULL or preset is Select.NULL:
                self.notify("Choose both a target and a preset", severity="warning")
                return
            self.dismiss(
                {
                    "target_id": target,
                    "preset_id": preset,
                    "name": self.query_one("#scan-name", Input).value.strip() or None,
                    "seed_with_current_assets": self.query_one("#scan-seeds", Checkbox).value,
                }
            )
