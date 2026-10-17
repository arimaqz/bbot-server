"""Keyboard shortcut help overlay."""

from textual.app import ComposeResult
from textual.containers import Container, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Static

from bbot_server.cli.tui.utils.keybindings import get_help_text


class HelpModal(ModalScreen):
    CSS = """
    HelpModal {
        align: center middle;
    }

    #help-dialog {
        width: 72;
        max-height: 22;
        border: thick $background 80%;
        background: $surface;
        padding: 1 2;
    }

    #help-body {
        height: 1fr;
        max-height: 16;
    }

    #help-close {
        width: 100%;
        margin-top: 1;
    }
    """

    def compose(self) -> ComposeResult:
        with Container(id="help-dialog"):
            yield Static("[bold]Keyboard shortcuts[/bold]", id="help-title")
            with VerticalScroll(id="help-body"):
                yield Static(get_help_text(), id="help-text")
            yield Button("Close", id="help-close", variant="primary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "help-close":
            self.dismiss(None)

    def on_key(self, event) -> None:
        if event.key in {"escape", "question_mark"}:
            self.dismiss(None)
