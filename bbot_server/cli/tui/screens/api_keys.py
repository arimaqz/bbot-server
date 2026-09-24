"""Manage keys in the local server configuration only."""

import os
from urllib.parse import urlparse

from rich.markup import escape as rich_escape
from textual import work
from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.screen import ModalScreen
from textual.widgets import Button, DataTable, Static

from bbot_server.cli.tui.screens.confirm_modal import ConfirmModal


class KeyRevealModal(ModalScreen[None]):
    CSS = """
    KeyRevealModal { align: center middle; }
    #key-reveal { width: 74; height: auto; padding: 2; border: thick $primary; background: $surface; }
    """

    def __init__(self, key):
        super().__init__()
        self.key = key

    def compose(self) -> ComposeResult:
        with Container(id="key-reveal"):
            yield Static("[bold]New API key[/bold]\nCopy this key now and store it securely.\n\n" + self.key)
            yield Button("Done", id="key-reveal-done", variant="primary")

    def on_button_pressed(self, event: Button.Pressed):
        self.dismiss(None)


class APIKeysScreen(Container):
    """Only operates on the config file shared with a server on this machine."""

    def __init__(self, app):
        super().__init__()
        self.bbot_app = app
        self._has_loaded = False

    def compose(self) -> ComposeResult:
        with Container():
            yield Static(
                "Local server configuration keys. Existing values are masked.", id="keys-context", classes="status-bar"
            )
            yield DataTable(id="keys-table")
            with Horizontal(classes="action-buttons"):
                yield Button("Add Key", id="key-add", variant="success")
                yield Button("Revoke Key", id="key-revoke", variant="error")
                yield Button("Refresh", id="key-refresh")

    def on_mount(self):
        table = self.query_one(DataTable)
        table.cursor_type = "row"
        table.add_columns("Key", "Source")

    def _config(self):
        from bbot_server.config import BBOT_SERVER_CONFIG, BBOT_SERVER_CONFIG_PATH

        hostname = urlparse(self.bbot_app.config.url).hostname
        if hostname not in ("localhost", "127.0.0.1", "::1"):
            raise ValueError(
                "API keys can only be managed on the server machine. Connect to localhost with its config file."
            )
        if not BBOT_SERVER_CONFIG_PATH.is_file():
            raise ValueError("Local server config file is missing")
        return BBOT_SERVER_CONFIG

    async def load_initial_data(self):
        if not self._has_loaded:
            self._has_loaded = True
            self.refresh_keys()

    def refresh_keys(self):
        status = self.query_one("#keys-context", Static)
        table = self.query_one(DataTable)
        table.clear()
        try:
            config = self._config()
            config.refresh()
            for key in sorted(config.get_api_keys(), key=str):
                value = str(key)
                table.add_row(
                    f"••••••••-{value[-12:]}", "Primary" if value == config.api_key else "Additional", key=value
                )
            status.update(f"{table.row_count} keys in local server configuration. New keys are shown once.")
        except Exception as exc:
            status.update(rich_escape(str(exc)))

    def selected_key(self):
        table = self.query_one(DataTable)
        return str(table.coordinate_to_cell_key(table.cursor_coordinate)[0].value) if table.row_count else None

    async def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "key-refresh":
            self.refresh_keys()
        elif event.button.id == "key-add":
            self._add_key()
        elif event.button.id == "key-revoke":
            key = self.selected_key()
            if key:
                self._revoke_key(key)

    @work(exclusive=True)
    async def _add_key(self):
        try:
            config = self._config()
            new_key = str(config.add_api_key())
            self.refresh_keys()
            await self.app.push_screen_wait(KeyRevealModal(new_key))
        except Exception as exc:
            self.notify(f"Could not add key: {exc}", severity="error", timeout=6)

    @work(exclusive=True)
    async def _revoke_key(self, key):
        try:
            config = self._config()
            if os.environ.get("BBOT_SERVER_API_KEY") and key == config.api_key:
                raise ValueError("This key is set by an environment variable; remove it from the server environment")
            if key == str(config.get_api_key()):
                raise ValueError("The UI is using this key. Switch the client to another key before revoking it")
            if not await self.app.push_screen_wait(
                ConfirmModal(
                    "Revoke API Key",
                    f"Revoke key ending in {key[-12:]}? Clients using it will lose access.",
                    "Revoke",
                    danger=True,
                )
            ):
                return
            config.revoke_api_key(key)
            self.refresh_keys()
            self.notify("API key revoked")
        except Exception as exc:
            self.notify(f"Could not revoke key: {exc}", severity="error", timeout=6)
