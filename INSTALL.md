# BBOT Server installation guide

This guide installs this fork from source with Docker Compose. It covers Linux
with Docker Engine and Windows with Docker Desktop using Linux containers.

Docker runs the API server, worker, scan agents, MongoDB, and Redis. Reports are
written directly to a folder on the host. No Python installation is required on
the host for this Docker workflow.

> [!IMPORTANT]
> Use BBOT only against systems you own or are explicitly authorized to test.

## What the installation creates

- BBOT Server API and documentation at <http://127.0.0.1:8807/v1/docs>.
- The terminal UI, launched with `docker compose exec server bbctl ui`.
- MongoDB data in the repository's local `mongodb/` directory.
- A private configuration file outside the repository.
- Exported HTML, PDF, CSV, and JSON reports in a host folder you control.

The API listens on `127.0.0.1` by default and is not exposed to other computers.

## Linux installation with Docker Engine

### 1. Install prerequisites

Install Git, Docker Engine, Buildx, and the Docker Compose plugin. Use Docker's
official instructions for your distribution:

- [Install Docker Engine](https://docs.docker.com/engine/install/)
- [Install the Docker Compose plugin](https://docs.docker.com/compose/install/linux/)

Verify the installation:

```bash
git --version
docker --version
docker compose version
docker run --rm hello-world
```

If Docker requires `sudo`, either use `sudo` for the Docker commands below or
complete Docker's Linux post-installation steps. Do not loosen permissions on
the Docker socket.

### 2. Clone this fork

Replace `<YOUR-GITHUB-USER>` with the account that owns the fork:

```bash
git clone --branch pc-ui https://github.com/<YOUR-GITHUB-USER>/bbot-server.git
cd bbot-server
```

### 3. Create the private configuration and report directory

The configuration must exist as a file before Compose starts. The following
commands create a new API key and keep it outside the repository:

```bash
mkdir -p "$HOME/.config/bbot_server" "$HOME/bbot-reports"
BBOT_CONFIG="$HOME/.config/bbot_server/config.yml"
API_KEY="$(cat /proc/sys/kernel/random/uuid)"
printf 'api_keys:\n  - %s\n' "$API_KEY" > "$BBOT_CONFIG"
chmod 600 "$BBOT_CONFIG"
printf 'BBOT_SERVER_CONFIG=%s\nBBOT_REPORTS_DIR=%s\n' \
  "$BBOT_CONFIG" "$HOME/bbot-reports" > .env
```

The repository ignores `.env`, the configuration file, database files, and
reports. Do not commit or share the generated API key.

If you already have a BBOT Server configuration, do not overwrite it. Put its
absolute path in `BBOT_SERVER_CONFIG` in `.env` instead.

### 4. Build and start BBOT Server

```bash
docker compose config
docker compose up -d --build
docker compose ps
```

The first build downloads the base images and dependencies and can take several
minutes. Wait until the `server` service reports `healthy`. To follow startup:

```bash
docker compose logs -f server worker agent
```

Press `Ctrl+C` to stop following logs; this does not stop the services.

### 5. Verify and open the UI

Open <http://127.0.0.1:8807/v1/docs> to verify the API. Launch the terminal UI
from the repository directory:

```bash
docker compose exec server bbctl ui
```

Use the footer shortcuts or click the screen names. Press `q` to leave the UI.
The Docker services continue running after the UI exits.

## Windows installation with Docker Desktop

### 1. Install prerequisites

Install:

1. [Git for Windows](https://git-scm.com/download/win)
2. [Docker Desktop for Windows](https://docs.docker.com/desktop/setup/install/windows-install/)

Enable Docker Desktop's WSL 2 backend and use **Linux containers**. Start Docker
Desktop, wait until its engine is running, and then open PowerShell. Administrator
PowerShell is not normally required after Docker Desktop is installed.

Verify the installation:

```powershell
git --version
docker --version
docker compose version
docker run --rm hello-world
```

### 2. Clone this fork

Replace `<YOUR-GITHUB-USER>` with the account that owns the fork:

```powershell
git clone --branch pc-ui https://github.com/<YOUR-GITHUB-USER>/bbot-server.git
Set-Location bbot-server
```

Keep the repository in a local Windows folder, not a network share. Docker
Desktop may ask for permission to share the drive or folder; allow access to
this repository and the two host paths created below.

### 3. Create the private configuration and report directory

Run these commands in PowerShell from the repository root:

```powershell
$ConfigDir = Join-Path $env:USERPROFILE ".config\bbot_server"
$ConfigFile = Join-Path $ConfigDir "config.yml"
$ReportsDir = Join-Path $env:USERPROFILE "bbot-reports"
New-Item -ItemType Directory -Force -Path $ConfigDir, $ReportsDir | Out-Null
$ApiKey = [guid]::NewGuid().ToString()
@("api_keys:", "  - $ApiKey") | Set-Content -Encoding ascii $ConfigFile
$ComposeConfig = $ConfigFile.Replace("\", "/")
$ComposeReports = $ReportsDir.Replace("\", "/")
@(
  "BBOT_SERVER_CONFIG=$ComposeConfig"
  "BBOT_REPORTS_DIR=$ComposeReports"
) | Set-Content -Encoding ascii .env
```

Creating the file first is important. If the bind-mount source does not exist,
Docker may create a directory where BBOT expects a YAML file.

The repository ignores `.env`, the configuration file, database files, and
reports. Do not commit or share the generated API key. If a configuration
already exists, keep it and only write its path to `.env`.

### 4. Build and start BBOT Server

```powershell
docker compose config
docker compose up -d --build
docker compose ps
```

The first build can take several minutes. Wait until the `server` service is
`healthy`. Follow startup logs if necessary:

```powershell
docker compose logs -f server worker agent
```

Press `Ctrl+C` to stop following logs without stopping the services.

### 5. Verify and open the UI

Open <http://127.0.0.1:8807/v1/docs> in a browser. Launch the terminal UI in the
same PowerShell window:

```powershell
docker compose exec server bbctl ui
```

Use Windows Terminal for the best colors, mouse support, and resizing. Maximize
the terminal if tables or buttons appear crowded. Press `q` to leave the UI.

## First-use workflow

After opening the UI:

1. Open **Settings** to set the global BBOT display name used by the UI and new
   reports.
2. Open **Modules** to review the modules available in the installed BBOT build.
3. Create a **Target** containing only authorized seeds.
4. Create a **Preset**. `modules: []` is valid YAML and means no modules are
   explicitly selected. Add module names under `modules` when needed.
5. Open **Agents** and confirm an agent becomes online. Agents created in the UI
   are supervised by the Compose agent service.
6. Create and start a scan from **Scans**.
7. Export reports from **Reports** or the scan screen.

Reports appear immediately in the host directory configured by
`BBOT_REPORTS_DIR`—`~/bbot-reports` on Linux or
`%USERPROFILE%\bbot-reports` on Windows in the examples above. Reports include
discovered assets and, when present, their ports, technologies, and active
findings. Ports are shown with their assets instead of in a duplicate section.
Reports exported from a scan additionally include scan-scoped event results
grouped by producing module. Configured modules with no stored events remain
visible as `no observed results`; that label does not prove whether a module
completed, was skipped, or failed before emitting an event. HTML module sections
are linked, collapsible, and searchable. Scope and methodology includes a
sanitized preset definition with credential-like values replaced by
`[REDACTED]`.

## Routine commands

Run these commands from the repository root.

| Task | Command |
| --- | --- |
| Show service status | `docker compose ps` |
| Open the TUI | `docker compose exec server bbctl ui` |
| Follow all logs | `docker compose logs -f` |
| Follow server logs | `docker compose logs -f server` |
| Restart the stack | `docker compose restart` |
| Stop containers | `docker compose stop` |
| Start stopped containers | `docker compose start` |
| Stop and remove containers | `docker compose down` |
| Rebuild after source changes | `docker compose up -d --build` |

`docker compose down` does not delete the bind-mounted `mongodb/` directory or
the host report directory. Treat both as potentially sensitive scan data.

## Update this fork

Commit or stash any local edits first, then update and rebuild:

### Linux

```bash
git switch pc-ui
git pull --ff-only
docker compose up -d --build
docker compose ps
```

### Windows PowerShell

```powershell
git switch pc-ui
git pull --ff-only
docker compose up -d --build
docker compose ps
```

Do not delete or recreate the configuration file during an update; it contains
the API key used by the server and clients.

## Change host paths or listening address

Edit `.env`, then recreate the services with `docker compose up -d`.

```dotenv
BBOT_SERVER_CONFIG=/absolute/path/to/config.yml
BBOT_REPORTS_DIR=/absolute/path/to/bbot-reports
BBOT_LISTEN_ADDRESS=127.0.0.1
BBOT_PORT=8807
```

Use forward slashes in Windows paths stored in `.env`, for example
`C:/Users/analyst/bbot-reports`. Keep `BBOT_LISTEN_ADDRESS=127.0.0.1` unless
remote access is intentionally required and protected by authentication and a
firewall.

## Troubleshooting

### The server is unhealthy or repeatedly restarts

```bash
docker compose ps
docker compose logs --tail=200 server
docker compose config
```

Check that `BBOT_SERVER_CONFIG` points to a file, not a directory, and that the
YAML contains at least one valid UUID under `api_keys`.

### The agent remains offline

```bash
docker compose ps agent worker redis
docker compose logs --tail=200 agent worker redis
docker compose restart agent worker
```

Confirm the server is healthy and that all services use the same mounted
configuration file. Then reopen the Agents screen.

### Reports mention a container path or do not appear on the host

Check the resolved mount and environment:

```bash
docker compose config
docker compose exec server printenv BBOT_REPORTS_HOST_DIR
docker compose exec server sh -lc 'ls -la /home/bbot/bbot-reports'
```

The first command should show the intended host directory mapped to
`/home/bbot/bbot-reports`. Recreate the stack after changing `.env`.

### Port 8807 is already in use

Set a different host port in `.env`, for example `BBOT_PORT=8810`, and run:

```bash
docker compose up -d
```

The API will then be available at `http://127.0.0.1:8810/v1/docs`. Internal
container communication remains on port 8807.

### Resetting local data

Stopping or rebuilding containers does not require deleting data. The
`mongodb/` directory contains the local BBOT database. Back it up if needed.
Only remove it when you intentionally want to permanently erase all stored
targets, scans, assets, findings, presets, agents, and settings.
