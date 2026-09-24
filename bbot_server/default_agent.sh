#!/bin/bash

set -euo pipefail

exec python -m bbot_server.modules.agents.agent_manager
