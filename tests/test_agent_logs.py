from bbot_server.modules.agents.log_buffer import AgentLogBuffer, dependency_banner, dependency_phase


def test_dependency_phase_recognizes_install_progress_and_failure():
    assert dependency_phase("Installing module dependencies. Please be patient") == "installing"
    assert dependency_phase('Installing dependencies for module "nuclei"') == "installing"
    assert dependency_phase('Setup succeeded for module "portscan"') == "progress"
    assert dependency_phase("Loaded 4/4 scan modules (portscan,http)") == "ready"
    assert dependency_phase('Setup failed for module "portscan"') == "failed"
    assert dependency_phase("Scan queued") is None


def test_log_buffer_keeps_recent_lines_and_dependency_banner():
    buffer = AgentLogBuffer(maxlen=3)
    buffer.append({"timestamp": 10, "level": "INFO", "logger": "bbot", "message": "agent connected"})
    buffer.append(
        {
            "timestamp": 20,
            "level": "INFO",
            "logger": "bbot.depsinstaller",
            "message": "Installing module dependencies. Please be patient",
            "agent_name": "runner",
            "scan_name": "scan-one",
        }
    )
    buffer.append(
        {
            "timestamp": 21,
            "level": "INFO",
            "logger": "bbot.depsinstaller",
            "message": 'Installing dependencies for module "nuclei"',
            "agent_name": "runner",
            "scan_name": "scan-one",
        }
    )
    overflow = buffer.append({"timestamp": 30, "level": "INFO", "logger": "bbot", "message": "later"})

    recent = buffer.recent(after=0)
    assert [entry["message"] for entry in recent][0].startswith("Installing module")
    assert recent[0]["dependency"] is True
    assert overflow["id"] == 4
    assert buffer.recent(after=overflow["id"]) == []
    assert "Installing dependencies" in dependency_banner(buffer.recent(), now=21)


def test_dependency_banner_hides_finished_installs():
    entries = [
        {
            "timestamp": 10,
            "phase": "ready",
            "message": "Loaded 2/2 scan modules",
            "agent_name": "runner",
            "scan_name": "scan-one",
        }
    ]
    assert dependency_banner(entries, now=10) is not None
    assert dependency_banner(entries, now=30) is None
