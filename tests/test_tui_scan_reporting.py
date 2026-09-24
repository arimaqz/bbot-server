"""UI scan actions and executive report without external services."""

from pathlib import Path
from types import SimpleNamespace

import pytest
from textual.app import App, ComposeResult
from textual.widgets import Select

from bbot_server.cli.tui.screens.scans import ScansScreen
from bbot_server.cli.tui.screens.start_scan_modal import StartScanModal
from bbot_server.reporting import create_report, render_report, collect_report, report_display_path, write_report
from bbot_server.cli.tui.screens.reports import ReportsScreen


SCAN = {
    "id": "SCAN:1",
    "name": "review",
    "status": "FINISHED",
    "created": 1,
    "started_at": 1,
    "finished_at": 2,
    "duration_seconds": 1,
    "target": {"id": "target-1", "name": "Example", "target": ["example.org"]},
    "preset": {"name": "baseline"},
}


class ReportClient:
    def __init__(self):
        self.requests = []

    async def count_assets(self, **kwargs):
        self.requests.append(("assets", kwargs))
        return 12

    async def count_findings(self, **kwargs):
        self.requests.append(("findings", kwargs))
        return 2 if kwargs["min_severity"] == 5 else 0

    async def query_assets(self, **kwargs):
        self.requests.append(("asset_details", kwargs))
        yield {"host": "example.org", "open_ports": [80, 443], "technologies": ["Apache"]}
        yield {"host": "api.example.org", "open_ports": [], "technologies": []}

    async def query_findings(self, **kwargs):
        self.requests.append(("details", kwargs))
        yield {
            "severity_score": 5,
            "name": "<script>alert(1)</script>",
            "host": "example.org",
            "description": "<unsafe>",
        }

    async def get_stats(self, **kwargs):
        self.requests.append(("stats", kwargs))
        return {"assets": 12}

    async def get_technologies_summary(self, **kwargs):
        self.requests.append(("technologies", kwargs))
        return [{"technology": "Apache", "hosts": ["example.org"], "last_seen": 1}]


@pytest.mark.asyncio
async def test_report_scopes_counts_and_escapes_values(tmp_path):
    client = ReportClient()
    path = await create_report(client, SCAN, tmp_path)
    html = path.read_text()
    assert "12</strong>" in html
    assert "2</strong>" in html
    assert "&lt;script&gt;" in html and "<script>" not in html
    assert "&lt;unsafe&gt;" in html
    assert "multiple scans" in html
    assert "Discovered assets" in html
    assert "<h2>Open ports</h2>" not in html
    assert "Technologies" in html
    assert "Findings" in html
    assert "api.example.org" in html
    assert "80, 443" in html
    assert "Apache" in html
    assert all(kwargs["target_id"] == "target-1" for _, kwargs in client.requests)
    assert all(kwargs["ignored"] is False for kind, kwargs in client.requests if kind in ("findings", "details"))
    assert [r[1]["min_severity"] for r in client.requests if r[0] == "findings"] == [5, 4, 3, 2, 1]


@pytest.mark.asyncio
async def test_report_exports_and_redacts_preset_secrets(tmp_path):
    import csv
    import json
    import shutil
    import subprocess

    scan = {**SCAN, "preset": {"name": "baseline", "preset": {"config": {"api_key": "secret-value"}}}}
    snapshot = await collect_report(ReportClient(), scan=scan)
    assert snapshot["scan"]["preset"] == {"name": "baseline"}
    assert snapshot["asset_records"] == [
        {"host": "api.example.org", "open_ports": [], "technologies": []},
        {"host": "example.org", "open_ports": [80, 443], "technologies": ["Apache"]},
    ]
    assert snapshot["open_ports"] == [
        {"host": "example.org", "port": 80},
        {"host": "example.org", "port": 443},
    ]
    assert snapshot["technologies"] == [{"name": "Apache", "host_count": 1, "hosts": ["example.org"]}]
    for format in ("html", "pdf", "csv", "json"):
        path = write_report(snapshot, format, tmp_path / f"report.{format}")
        assert path.is_file() and path.stat().st_size > 100
        if format != "pdf":
            assert "secret-value" not in path.read_text()
    assert json.loads((tmp_path / "report.json").read_text())["severity_counts"]["CRITICAL"] == 2
    with (tmp_path / "report.csv").open() as stream:
        rows = list(csv.DictReader(stream))
    assert any(row["record_type"] == "priority_finding" for row in rows)
    assert any(row["record_type"] == "asset" and row["host"] == "example.org" for row in rows)
    assert any(row["record_type"] == "open_port" and row["name"] == "443" for row in rows)
    assert any(row["record_type"] == "technology" and row["name"] == "Apache" for row in rows)
    if shutil.which("pdftotext"):
        result = subprocess.run(
            ["pdftotext", str(tmp_path / "report.pdf"), "-"], capture_output=True, text=True, check=True
        )
        assert "Example - Security snapshot" in result.stdout
        assert "secret-value" not in result.stdout


@pytest.mark.asyncio
async def test_domain_report_uses_domain_filters():
    client = ReportClient()
    snapshot = await collect_report(client, domain="Example.ORG")
    assert snapshot["scope"] == "example.org"
    assert all(kwargs["domain"] == "example.org" for _, kwargs in client.requests)
    with pytest.raises(ValueError):
        await collect_report(client, domain="bad domain")


def test_report_escapes_scope_and_scan_names():
    scan = {**SCAN, "name": "<untrusted>", "target": {**SCAN["target"], "target": ["<scope>"]}}
    html = render_report(scan, 0, {}, [], generated_at=1)
    assert "&lt;untrusted&gt;" in html and "&lt;scope&gt;" in html
    assert "<untrusted>" not in html
    assert "No active" in html


def test_report_uses_custom_name_and_omits_recommended_next_steps():
    html = render_report(SCAN, 0, {}, [], generated_at=1, brand_name="Acme Security")

    assert "Acme Security / Security overview" in html
    assert "<title>Acme Security | Example security snapshot</title>" in html
    assert "Recommended next steps" not in html


def test_report_display_path_uses_host_directory(monkeypatch):
    monkeypatch.setenv("BBOT_REPORTS_HOST_DIR", r"C:\Users\analyst\bbot-reports")

    assert report_display_path(Path("/home/bbot/bbot-reports/report.html")) == (
        r"C:\Users\analyst\bbot-reports\report.html"
    )


class ScanApp(App):
    def __init__(self, service):
        super().__init__()
        self.data_service = service

    def compose(self) -> ComposeResult:
        yield ScansScreen(self)


class FakeService:
    def __init__(self):
        self.started = []
        self.cancelled = []
        self.deleted = []
        self.exported = []
        self.scan_queries = 0
        self.scans = [SCAN]

    async def get_scans_paginated(self, **kwargs):
        self.scan_queries += 1
        return self.scans, len(self.scans)

    async def get_scan_options(self):
        return [SimpleNamespace(id="target-1", name="Example")], [SimpleNamespace(id="preset-1", name="baseline")]

    async def start_scan(self, **kwargs):
        self.started.append(kwargs)
        return SimpleNamespace(name="new-scan")

    async def cancel_scan(self, scan_id):
        self.cancelled.append(scan_id)

    async def delete_scan(self, scan_id):
        self.deleted.append(scan_id)

    async def export_scan_report(self, scan, format="html"):
        self.exported.append(scan)
        return Path("report.html")


@pytest.mark.asyncio
async def test_scans_screen_starts_cancels_and_exports():
    service = FakeService()
    app = ScanApp(service)
    async with app.run_test(size=(110, 45)) as pilot:
        screen = app.query_one(ScansScreen)
        await screen.load_initial_data()
        await pilot.pause()
        await pilot.click("#new-scan-btn")
        await pilot.pause()
        assert isinstance(app.screen, StartScanModal)
        app.screen.query_one("#scan-target", Select).value = "target-1"
        app.screen.query_one("#scan-preset", Select).value = "preset-1"
        await pilot.click("#start-scan-submit")
        await pilot.pause()
        assert service.started[0]["target_id"] == "target-1"
        screen.query_one("#scan-table")._restore_selection("SCAN:1")
        await pilot.click("#report-scan-btn")
        await pilot.pause()
        assert service.exported[0]["id"] == "SCAN:1"
        # Simulate a running row; cancel requires explicit confirmation.
        running = {**SCAN, "status": "RUNNING"}
        screen.query_one("#scan-table").update_scans([running])
        await pilot.pause()
        await pilot.click("#cancel-scan-btn")
        await pilot.pause()
        await pilot.click("#confirm-btn")
        await pilot.pause()
        assert service.cancelled == ["SCAN:1"]
        screen.query_one("#scan-table").update_scans([SCAN])
        await pilot.pause()
        await pilot.click("#delete-scan-btn")
        await pilot.pause()
        await pilot.click("#confirm-btn")
        await pilot.pause()
        assert service.deleted == ["SCAN:1"]


@pytest.mark.asyncio
async def test_scans_screen_waits_for_auto_page_size_without_showing_error(monkeypatch):
    service = FakeService()
    app = ScanApp(service)
    async with app.run_test(size=(80, 24)):
        screen = app.query_one(ScansScreen)
        pagination = screen.query_one("#scan-pagination")
        monkeypatch.setattr(pagination, "get_skip_limit", lambda: None)

        await screen.refresh_scans(show_loading=True)

        assert service.scan_queries == 0
        assert not screen.query_one("#scans-status").render().plain.startswith("Error loading scans:")


@pytest.mark.asyncio
async def test_queued_scan_without_runtime_timestamps_is_displayed():
    service = FakeService()
    service.scans = [
        {
            "id": "SCAN:queued",
            "name": "waiting-scan",
            "status": "QUEUED",
            "created": 1_700_000_000,
            "target": {"name": "Example"},
            "preset": {"name": "baseline"},
        }
    ]
    app = ScanApp(service)
    async with app.run_test(size=(110, 45)) as pilot:
        screen = app.query_one(ScansScreen)
        await screen.load_initial_data()
        await pilot.pause()

        status = screen.query_one("#scans-status").render().plain
        assert not status.startswith("Error loading scans:")
        row = screen.query_one("#scan-table").get_row_at(0)
        assert row[0] == "waiting-scan"
        assert row[4:7] == ["-", "-", "-"]


class ScopeService:
    def __init__(self):
        self.scopes = []

    async def get_targets(self):
        class Target:
            id = "target-1"
            name = "Example"

            def model_dump(self, mode=None):
                return SCAN["target"]

        return [Target()]

    async def get_scope_report(self, **scope):
        self.scopes.append(scope)
        return await collect_report(ReportClient(), **scope)


@pytest.mark.asyncio
async def test_reports_screen_target_domain_and_pdf_export(tmp_path, monkeypatch):
    from textual.widgets import Input
    import bbot_server.cli.tui.screens.reports as reports_module

    monkeypatch.setattr(reports_module, "report_path", lambda scan: tmp_path / "summary.html")
    service = ScopeService()
    app = ScanApp(service)
    app.compose = lambda: iter([ReportsScreen(app)])
    async with app.run_test(size=(120, 45)) as pilot:
        screen = app.query_one(ReportsScreen)
        await screen.load_initial_data()
        screen.query_one("#report-target", Select).value = "target-1"
        await pilot.click("#report-view")
        await pilot.pause()
        assert service.scopes[-1]["target"]["id"] == "target-1"
        screen.query_one("#report-format", Select).value = "pdf"
        await pilot.click("#report-export")
        await pilot.pause()
        assert (tmp_path / "summary.pdf").is_file()
        screen.query_one("#report-target", Select).clear()
        assert screen.query_one("#report-target", Select).value is Select.NULL
        screen.query_one("#report-domain", Input).value = "example.org"
        await pilot.click("#report-view")
        await pilot.pause()
        assert service.scopes[-1] == {"domain": "example.org"}
