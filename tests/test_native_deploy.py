from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEPLOY = ROOT / "deploy" / "native"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_shell_scripts_parse() -> None:
    scripts = [DEPLOY / "setup.sh", DEPLOY / "ufw-rules.sh"]
    for script in scripts:
        subprocess.run(["bash", "-n", str(script)], check=True)


def test_supervisor_parses_and_dry_runs_update_commands() -> None:
    supervisor = DEPLOY / "supervisor.py"
    compile(read(supervisor), str(supervisor), "exec")

    result = subprocess.run(
        [sys.executable, str(supervisor), "--dry-run", "--once"],
        check=True,
        text=True,
        capture_output=True,
    )

    output = result.stdout
    assert "Dry run enabled" in output
    assert "uv sync --locked --no-dev" in output
    assert "git fetch origin deploy --quiet" in output
    assert "git pull --ff-only origin deploy" in output


def test_setup_dry_run_is_safe_and_covers_core_services() -> None:
    result = subprocess.run(
        ["bash", str(DEPLOY / "setup.sh"), "--dry-run"],
        check=True,
        text=True,
        capture_output=True,
    )

    output = result.stdout
    assert "apt-get install -y" in output
    assert "git" in output
    assert "grafana" in output
    assert "prometheus-node-exporter" in output
    assert "unattended-upgrades" in output
    assert "git clone --branch deploy --single-branch" in output
    assert "git -C /opt/technoeconomics/app pull --ff-only origin deploy" in output
    assert "render" in output
    assert "technoeconomics.service" in output
    assert "sysctl --system" in output
    assert "systemctl enable --now" in output
    assert "grafana-server" in output
    assert "ufw-rules.sh" in output


def test_ufw_dry_run_keeps_ssh_before_enable() -> None:
    result = subprocess.run(
        ["bash", str(DEPLOY / "ufw-rules.sh"), "--dry-run"],
        check=True,
        text=True,
        capture_output=True,
    )

    output = result.stdout
    ssh_index = output.index("ufw allow 22/tcp")
    enable_index = output.index("ufw --force enable")
    assert ssh_index < enable_index
    assert "ufw allow 80/tcp" in output
    assert "ufw allow 443/tcp" in output


def test_app_systemd_service_is_hardened_and_loopback_only() -> None:
    service = read(DEPLOY / "systemd" / "technoeconomics.service.template")

    assert "ExecStart=/usr/bin/python3 {{APP_DIR}}/deploy/native/supervisor.py" in service
    assert "TECHNOECONOMICS_HOST=127.0.0.1" in service
    assert "TECHNOECONOMICS_PORT=8000" in service
    assert "TECHNOECONOMICS_BRANCH={{BRANCH}}" in service
    assert "Restart=always" in service
    assert "NoNewPrivileges=true" in service
    assert "PrivateTmp=true" in service
    assert "ProtectSystem=strict" in service
    assert "ProtectHome=true" in service
    assert "ReadWritePaths={{APP_DIR}} {{STATE_DIR}} {{CACHE_DIR}} {{LOG_DIR}} /tmp" in service


def test_caddy_and_grafana_are_configured_for_subpath() -> None:
    caddyfile = read(DEPLOY / "Caddyfile.template")
    grafana_override = read(DEPLOY / "systemd" / "grafana-server.override.conf.template")

    assert "{{DOMAIN}}" in caddyfile
    assert "@grafana path {{GRAFANA_PATH}} {{GRAFANA_PATH}}/*" in caddyfile
    assert "reverse_proxy 127.0.0.1:3000" in caddyfile
    assert "reverse_proxy 127.0.0.1:8000" in caddyfile
    assert "GF_SERVER_ROOT_URL=https://{{DOMAIN}}{{GRAFANA_PATH}}/" in grafana_override
    assert "GF_SERVER_SERVE_FROM_SUB_PATH=true" in grafana_override
    assert "GF_SERVER_HTTP_ADDR=127.0.0.1" in grafana_override


def test_prometheus_is_local_and_grafana_datasource_points_to_it() -> None:
    prometheus_override = read(DEPLOY / "systemd" / "prometheus.override.conf")
    node_exporter_override = read(DEPLOY / "systemd" / "prometheus-node-exporter.override.conf")
    datasource = read(DEPLOY / "grafana" / "provisioning" / "datasources" / "prometheus.yml")

    assert "--web.listen-address=127.0.0.1:9090" in prometheus_override
    assert "--web.listen-address=127.0.0.1:9100" in node_exporter_override
    assert "url: http://127.0.0.1:9090" in datasource
    assert "isDefault: true" in datasource


def test_host_hardening_files_cover_sysctl_and_security_updates() -> None:
    sysctl = read(DEPLOY / "sysctl" / "99-technoeconomics-hardening.conf")
    auto_upgrades = read(DEPLOY / "apt" / "20auto-upgrades")

    assert "net.ipv4.tcp_syncookies = 1" in sysctl
    assert "net.ipv4.conf.all.accept_redirects = 0" in sysctl
    assert "net.ipv6.conf.all.accept_redirects = 0" in sysctl
    assert "kernel.dmesg_restrict = 1" in sysctl
    assert 'APT::Periodic::Unattended-Upgrade "1";' in auto_upgrades
