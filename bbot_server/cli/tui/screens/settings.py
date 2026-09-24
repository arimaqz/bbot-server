"""Application-wide display settings."""

from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.widgets import Button, Input, Static


class SettingsScreen(Container):
    DEFAULT_CSS = """
    #settings-content { width: 100%; padding: 1 2; }
    #setting-name { width: 100%; margin: 1 0; }
    #settings-actions { height: 3; }
    """

    def __init__(self, app):
        super().__init__()
        self.bbot_app = app
        self._has_loaded = False

    def compose(self) -> ComposeResult:
        with Container(id="settings-content"):
            yield Static("[bold]Application settings[/bold]", classes="section-title")
            yield Static("Display name used throughout the UI and generated reports.")
            yield Input(value=self.bbot_app.config.name, placeholder="Application name", id="setting-name")
            with Horizontal(id="settings-actions"):
                yield Button("Save Settings", id="setting-save", variant="success")

    async def load_initial_data(self):
        if self._has_loaded:
            return
        self._has_loaded = True
        refresh = getattr(self.bbot_app.config, "refresh", None)
        if refresh:
            refresh()
        self.query_one("#setting-name", Input).value = self.bbot_app.config.name

    async def on_button_pressed(self, event: Button.Pressed):
        if event.button.id != "setting-save":
            return
        try:
            name = self.query_one("#setting-name", Input).value.strip()
            self.bbot_app.config.set_name(name)
            self.bbot_app.apply_display_name(self.bbot_app.config.name)
            self.notify("Settings saved")
        except Exception as exc:
            self.notify(f"Could not save settings: {exc}", severity="error", timeout=6)
