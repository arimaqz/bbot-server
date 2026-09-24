"""
Target detail widget for BBOT Server TUI
"""

from textual.app import ComposeResult
from textual.widgets import Static
from textual.containers import VerticalScroll

from bbot_server.cli.tui.utils.formatters import format_timestamp, get_field


class TargetDetail(VerticalScroll):
    """Widget for displaying detailed target information"""

    def compose(self) -> ComposeResult:
        """Create the static text widget"""
        yield Static("[dim]No target selected[/dim]", id="target-detail-text")

    def update_target(self, target) -> None:
        """
        Update the detail view with target information

        Args:
            target: Target model
        """
        try:
            detail_text = self.query_one("#target-detail-text", Static)
        except Exception:
            return

        if not target:
            detail_text.update("[dim]No target selected[/dim]")
            return

        # Build detail text
        details = []

        # Basic info
        details.append(f"[bold]Name:[/bold] {get_field(target, 'name', 'UNKNOWN')}")
        details.append(f"[bold]Description:[/bold] {get_field(target, 'description', 'N/A')}")

        # Default status
        is_default = get_field(target, "default", False)
        details.append(f"[bold]Default Target:[/bold] {'Yes' if is_default else 'No'}")

        # ID
        target_id = get_field(target, "id", "N/A")
        details.append(f"[bold]ID:[/bold] {target_id}")

        # Target list
        target_list = get_field(target, "target", [])
        if target_list:
            targets_str = ", ".join(target_list)
            details.append(f"[bold]Targets ({len(target_list)}):[/bold] {targets_str}")
        else:
            details.append(f"[bold]Targets:[/bold] (none)")

        # Seeds
        seeds = get_field(target, "seeds", [])
        if seeds:
            seeds_str = ", ".join(seeds)
            details.append(f"[bold]Seeds ({len(seeds)}):[/bold] {seeds_str}")

        # Blacklist
        blacklist = get_field(target, "blacklist", [])
        if blacklist:
            blacklist_str = ", ".join(blacklist)
            details.append(f"[bold]Blacklist ({len(blacklist)}):[/bold] {blacklist_str}")

        # Strict DNS scope
        strict_dns = get_field(target, "strict_scope", False)
        details.append(f"[bold]Strict DNS Scope:[/bold] {'Yes' if strict_dns else 'No'}")

        # Sizes
        target_size = get_field(target, "target_size", 0)
        seed_size = get_field(target, "seed_size", 0)
        blacklist_size = get_field(target, "blacklist_size", 0)
        details.append(f"[bold]Target Size:[/bold] {target_size}")
        details.append(f"[bold]Seed Size:[/bold] {seed_size}")
        details.append(f"[bold]Blacklist Size:[/bold] {blacklist_size}")

        # Hashes
        hash_val = get_field(target, "hash", "N/A")
        details.append(f"[bold]Hash:[/bold] {hash_val}")

        scope_hash = get_field(target, "scope_hash", "N/A")
        details.append(f"[bold]Scope Hash:[/bold] {scope_hash}")

        # Timestamps
        created = get_field(target, "created")
        details.append(f"[bold]Created:[/bold] {format_timestamp(created) if created is not None else '-'}")

        modified = get_field(target, "modified")
        details.append(f"[bold]Modified:[/bold] {format_timestamp(modified) if modified is not None else '-'}")

        detail_text.update("\n\n".join(details))
