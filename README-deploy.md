# X-UI Generator VPS Deployment

## Layout

```text
/opt/xui-config/
  config/
  data/cache/
  data/state/
  output/
```

## First-Time Setup

```bash
mkdir -p /opt/xui-config/config
mkdir -p /opt/xui-config/data/cache
mkdir -p /opt/xui-config/data/state
mkdir -p /opt/xui-config/output
```

Copy:

- `config/mapping.vps.example.yaml` -> `/opt/xui-config/config/mapping.yaml`
- real template JSON -> `/opt/xui-config/config/config.json`

## Build

```bash
cd /opt/xui-config
docker compose build
```

## Run Once

```bash
cd /opt/xui-config
docker compose run --rm generator
```

## Check Results

```bash
ls -lah /opt/xui-config/output
ls -lah /opt/xui-config/data/state
sed -n '1,80p' /opt/xui-config/output/config.generated.report.json
```

## Smoke

From your admin machine:

```powershell
$env:SMOKE_SSH_HOST='192.168.2.195'
$env:SMOKE_SSH_USER='root'
$env:SMOKE_REMOTE_PATH='/opt/xui-config'
.\scripts\test-smoke-connection.ps1
```
