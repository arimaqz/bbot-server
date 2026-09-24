"""Run Docker-local agent processes for agent records created through BBOT Server."""

import json
import logging
import os
import signal
import subprocess
import threading


DEFAULT_AGENT_NAME = "Docker Default Agent"
DEFAULT_AGENT_DESCRIPTION = "Default agent for Docker"


def parse_json_stream(value):
    """Parse the concatenated JSON objects emitted by ``bbctl --json`` commands."""
    decoder = json.JSONDecoder()
    items = []
    position = 0
    while position < len(value):
        while position < len(value) and value[position].isspace():
            position += 1
        if position >= len(value):
            break
        item, position = decoder.raw_decode(value, position)
        items.append(item)
    return items


class AgentManager:
    """Keep one local agent process running for each disconnected agent record."""

    def __init__(self, command_runner=subprocess.run, process_factory=subprocess.Popen):
        self.command_runner = command_runner
        self.process_factory = process_factory
        self.processes = {}
        self.log = logging.getLogger("bbot_server.agent_manager")

    def _json_command(self, *arguments):
        result = self.command_runner(
            ["bbctl", *arguments],
            capture_output=True,
            text=True,
            check=True,
        )
        return parse_json_stream(result.stdout)

    def get_agents(self):
        return self._json_command("agent", "list", "--json")

    def ensure_default_agent(self):
        agents = self.get_agents()
        if any(agent["name"] == DEFAULT_AGENT_NAME for agent in agents):
            return agents
        created = self._json_command(
            "agent",
            "create",
            "--name",
            DEFAULT_AGENT_NAME,
            "--description",
            DEFAULT_AGENT_DESCRIPTION,
        )[0]
        return [*agents, created]

    def sync(self, agents):
        """Start missing local agents and stop processes whose records were deleted."""
        agent_by_id = {str(agent["id"]): agent for agent in agents}

        for agent_id, process in list(self.processes.items()):
            if agent_id not in agent_by_id:
                self.log.info("Stopping deleted local agent %s", agent_id)
                process.terminate()
                process.wait(timeout=10)
                del self.processes[agent_id]
            elif process.poll() is not None:
                self.log.warning("Local agent %s exited; restarting it", agent_id)
                del self.processes[agent_id]

        for agent_id, agent in agent_by_id.items():
            if agent_id in self.processes or agent.get("connected"):
                continue
            self.log.info("Starting local agent %s (%s)", agent["name"], agent_id)
            self.processes[agent_id] = self.process_factory(
                ["bbctl", "agent", "start", "--id", agent_id, "--name", agent["name"]]
            )

    def stop(self):
        for process in self.processes.values():
            if process.poll() is None:
                process.terminate()
        for process in self.processes.values():
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
        self.processes.clear()

    def loop(self, poll_seconds=2):
        stopping = threading.Event()

        def request_stop(signum, frame):
            stopping.set()

        signal.signal(signal.SIGTERM, request_stop)
        signal.signal(signal.SIGINT, request_stop)
        try:
            agents = self.ensure_default_agent()
            while not stopping.is_set():
                self.sync(agents)
                if stopping.wait(poll_seconds):
                    break
                try:
                    agents = self.get_agents()
                except (subprocess.SubprocessError, ValueError, json.JSONDecodeError) as exc:
                    self.log.error("Could not refresh agents: %s", exc)
        finally:
            self.stop()


def main():
    logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
    poll_seconds = float(os.getenv("BBOT_AGENT_MANAGER_POLL_SECONDS", "2"))
    AgentManager().loop(poll_seconds=poll_seconds)


if __name__ == "__main__":
    main()
