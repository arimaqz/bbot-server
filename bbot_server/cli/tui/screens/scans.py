"""
Scans screen for BBOT Server TUI
"""

from textual.app import ComposeResult

# Removed Screen import
from textual.containers import Container, Grid, Horizontal, Vertical
from textual.widgets import Static, Button, Select
from textual.reactive import reactive
from textual import work

from bbot_server.cli.tui.widgets.scan_table import ScanTable
from bbot_server.cli.tui.widgets.scan_detail import ScanDetail
from bbot_server.cli.tui.widgets.filter_bar import FilterBar
from bbot_server.cli.tui.widgets.paginated_table import PaginatedTableContainer
from bbot_server.cli.tui.utils.colors import loading_text, success_text, warning_text, error_text
from bbot_server.cli.tui.screens.start_scan_modal import StartScanModal
from bbot_server.cli.tui.screens.confirm_modal import ConfirmModal


class ScansScreen(Container):
    """
    Scan management screen

    Displays a table of all scans with filtering, details panel,
    and actions for creating, cancelling, and refreshing scans.
    """

    filter_text = reactive("")
    selected_scan_id = reactive(None)

    def __init__(self, app):
        super().__init__()
        self.bbot_app = app
        self._refresh_timer = None
        self._has_loaded = False

    def compose(self) -> ComposeResult:
        """Create child widgets"""
        with Container(id="scans-container"):
            # Filter bar at top
            with Horizontal(id="filter-container", classes="controls-bar"):
                yield FilterBar(placeholder="Filter by scan name or target...", id="scan-filter")
                yield Button("Refresh", id="refresh-btn", variant="primary")

            # Status bar
            yield Static("Loading scans...", id="scans-status", classes="status-bar")

            # Main content: table on left, detail on right
            with Horizontal(id="scans-content", classes="content-area"):
                with Vertical(id="scans-table-container", classes="table-container"):
                    yield PaginatedTableContainer(
                        ScanTable(id="scan-table"), auto_page_size=True, id="scan-pagination"
                    )
                    with Grid(id="scan-actions", classes="action-buttons"):
                        yield Button("New Scan", id="new-scan-btn", variant="success")
                        yield Button("Cancel Scan", id="cancel-scan-btn", variant="error", disabled=True)
                        yield Button("Delete Scan", id="delete-scan-btn", variant="error", disabled=True)
                        yield Select(
                            [("HTML", "html"), ("PDF", "pdf"), ("CSV", "csv"), ("JSON", "json")],
                            value="html",
                            allow_blank=False,
                            id="scan-report-format",
                        )
                        yield Button("Export Report", id="report-scan-btn", disabled=True)

                with Vertical(id="scan-detail-container", classes="detail-container"):
                    yield Static("[bold]Scan Details[/bold]", id="detail-header")
                    yield ScanDetail(id="scan-detail", classes="detail-panel")

    async def on_mount(self) -> None:
        """Called when screen is mounted"""
        # Start periodic refresh (paused until first load)
        self._refresh_timer = self.set_interval(5.0, self.refresh_scans, pause=True)

    async def load_initial_data(self) -> None:
        """Load data on first visit to this tab"""
        if self._has_loaded:
            return

        self._has_loaded = True
        await self.refresh_scans(show_loading=True)

        # Resume periodic refresh
        if self._refresh_timer:
            self._refresh_timer.resume()

    async def on_unmount(self) -> None:
        """Called when screen is unmounted"""
        # Stop periodic refresh
        if self._refresh_timer:
            self._refresh_timer.stop()

    async def refresh_scans(self, show_loading: bool = False) -> None:
        """Fetch and display scans from server with pagination

        Args:
            show_loading: If True, show "Loading..." status message (for manual refreshes)
        """
        # Check if services are initialized
        if not self.bbot_app.data_service:
            return

        try:
            status = self.query_one("#scans-status", Static)
            # Only show loading message on initial load or manual refresh
            if show_loading:
                status.update(loading_text("Loading scans..."))

            # Get pagination parameters
            pagination = self.query_one("#scan-pagination", PaginatedTableContainer)
            skip_limit = pagination.get_skip_limit()
            if skip_limit is None:
                return
            skip, limit = skip_limit

            # Fetch scans with server-side pagination and search
            scans, total = await self.bbot_app.data_service.get_scans_paginated(
                skip=skip, limit=limit, search=self.filter_text or None
            )

            # Update pagination with total count
            pagination.total_items = total

            # Update table with current page of scans
            table = self.query_one("#scan-table", ScanTable)
            table.update_scans(scans)
            self._update_selection(table.get_selected_scan())

            # Update status (pagination widget shows page info, status shows filter info)
            if total > 0:
                if self.filter_text:
                    status.update(success_text(f"Filtered: {total} scans match"))
                else:
                    status.update(success_text(f"{total} total scans"))
            else:
                status.update(warning_text("No scans found"))

        except Exception as e:
            # Show error
            status = self.query_one("#scans-status", Static)
            status.update(error_text(f"Error loading scans: {e}"))

    def on_data_table_row_highlighted(self, event) -> None:
        """Handle row selection in scan table"""
        # Only handle events from the scan table
        if event.data_table.id != "scan-table":
            return

        table = self.query_one("#scan-table", ScanTable)
        self._update_selection(table.get_selected_scan())

    def _update_selection(self, scan) -> None:
        """Keep details and actions synchronized with the current row."""
        # Update detail panel
        detail = self.query_one("#scan-detail", ScanDetail)
        detail.update_scan(scan)

        # Update selected scan ID
        if scan:
            self.selected_scan_id = scan["id"]
        else:
            self.selected_scan_id = None
        self.query_one("#cancel-scan-btn", Button).disabled = not scan or scan["status"] not in (
            "QUEUED",
            "STARTING",
            "RUNNING",
            "ABORTING",
        )
        self.query_one("#report-scan-btn", Button).disabled = scan is None
        self.query_one("#delete-scan-btn", Button).disabled = not scan or scan["status"] not in (
            "FINISHED",
            "FAILED",
            "ABORTED",
        )

    def on_filter_bar_filter_changed(self, event: FilterBar.FilterChanged) -> None:
        """Handle filter text changes"""
        self.filter_text = event.filter_text
        # Reset to first page when filter changes
        pagination = self.query_one("#scan-pagination", PaginatedTableContainer)
        pagination.reset_to_first_page()
        # Trigger refresh with new filter (show loading since user-initiated)
        self.run_worker(self.refresh_scans(show_loading=True))

    def on_paginated_table_container_page_changed(self, event: PaginatedTableContainer.PageChanged) -> None:
        """Handle page navigation"""
        self.run_worker(self.refresh_scans())

    def on_paginated_table_container_page_size_changed(self, event: PaginatedTableContainer.PageSizeChanged) -> None:
        """Handle page size changes from auto-sizing"""
        # Refetch data with new page size
        self.run_worker(self.refresh_scans())

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses"""
        if event.button.id == "refresh-btn":
            await self.action_refresh()
        elif event.button.id == "new-scan-btn":
            self.action_new_scan()
        elif event.button.id == "cancel-scan-btn":
            self.action_cancel_scan()
        elif event.button.id == "delete-scan-btn":
            self.action_delete_scan()
        elif event.button.id == "report-scan-btn":
            self.action_export_report()

    def action_new_scan(self) -> None:
        self._new_scan()

    @work(exclusive=True)
    async def _new_scan(self) -> None:
        try:
            targets, presets = await self.bbot_app.data_service.get_scan_options()
            if not targets or not presets:
                self.notify("Create a target and preset before starting a scan", severity="warning")
                return
            options = await self.app.push_screen_wait(StartScanModal(targets, presets))
            if options is not None:
                scan = await self.bbot_app.data_service.start_scan(**options)
                self.notify(f"Scan '{scan.name}' queued", timeout=4)
                await self.refresh_scans()
        except Exception as exc:
            self.notify(f"Could not start scan: {exc}", severity="error", timeout=6)

    def action_cancel_scan(self) -> None:
        scan = self.query_one("#scan-table", ScanTable).get_selected_scan()
        if scan and scan["status"] in ("QUEUED", "STARTING", "RUNNING", "ABORTING"):
            self._cancel_scan(scan)

    @work(exclusive=True)
    async def _cancel_scan(self, scan) -> None:
        confirmed = await self.app.push_screen_wait(
            ConfirmModal("Cancel Scan", f"Cancel scan '{scan['name']}'?", confirm_label="Cancel scan", danger=True)
        )
        if confirmed:
            try:
                await self.bbot_app.data_service.cancel_scan(scan["id"])
                self.notify(f"Cancellation requested for '{scan['name']}'", timeout=4)
                await self.refresh_scans()
            except Exception as exc:
                self.notify(f"Could not cancel scan: {exc}", severity="error", timeout=6)

    def action_delete_scan(self) -> None:
        scan = self.query_one("#scan-table", ScanTable).get_selected_scan()
        if scan and scan["status"] in ("FINISHED", "FAILED", "ABORTED"):
            self._delete_scan(scan)

    @work(exclusive=True)
    async def _delete_scan(self, scan) -> None:
        confirmed = await self.app.push_screen_wait(
            ConfirmModal(
                "Delete Scan",
                f"Permanently delete scan '{scan['name']}'?",
                confirm_label="Delete scan",
                danger=True,
            )
        )
        if confirmed:
            try:
                await self.bbot_app.data_service.delete_scan(scan["id"])
                self.notify(f"Scan '{scan['name']}' deleted", timeout=4)
                await self.refresh_scans()
            except Exception as exc:
                self.notify(f"Could not delete scan: {exc}", severity="error", timeout=6)

    def action_export_report(self) -> None:
        scan = self.query_one("#scan-table", ScanTable).get_selected_scan()
        if scan:
            self._export_report(scan)

    @work(exclusive=True)
    async def _export_report(self, scan) -> None:
        try:
            from bbot_server.reporting import report_display_path

            format = self.query_one("#scan-report-format", Select).value
            path = await self.bbot_app.data_service.export_scan_report(scan, format=format)
            self.notify(f"Report saved: {report_display_path(path)}", timeout=10)
        except Exception as exc:
            self.notify(f"Could not export report: {exc}", severity="error", timeout=6)

    async def action_refresh(self) -> None:
        """Refresh scans"""
        await self.refresh_scans(show_loading=True)
        self.notify("Scans refreshed", timeout=2)

    def action_focus_filter(self) -> None:
        """Focus the filter input"""
        filter_bar = self.query_one("#scan-filter", FilterBar)
        filter_bar.focus()

    def action_clear_filter(self) -> None:
        """Clear the filter"""
        filter_bar = self.query_one("#scan-filter", FilterBar)
        filter_bar.clear_filter()
        self.filter_text = ""
        # Reset pagination when filter is cleared
        pagination = self.query_one("#scan-pagination", PaginatedTableContainer)
        pagination.reset_to_first_page()
        # Trigger refresh to show all scans
        self.run_worker(self.refresh_scans())
