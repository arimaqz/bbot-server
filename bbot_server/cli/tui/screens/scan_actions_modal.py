"""Secondary actions for the selected scan (cancel / delete)."""

from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.screen import ModalScreen
from textual.widgets import Button, Static


class ScanActionsModal(ModalScreen[str | None]):
    """Returns 'cancel', 'delete', or None."""

    CSS = """
    ScanActionsModal {
        align: center middle;
    }

    #scan-actions-dialog {
        width: 52;
        border: thick $background 80%;
        background: $surface;
        padding: 1 2;
    }

    #scan-actions-title {
        text-style: bold;
        color: $primary;
        padding-bottom: 1;
    }

    #scan-actions-buttons {
        height: auto;
        align: center middle;
        padding-top: 1;
    }

    Button {
        margin: 0 1;
    }
    """

    def __init__(self, scan_name: str, can_cancel: bool, can_delete: bool):
        super().__init__()
        self.scan_name = scan_name
        self.can_cancel = can_cancel
        self.can_delete = can_delete

    def compose(self) -> ComposeResult:
        with Container(id="scan-actions-dialog"):
            yield Static(f"Manage scan: {self.scan_name}", id="scan-actions-title")
            yield Static(
                "Cancel stops an active scan. Delete removes a finished record permanently.",
                id="scan-actions-help",
            )
            with Horizontal(id="scan-actions-buttons"):
                yield Button(
                    "Cancel scan",
                    id="scan-action-cancel",
                    variant="warning",
                    disabled=not self.can_cancel,
                )
                yield Button(
                    "Delete scan",
                    id="scan-action-delete",
                    variant="error",
                    disabled=not self.can_delete,
                )
                yield Button("Close", id="scan-action-close", variant="default")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "scan-action-cancel":
            self.dismiss("cancel")
        elif event.button.id == "scan-action-delete":
            self.dismiss("delete")
        else:
            self.dismiss(None)

    def on_key(self, event) -> None:
        if event.key == "escape":
            self.dismiss(None)
