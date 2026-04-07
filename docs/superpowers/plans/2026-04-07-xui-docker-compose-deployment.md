# X-UI Generator Docker Compose Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Docker Compose deployment assets so the generator can run independently on a VPS, persist cache/state/output, and be validated by external smoke scripts.

**Architecture:** Keep the generator app logic unchanged where possible and add a thin deployment layer around it: container image, Compose service, VPS-oriented config examples, and smoke scripts aware of the new `config/data/output` layout. Lock the deployment contract with lightweight YAML/document/script tests before editing the deployment assets.

**Tech Stack:** Python 3.10, PyYAML, pytest, Docker Compose, Paramiko, PowerShell

**Workspace note:** `F:\x-ui` is already a Git repository on `main`. This plan assumes implementation happens in the current repo and uses small commits per task.

---

## File Structure

### Existing files to modify

- `F:\x-ui\scripts\test_smoke_connection.py`
  Responsibility: SSH smoke probe; update it to validate the Compose deployment layout instead of the old `config.yaml/data` layout.
- `F:\x-ui\scripts\test-smoke-connection.ps1`
  Responsibility: wrapper for the Python smoke script; update default remote path and keep argument passthrough aligned.

### Existing files to keep unchanged

- `F:\x-ui\generate_xray_config.py`
  Responsibility: container entrypoint command target.
- `F:\x-ui\xui_port_pool_generator\*`
  Responsibility: generator runtime logic already implemented.

### New deployment files

- `F:\x-ui\Dockerfile`
  Responsibility: build the generator image.
- `F:\x-ui\docker-compose.yml`
  Responsibility: define the `generator` service and host mounts.
- `F:\x-ui\requirements.txt`
  Responsibility: Python runtime dependencies required by generator and repo-hosted smoke script.
- `F:\x-ui\.dockerignore`
  Responsibility: keep build context small and avoid shipping cache/state/generated artifacts.
- `F:\x-ui\.env.example`
  Responsibility: sample environment variables for Compose and smoke execution.
- `F:\x-ui\README-deploy.md`
  Responsibility: deployment runbook for VPS setup and generator execution.
- `F:\x-ui\config\mapping.vps.example.yaml`
  Responsibility: VPS-oriented example mapping using container paths.
- `F:\x-ui\config\config.json.example`
  Responsibility: example template file copied from the existing root `config.json`.

### New test files

- `F:\x-ui\tests\test_deployment_contract.py`
  Responsibility: validate Compose mounts/command and VPS mapping example paths.
- `F:\x-ui\tests\test_smoke_script.py`
  Responsibility: validate smoke script defaults and remote summary command contents.
- `F:\x-ui\tests\test_deployment_docs.py`
  Responsibility: validate deployment docs and env example mention the required commands and variables.

## Task 1: Add Docker Compose Contract Files

**Files:**
- Create: `F:\x-ui\tests\test_deployment_contract.py`
- Create: `F:\x-ui\Dockerfile`
- Create: `F:\x-ui\docker-compose.yml`
- Create: `F:\x-ui\requirements.txt`
- Create: `F:\x-ui\.dockerignore`
- Create: `F:\x-ui\config\mapping.vps.example.yaml`
- Create: `F:\x-ui\config\config.json.example`

- [ ] **Step 1: Write the failing deployment contract tests**

```python
import json
from pathlib import Path

import yaml


ROOT = Path(r"F:\x-ui")


def test_compose_generator_service_uses_expected_mounts_and_command() -> None:
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    service = compose["services"]["generator"]

    assert service["working_dir"] == "/app"
    assert service["command"] == [
        "python",
        "generate_xray_config.py",
        "--mapping",
        "/app/config/mapping.yaml",
        "--template",
        "/app/config/config.json",
    ]
    assert "./config:/app/config" in service["volumes"]
    assert "./data/cache:/app/cache" in service["volumes"]
    assert "./data/state:/app/state" in service["volumes"]
    assert "./output:/app/output" in service["volumes"]


def test_vps_mapping_example_uses_container_runtime_paths() -> None:
    mapping = yaml.safe_load(
        (ROOT / "config" / "mapping.vps.example.yaml").read_text(encoding="utf-8")
    )

    assert mapping["runtime"]["cache_dir"] == "/app/cache"
    assert mapping["runtime"]["state_path"] == "/app/state/port_bindings.json"
    assert mapping["runtime"]["output_path"] == "/app/output/config.generated.json"
    assert mapping["runtime"]["report_path"] == "/app/output/config.generated.report.json"
```

- [ ] **Step 2: Run the deployment contract tests to verify they fail**

Run:

```powershell
python -m pytest F:\x-ui\tests\test_deployment_contract.py -q
```

Expected: FAIL with `FileNotFoundError` because `docker-compose.yml` and `config/mapping.vps.example.yaml` do not exist yet.

- [ ] **Step 3: Create the Docker/Compose assets and VPS config examples**

`F:\x-ui\requirements.txt`

```text
PyYAML==6.0.2
paramiko==3.5.1
```

`F:\x-ui\.dockerignore`

```text
.git
.pytest_cache
__pycache__
cache
state
output
tests
docs
310config86-106.yaml
RH5SFz15rrci.yaml
config.generated.json
config.generated.report.json
```

`F:\x-ui\Dockerfile`

```dockerfile
FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY generate_xray_config.py /app/generate_xray_config.py
COPY xui_port_pool_generator /app/xui_port_pool_generator

CMD ["python", "generate_xray_config.py", "--mapping", "/app/config/mapping.yaml", "--template", "/app/config/config.json"]
```

`F:\x-ui\docker-compose.yml`

```yaml
services:
  generator:
    build: .
    container_name: xui-config-generator
    working_dir: /app
    command:
      - python
      - generate_xray_config.py
      - --mapping
      - /app/config/mapping.yaml
      - --template
      - /app/config/config.json
    environment:
      PYTHONUNBUFFERED: "1"
    volumes:
      - ./config:/app/config
      - ./data/cache:/app/cache
      - ./data/state:/app/state
      - ./output:/app/output
```

`F:\x-ui\config\mapping.vps.example.yaml`

```yaml
version: 1
sources:
  - id: airport_a
    url: https://example.com/sub-a
    enabled: true
    format: clash
groups:
  - name: tg_hk
    filter: '(?i)(hk|hong kong|香港)'
    exclude: '(?i)(iepl|iplc)'
    port_range:
      start: 20000
      end: 20049
runtime:
  cache_dir: /app/cache
  state_path: /app/state/port_bindings.json
  output_path: /app/output/config.generated.json
  report_path: /app/output/config.generated.report.json
  output_mode: config_json
```

`F:\x-ui\config\config.json.example`

```json
{
  "copy_from": "../config.json",
  "note": "Replace this file with the VPS template copied from the real root config.json content."
}
```

- [ ] **Step 4: Run the deployment contract tests again**

Run:

```powershell
python -m pytest F:\x-ui\tests\test_deployment_contract.py -q
```

Expected: PASS with `2 passed`.

- [ ] **Step 5: Commit the deployment contract files**

Run:

```powershell
git add F:\x-ui\tests\test_deployment_contract.py F:\x-ui\Dockerfile F:\x-ui\docker-compose.yml F:\x-ui\requirements.txt F:\x-ui\.dockerignore F:\x-ui\config\mapping.vps.example.yaml F:\x-ui\config\config.json.example
git commit -m "feat(deploy): 新增 Compose 部署骨架"
```

Expected: one commit created.

## Task 2: Update Smoke Scripts for the Compose Layout

**Files:**
- Create: `F:\x-ui\tests\test_smoke_script.py`
- Modify: `F:\x-ui\scripts\test_smoke_connection.py`
- Modify: `F:\x-ui\scripts\test-smoke-connection.ps1`

- [ ] **Step 1: Write the failing smoke script tests**

```python
from pathlib import Path


ROOT = Path(r"F:\x-ui")


def test_smoke_defaults_target_compose_deployment_root() -> None:
    text = (ROOT / "scripts" / "test_smoke_connection.py").read_text(encoding="utf-8")

    assert 'DEFAULT_REMOTE_PATH = "/opt/xui-config"' in text


def test_build_summary_command_checks_new_layout_and_runs_generator() -> None:
    text = (ROOT / "scripts" / "test_smoke_connection.py").read_text(encoding="utf-8")

    assert "docker compose run --rm generator" in text
    assert "config/mapping.yaml" in text
    assert "config/config.json" in text
    assert "data/state/port_bindings.json" in text
    assert "output/config.generated.report.json" in text
```

- [ ] **Step 2: Run the smoke script tests to verify they fail**

Run:

```powershell
python -m pytest F:\x-ui\tests\test_smoke_script.py -q
```

Expected: FAIL because the current smoke script still points to the old remote path and old layout checks.

- [ ] **Step 3: Refactor the smoke scripts to match the new deployment layout**

`F:\x-ui\scripts\test_smoke_connection.py`

```python
DEFAULT_REMOTE_PATH = "/opt/xui-config"


def detect_app_root(client: paramiko.SSHClient, remote_path: str, timeout: int) -> str:
    candidates = [remote_path, f"{remote_path}/app"]
    for candidate in candidates:
        compose_file = shlex.quote(f"{candidate}/docker-compose.yml")
        result = run_remote(client, f"test -f {compose_file}", timeout)
        if result.code == 0:
            return candidate
    raise RuntimeError(
        f"docker-compose.yml not found under {remote_path} or {remote_path}/app",
    )


def build_summary_command(app_root: str) -> str:
    quoted = shlex.quote(app_root)
    return f"""set -e
cd {quoted}
echo "APP_ROOT=$PWD"
echo "HAS_DOCKER_COMPOSE=$(test -f docker-compose.yml && echo 1 || echo 0)"
echo "HAS_MAPPING=$(test -f config/mapping.yaml && echo 1 || echo 0)"
echo "HAS_TEMPLATE=$(test -f config/config.json && echo 1 || echo 0)"
echo "HAS_STATE=$(test -f data/state/port_bindings.json && echo 1 || echo 0)"
echo "HAS_REPORT=$(test -f output/config.generated.report.json && echo 1 || echo 0)"
echo "RUN_GENERATOR_BEGIN"
docker compose run --rm generator 2>&1
echo "RUN_GENERATOR_END"
echo "DIRECTORY_LISTING_BEGIN"
ls -la | sed -n '1,20p'
echo "DIRECTORY_LISTING_END"
echo "REPORT_HEAD_BEGIN"
sed -n '1,80p' output/config.generated.report.json 2>/dev/null || true
echo "REPORT_HEAD_END"
echo "DOCKER_COMPOSE_PS_BEGIN"
docker compose ps 2>&1 || true
echo "DOCKER_COMPOSE_PS_END"
"""
```

`F:\x-ui\scripts\test-smoke-connection.ps1`

```powershell
param(
    [string]$TargetHost = $(if ($env:SMOKE_SSH_HOST) { $env:SMOKE_SSH_HOST } else { '192.168.2.195' }),
    [int]$Port = $(if ($env:SMOKE_SSH_PORT) { [int]$env:SMOKE_SSH_PORT } else { 22 }),
    [string]$User = $(if ($env:SMOKE_SSH_USER) { $env:SMOKE_SSH_USER } else { 'root' }),
    [string]$RemotePath = $(if ($env:SMOKE_REMOTE_PATH) { $env:SMOKE_REMOTE_PATH } else { '/opt/xui-config' }),
    [string]$Password = $env:SMOKE_SSH_PASSWORD
)
```

- [ ] **Step 4: Run the smoke script tests again**

Run:

```powershell
python -m pytest F:\x-ui\tests\test_smoke_script.py -q
```

Expected: PASS with `2 passed`.

- [ ] **Step 5: Commit the smoke script updates**

Run:

```powershell
git add F:\x-ui\tests\test_smoke_script.py F:\x-ui\scripts\test_smoke_connection.py F:\x-ui\scripts\test-smoke-connection.ps1
git commit -m "feat(deploy): 适配 VPS smoke 检查"
```

Expected: one commit created.

## Task 3: Add Deployment Runbook and Environment Example

**Files:**
- Create: `F:\x-ui\tests\test_deployment_docs.py`
- Create: `F:\x-ui\.env.example`
- Create: `F:\x-ui\README-deploy.md`

- [ ] **Step 1: Write the failing deployment docs test**

```python
from pathlib import Path


ROOT = Path(r"F:\x-ui")


def test_deploy_readme_and_env_example_cover_required_commands() -> None:
    env_text = (ROOT / ".env.example").read_text(encoding="utf-8")
    readme_text = (ROOT / "README-deploy.md").read_text(encoding="utf-8")

    assert "SMOKE_SSH_HOST" in env_text
    assert "SMOKE_SSH_USER" in env_text
    assert "SMOKE_REMOTE_PATH" in env_text
    assert "docker compose build" in readme_text
    assert "docker compose run --rm generator" in readme_text
    assert "/opt/xui-config/output" in readme_text
```

- [ ] **Step 2: Run the docs test to verify it fails**

Run:

```powershell
python -m pytest F:\x-ui\tests\test_deployment_docs.py -q
```

Expected: FAIL with `FileNotFoundError` because `.env.example` and `README-deploy.md` do not exist yet.

- [ ] **Step 3: Write the environment example and deployment runbook**

`F:\x-ui\.env.example`

```text
COMPOSE_PROJECT_NAME=xui-config
SMOKE_SSH_HOST=192.168.2.195
SMOKE_SSH_PORT=22
SMOKE_SSH_USER=root
SMOKE_REMOTE_PATH=/opt/xui-config
```

`F:\x-ui\README-deploy.md`

````markdown
# X-UI Generator VPS Deployment

## Layout

~~~text
/opt/xui-config/
  config/
  data/cache/
  data/state/
  output/
~~~

## First-Time Setup

~~~bash
mkdir -p /opt/xui-config/config
mkdir -p /opt/xui-config/data/cache
mkdir -p /opt/xui-config/data/state
mkdir -p /opt/xui-config/output
~~~

Copy:

- `config/mapping.vps.example.yaml` -> `/opt/xui-config/config/mapping.yaml`
- real template JSON -> `/opt/xui-config/config/config.json`

## Build

~~~bash
cd /opt/xui-config
docker compose build
~~~

## Run Once

~~~bash
cd /opt/xui-config
docker compose run --rm generator
~~~

## Check Results

~~~bash
ls -lah /opt/xui-config/output
ls -lah /opt/xui-config/data/state
sed -n '1,80p' /opt/xui-config/output/config.generated.report.json
~~~

## Smoke

From your admin machine:

~~~powershell
$env:SMOKE_SSH_HOST='192.168.2.195'
$env:SMOKE_SSH_USER='root'
$env:SMOKE_REMOTE_PATH='/opt/xui-config'
.\scripts\test-smoke-connection.ps1
~~~
````

- [ ] **Step 4: Run the docs test again**

Run:

```powershell
python -m pytest F:\x-ui\tests\test_deployment_docs.py -q
```

Expected: PASS with `1 passed`.

- [ ] **Step 5: Commit the docs files**

Run:

```powershell
git add F:\x-ui\.env.example F:\x-ui\README-deploy.md F:\x-ui\tests\test_deployment_docs.py
git commit -m "docs(deploy): 补充 VPS 部署说明"
```

Expected: one commit created.

## Task 4: Run Local Verification and Compose Validation

**Files:**
- Verify: `F:\x-ui\Dockerfile`
- Verify: `F:\x-ui\docker-compose.yml`
- Verify: `F:\x-ui\scripts\test_smoke_connection.py`
- Verify: `F:\x-ui\README-deploy.md`

- [ ] **Step 1: Run the new deployment-focused test suite**

Run:

```powershell
python -m pytest F:\x-ui\tests\test_deployment_contract.py F:\x-ui\tests\test_smoke_script.py F:\x-ui\tests\test_deployment_docs.py -q
```

Expected: PASS with all tests green.

- [ ] **Step 2: Run the full project regression suite**

Run:

```powershell
python -m pytest F:\x-ui\tests\test_mapping_loader.py F:\x-ui\tests\test_sources_and_grouping.py F:\x-ui\tests\test_allocator.py F:\x-ui\tests\test_pipeline.py F:\x-ui\tests\test_deployment_contract.py F:\x-ui\tests\test_smoke_script.py F:\x-ui\tests\test_deployment_docs.py -q
```

Expected: PASS with all tests green.

- [ ] **Step 3: Install the deployment dependencies in the local Python environment**

Run:

```powershell
python -m pip install -r F:\x-ui\requirements.txt
```

Expected: `PyYAML` and `paramiko` are installed or already satisfied.

- [ ] **Step 4: Verify the smoke script CLI and Compose file parse**

Run:

```powershell
python F:\x-ui\scripts\test_smoke_connection.py --help
docker compose -f F:\x-ui\docker-compose.yml config
```

Expected:

- the Python help command exits `0` and prints usage
- `docker compose ... config` exits `0` and prints the normalized Compose configuration

- [ ] **Step 5: Review the deployment artifact set**

Run:

```powershell
Get-ChildItem F:\x-ui\Dockerfile, F:\x-ui\docker-compose.yml, F:\x-ui\requirements.txt, F:\x-ui\.dockerignore, F:\x-ui\.env.example, F:\x-ui\README-deploy.md, F:\x-ui\config\mapping.vps.example.yaml, F:\x-ui\config\config.json.example
```

Expected: each file exists and is listed exactly once.

- [ ] **Step 6: Commit the final deployment verification**

Run:

```powershell
git add F:\x-ui\Dockerfile F:\x-ui\docker-compose.yml F:\x-ui\requirements.txt F:\x-ui\.dockerignore F:\x-ui\.env.example F:\x-ui\README-deploy.md F:\x-ui\config\mapping.vps.example.yaml F:\x-ui\config\config.json.example F:\x-ui\scripts\test_smoke_connection.py F:\x-ui\scripts\test-smoke-connection.ps1 F:\x-ui\tests\test_deployment_contract.py F:\x-ui\tests\test_smoke_script.py F:\x-ui\tests\test_deployment_docs.py
git commit -m "feat(deploy): 完成 Compose 部署资产"
```

Expected: one commit created.

## Self-Review

### Spec coverage

- Compose independent generator deployment: Task 1
- VPS layout and container path contract: Task 1
- smoke script positioning and remote checks: Task 2
- deployment runbook and `.env.example`: Task 3
- local verification and Compose validation: Task 4

### Placeholder scan

- This plan contains no unresolved placeholder markers.
- Each task includes exact files, commands, and expected results.

### Type consistency

- `docker-compose.yml` consistently uses `/app/config`, `/app/cache`, `/app/state`, and `/app/output`.
- `DEFAULT_REMOTE_PATH` is aligned between the Python smoke script, the PowerShell wrapper, and `.env.example`.
