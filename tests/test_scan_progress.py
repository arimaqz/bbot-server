"""Scan progress parsing for TUI detail pane."""

from bbot_server.cli.tui.utils.scan_progress import build_scan_progress, module_states_from_logs


def test_module_states_from_agent_log_messages():
    modules = ["nmap", "httpx"]
    entries = [
        {"message": 'Installing dependencies for module "nmap"', "phase": "installing"},
        {"message": 'Setup succeeded for module "nmap"', "phase": "progress"},
    ]
    states = module_states_from_logs(entries, modules)
    assert states["nmap"] == "done"
    assert states["httpx"] == "pending"


def test_build_scan_progress_marks_installing_stage():
    scan = {
        "status": "STARTING",
        "preset": {"preset": {"modules": ["nmap"]}},
    }
    entries = [{"message": 'Installing dependencies for module "nmap"', "phase": "installing"}]
    progress = build_scan_progress(scan, entries)
    assert progress["stage"] == "installing_deps"
    assert progress["installing"] == ["nmap"]
