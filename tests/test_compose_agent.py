from pathlib import Path

import pytest
import yaml


PROJECT_ROOT = Path(__file__).parent.parent


@pytest.mark.parametrize("compose_path", [PROJECT_ROOT / "compose.yml", PROJECT_ROOT / "bbot_server" / "compose.yml"])
def test_compose_starts_default_scan_agent(compose_path):
    compose = yaml.safe_load(compose_path.read_text())
    agent = compose["services"]["agent"]

    assert agent["command"] == ["bash", "/app/bbot_server/default_agent.sh"]
    assert agent["depends_on"]["server"]["condition"] == "service_healthy"


@pytest.mark.parametrize("compose_path", [PROJECT_ROOT / "compose.yml", PROJECT_ROOT / "bbot_server" / "compose.yml"])
def test_compose_exports_reports_to_the_host(compose_path):
    compose = yaml.safe_load(compose_path.read_text())
    expected_mount = "${BBOT_REPORTS_DIR:-~/bbot-reports}:/home/bbot/bbot-reports"

    for service_name in ("server", "worker", "agent"):
        assert expected_mount in compose["services"][service_name]["volumes"]
    assert "BBOT_REPORTS_HOST_DIR=${BBOT_REPORTS_DIR:-~/bbot-reports}" in compose["services"]["server"][
        "environment"
    ]


def test_image_prepares_writable_bbot_config_directory():
    dockerfile = (PROJECT_ROOT / "Dockerfile").read_text()

    assert "p7zip-full" in dockerfile
    assert "mkdir -p /home/bbot/.config/bbot" in dockerfile
    assert "chown -R bbot:bbot /home/bbot" in dockerfile


def test_default_agent_keeps_the_same_identity_across_restarts():
    launcher = (PROJECT_ROOT / "bbot_server" / "default_agent.sh").read_text()

    assert "python -m bbot_server.modules.agents.agent_manager" in launcher
    assert "bbctl agent delete" not in launcher
