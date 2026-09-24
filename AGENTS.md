# AGENTS.md

This is the working guide for coding agents and contributors modifying this
fork of `blacklanternsecurity/bbot-server`. Read it before changing code.

## Project summary

BBOT Server is a Python 3.10+ FastAPI application that stores BBOT events and
derived assets in MongoDB, distributes work through Redis/Taskiq, exposes Python
and HTTP interfaces, and includes a Textual terminal UI (`bbctl ui`). The
project is licensed under AGPL-3.0.

This fork extends the upstream `stable` project with a more complete PC/Docker
workflow:

- TUI management for targets, presets, modules, agents, API keys, reports, and
  global display-name settings.
- Scan creation, cancellation, deletion, and report export from the TUI.
- A Docker agent manager that starts and supervises agents registered in the UI.
- HTML, PDF, CSV, and JSON target-inventory reports containing assets, asset
  ports, technologies, and all active findings.
- A host-mounted report directory controlled by `BBOT_REPORTS_DIR`.

## Important paths

- `bbot_server/applets/`: core application composition and lifecycle.
- `bbot_server/modules/`: API, CLI, model, and worker behavior by domain.
- `bbot_server/interfaces/`: matching native Python and HTTP client interfaces.
- `bbot_server/cli/tui/`: Textual application, screens, widgets, services, and
  `styles.tcss`.
- `bbot_server/reporting.py`: report collection, rendering, and export.
- `bbot_server/modules/agents/agent_manager.py`: Docker agent supervision.
- `bbot_server/default_agent.sh`: Compose agent entrypoint.
- `bbot_server/config.py`, `defaults.yml`, `defaults_docker.yml`: configuration.
- `compose.yml`: local application stack (server, worker, agent, MongoDB, Redis).
- `compose.test.yml`: disposable host-side MongoDB and Redis for tests.
- `INSTALL.md`: supported Linux and Windows Docker installation workflow.
- `tests/`: regression, API, CLI, TUI, and integration tests.
- `helm/`: Kubernetes chart; test separately with `helm_deployment_test.py`.

## Architecture and invariants

### Interfaces and data

- Public behavior should work through both `interface="python"` and
  `interface="http"`. Add or update translation/model logic when an endpoint
  changes.
- MongoDB documents use typed asset models. Preserve archived/ignored filtering
  and target/domain scope semantics.
- API timestamps may be absent for queued records. TUI formatting must safely
  render missing values instead of assuming fields such as `started_at` exist.
- Avoid unbounded queries in interactive tables. Use the existing paginated
  service helpers. Report exports intentionally collect the complete selected
  inventory.

### TUI

- Screens receive data through `cli/tui/services/data_service.py`; keep network
  and storage details out of view code.
- Preserve the built-in `bbot-dark`/`bbot-light` themes and verify layouts at
  both 80x24 and a wider terminal.
- Keep destructive actions behind confirmation dialogs.
- Module metadata must come from BBOT's installed module loader, not a hardcoded
  list.

### Agents and Compose

- `server`, `worker`, and `agent` mount the same server config. Do not embed API
  keys in Compose or source files.
- The agent manager must start each offline registered agent once, restart an
  exited process, and stop processes for deleted agents.
- Keep `BBOT_SERVER_RECONCILE_INDEXES=false` limited to secondary long-running
  Compose processes; tests and the primary server need index reconciliation.
- Changes to root `compose.yml` may need corresponding changes to
  `bbot_server/compose.yml`, deployment tests, and README instructions.

### Reports

- A report is a current target/domain inventory snapshot. A selected scan
  supplies target and timing context; findings may originate from multiple
  scans of that target.
- HTML and PDF show assets with their ports in one table. Do not add a duplicate
  standalone open-ports section.
- Never serialize a scan's full embedded preset: it can contain credentials.
  Export only the preset name and other explicitly selected safe fields.
- Escape untrusted values in HTML and ReportLab XML/Paragraph content.
- Keep HTML, PDF, CSV, and JSON exports semantically consistent. JSON/CSV may
  retain structured port rows for machine processing.
- `BBOT_REPORTS_DIR` is a host path supplied to Compose. Inside containers,
  write to `/home/bbot/bbot-reports` and use `BBOT_REPORTS_HOST_DIR` only when
  displaying the host-visible location. Never hardcode a username or home path.

## Configuration and privacy

- Configuration precedence includes environment variables using the
  `BBOT_SERVER_` prefix and `__` for nested keys.
- Never commit real `config.yml` files, `.env` files, API keys, scan databases,
  reports, targets, hostnames, personal paths, or credentials.
- Use obvious examples such as `example.org`, `evilcorp.com`, `deadbeef`, or
  `C:\Users\analyst` in tests and documentation.
- Runtime MongoDB data belongs under `mongodb/` and exported reports normally
  belong under `~/bbot-reports/`; both must remain outside version control.
- Before publishing, inspect the exact staged files and scan them for private-key
  markers, provider tokens, credentials, personal paths, and real targets.

## Development setup

Use the lockfile and `uv`:

```bash
uv sync --frozen
```

On Windows, the pinned BBOT dependency may attempt to build `blasthttp` from
source if no compatible wheel is available. Prefer the project's Linux Docker
image or CI environment rather than weakening the lockfile to work around a
local compiler/OpenSSL problem.

For a development application stack:

```bash
docker compose up -d --build
docker compose ps
docker compose logs -f server worker agent
```

Reports default to `~/bbot-reports`. Override the host directory before starting
Compose when needed:

```bash
export BBOT_REPORTS_DIR=/path/on/host
docker compose up -d
```

## Testing requirements

- Every feature needs a test.
- Every bug fix starts with a regression test that fails before the fix and
  passes afterward.
- Run the smallest relevant tests while iterating, then the broader suite.
- Tests use `pytest`, `pytest-asyncio`, MongoDB, and Redis.

Canonical host-side suite:

```bash
docker compose -f compose.test.yml up -d --wait
uv sync --frozen
uv run pytest -v tests/
docker compose -f compose.test.yml down
```

Useful focused checks:

```bash
uv run pytest -q tests/test_tui_management.py
uv run pytest -q tests/test_tui_modules.py
uv run pytest -q tests/test_tui_scan_reporting.py
uv run pytest -q tests/test_tui_targets.py
uv run pytest -q tests/test_agent_manager.py tests/test_compose_agent.py
uv run ruff check bbot_server tests
uv run ruff format --check bbot_server tests
```

`helm_deployment_test.py` is separate and requires Minikube, Helm, and kubectl.
Docker-in-Docker tests can be skipped by the test environment; do not describe a
suite as fully passing without reporting skips and environment-related blockers.

## Code style and editing

- Target Python 3.10 and the Ruff configuration in `pyproject.toml`.
- Prefer small changes that follow existing applet/module and TUI service
  patterns.
- Preserve public compatibility unless a breaking change is explicitly agreed.
- Do not edit generated caches, `.venv`, MongoDB data, report outputs, or bundled
  binary font files unless the task specifically requires it.
- Update README and tests whenever behavior, commands, configuration, Compose,
  or user-visible UI changes.

## Git and release checklist

This working copy may originate from an archive and lack `.git`. Before
publishing it, preserve upstream history:

1. Fork `blacklanternsecurity/bbot-server` on GitHub.
2. Clone the fork and add the official repository as `upstream`.
3. Base the work on the matching upstream `stable` commit.
4. Copy/apply only the intended source changes; do not copy runtime directories.
5. Review `git status`, `git diff --check`, and the complete staged diff.
6. Run secret/path scans and the relevant test suite.
7. Make focused commits with clear messages, then push a feature branch.

Before declaring the project ready, confirm:

- No real API keys, config files, databases, reports, personal paths, or targets
  are tracked.
- `.gitignore` and `.dockerignore` cover local/runtime artifacts.
- README documents all user-visible changes and portable configuration.
- Ruff checks pass.
- Focused regression tests pass and full-suite limitations are reported.
- The branch contains upstream history and intentional commits, not one
  unrelated archive import.
