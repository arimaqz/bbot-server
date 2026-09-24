import json

from bbot_server.modules.agents.agent_manager import AgentManager, parse_json_stream


class DummyProcess:
    def __init__(self, returncode=None):
        self.returncode = returncode
        self.terminated = False

    def poll(self):
        return self.returncode

    def terminate(self):
        self.terminated = True

    def wait(self, timeout=None):
        self.returncode = 0


def test_parse_json_stream_accepts_bbctl_concatenated_objects():
    assert parse_json_stream('{"id":"one"}{"id":"two"}') == [{"id": "one"}, {"id": "two"}]


def test_manager_starts_each_offline_agent_once_and_stops_deleted_agents():
    commands = []
    processes = []

    def popen(command):
        commands.append(command)
        process = DummyProcess()
        processes.append(process)
        return process

    manager = AgentManager(process_factory=popen)
    agents = [
        {"id": "local-1", "name": "Local One", "connected": False},
        {"id": "remote-1", "name": "Remote One", "connected": True},
    ]

    manager.sync(agents)
    manager.sync(agents)

    assert commands == [["bbctl", "agent", "start", "--id", "local-1", "--name", "Local One"]]

    manager.sync([])
    assert processes[0].terminated is True


def test_manager_restarts_an_agent_process_that_exited():
    processes = [DummyProcess(returncode=1), DummyProcess()]
    manager = AgentManager(process_factory=lambda command: processes.pop(0))
    agent = [{"id": "local-1", "name": "Local One", "connected": False}]

    manager.sync(agent)
    manager.sync(agent)

    assert manager.processes["local-1"].poll() is None


def test_manager_creates_the_default_agent_only_when_missing():
    calls = []

    def runner(command, **kwargs):
        calls.append(command)
        if command[1:4] == ["agent", "list", "--json"]:
            output = '{"id":"user-1","name":"User Agent","connected":false}'
        else:
            output = json.dumps({"id": "default-1", "name": "Docker Default Agent", "connected": False})
        return type("Result", (), {"stdout": output})()

    manager = AgentManager(command_runner=runner)
    agents = manager.ensure_default_agent()

    assert [agent["name"] for agent in agents] == ["User Agent", "Docker Default Agent"]
    assert calls[-1][1:3] == ["agent", "create"]
