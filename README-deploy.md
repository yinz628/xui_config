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

## Start Web Console

```bash
cd /opt/xui-config
cp .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(32))"
# paste the generated secret into WEB_SESSION_SECRET and set WEB_ADMIN_PASSWORD
docker compose up -d web
```

Open:

```text
http://<server-ip>:8000/login
```

## Check Results

```bash
ls -lah /opt/xui-config/output
ls -lah /opt/xui-config/data/state
sed -n '1,80p' /opt/xui-config/output/config.generated.report.json
```

## Check Web

```bash
cd /opt/xui-config
docker compose ps
curl -I http://127.0.0.1:8000/login
```

## Smoke

From your admin machine:

```powershell
$env:SMOKE_SSH_HOST='192.168.2.195'
$env:SMOKE_SSH_USER='root'
$env:SMOKE_REMOTE_PATH='/opt/xui-config'
.\scripts\test-smoke-connection.ps1
```
