# Native Deployment

This deploys the app directly on a Debian-based VPS with systemd, Caddy, UFW,
fail2ban, Grafana, Prometheus, and node_exporter.

The app runs through `deploy/native/supervisor.py`. Systemd keeps the supervisor
alive; the supervisor keeps FastAPI alive, periodically pulls the configured Git
branch, runs `uv sync --locked --no-dev`, and restarts FastAPI after successful
updates. Caddy reverse-proxies to FastAPI on `127.0.0.1:8000`.

Preview the actions without changing the host:

```bash
./deploy/native/setup.sh --dry-run
```

Install on the VPS as root:

```bash
sudo ./deploy/native/setup.sh
```

Install from a specific repo or branch:

```bash
sudo ./deploy/native/setup.sh \
  --repo-url https://github.com/mrmorawski/technoeconomics.git \
  --branch deploy
```

Defaults:

- App: `https://technoeconomics.app/`
- Grafana: `https://technoeconomics.app/grafana/`
- App install path: `/opt/technoeconomics/app`
- App system user: `technoeconomics`
- SSH remains on `22/tcp`
- Git branch tracked by supervisor: `deploy`

The setup script is idempotent. It clones the configured branch on first install,
or runs a fast-forward pull when the app directory already contains a Git
checkout.
