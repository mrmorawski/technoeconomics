#!/usr/bin/env bash
set -euo pipefail

DOMAIN="technoeconomics.app"
GRAFANA_PATH="/grafana"
REPO_URL="https://github.com/mrmorawski/technoeconomics.git"
BRANCH="deploy"
APP_USER="technoeconomics"
APP_DIR="/opt/technoeconomics/app"
STATE_DIR="/var/lib/technoeconomics"
CACHE_DIR="/var/cache/technoeconomics"
LOG_DIR="/var/log/technoeconomics"
DRY_RUN=0

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

usage() {
    cat <<EOF
Usage: $0 [options]

Install technoeconomics.app natively on a Debian-based system.

Options:
  --dry-run              Print actions without changing the host.
  --domain DOMAIN        Public domain served by Caddy (default: $DOMAIN).
  --grafana-path PATH    Grafana subpath (default: $GRAFANA_PATH).
  --repo-url URL         Git repository to clone/pull (default: $REPO_URL).
  --branch BRANCH        Git branch tracked by the supervisor (default: $BRANCH).
  --app-dir PATH         Deployment directory (default: $APP_DIR).
  -h, --help             Show this help.
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run)
            DRY_RUN=1
            shift
            ;;
        --domain)
            DOMAIN="${2:?missing value for --domain}"
            shift 2
            ;;
        --grafana-path)
            GRAFANA_PATH="${2:?missing value for --grafana-path}"
            shift 2
            ;;
        --repo-url)
            REPO_URL="${2:?missing value for --repo-url}"
            shift 2
            ;;
        --branch)
            BRANCH="${2:?missing value for --branch}"
            shift 2
            ;;
        --app-dir)
            APP_DIR="${2:?missing value for --app-dir}"
            shift 2
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "Unknown option: $1" >&2
            usage >&2
            exit 2
            ;;
    esac
done

if [[ "$GRAFANA_PATH" != /* ]]; then
    echo "--grafana-path must start with /" >&2
    exit 2
fi

if [[ "$DRY_RUN" -eq 0 && "${EUID:-$(id -u)}" -ne 0 ]]; then
    echo "Run as root, or pass --dry-run to inspect actions safely." >&2
    exit 1
fi

log() {
    printf '\n==> %s\n' "$*"
}

run() {
    if [[ "$DRY_RUN" -eq 1 ]]; then
        printf '[dry-run]'
        printf ' %q' "$@"
        printf '\n'
    else
        "$@"
    fi
}

run_shell() {
    if [[ "$DRY_RUN" -eq 1 ]]; then
        printf '[dry-run] bash -c %q\n' "$1"
    else
        bash -c "$1"
    fi
}

render_template() {
    local src="$1"
    local dst="$2"
    local mode="$3"
    local tmp

    if [[ "$DRY_RUN" -eq 1 ]]; then
        printf '[dry-run] render %q -> %q\n' "$src" "$dst"
        return
    fi

    tmp="$(mktemp)"
    sed \
        -e "s|{{DOMAIN}}|$DOMAIN|g" \
        -e "s|{{GRAFANA_PATH}}|$GRAFANA_PATH|g" \
        -e "s|{{APP_DIR}}|$APP_DIR|g" \
        -e "s|{{APP_USER}}|$APP_USER|g" \
        -e "s|{{STATE_DIR}}|$STATE_DIR|g" \
        -e "s|{{CACHE_DIR}}|$CACHE_DIR|g" \
        -e "s|{{LOG_DIR}}|$LOG_DIR|g" \
        -e "s|{{BRANCH}}|$BRANCH|g" \
        "$src" > "$tmp"
    install -D -m "$mode" "$tmp" "$dst"
    rm -f "$tmp"
}

write_file() {
    local dst="$1"
    local content="$2"

    if [[ "$DRY_RUN" -eq 1 ]]; then
        printf '[dry-run] write %q\n' "$dst"
        return
    fi

    install -D -m 0644 /dev/null "$dst"
    printf '%s\n' "$content" > "$dst"
}

install_packages() {
    log "Install host packages"
    run apt-get update
    run apt-get install -y \
        apt-transport-https \
        ca-certificates \
        curl \
        git \
        gnupg

    run install -d -m 0755 /etc/apt/keyrings
    run_shell "curl -fsSL https://apt.grafana.com/gpg-full.key -o /etc/apt/keyrings/grafana.asc"
    run chmod 0644 /etc/apt/keyrings/grafana.asc
    write_file /etc/apt/sources.list.d/grafana.list \
        "deb [signed-by=/etc/apt/keyrings/grafana.asc] https://apt.grafana.com stable main"

    run apt-get update
    run apt-get install -y \
        caddy \
        fail2ban \
        grafana \
        prometheus \
        prometheus-node-exporter \
        python3 \
        unattended-upgrades \
        ufw
}

install_uv() {
    log "Install uv"
    if [[ -x /usr/local/bin/uv ]]; then
        echo "uv already installed; skipping installer"
        return
    fi
    run_shell "curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR=/usr/local/bin sh"
}

create_app_user() {
    log "Create app user and directories"
    if id "$APP_USER" >/dev/null 2>&1; then
        echo "User $APP_USER already exists; skipping useradd"
    else
        run useradd --system --home "$STATE_DIR" --shell /usr/sbin/nologin "$APP_USER"
    fi

    run install -d -m 0750 -o "$APP_USER" -g "$APP_USER" "$STATE_DIR" "$CACHE_DIR" "$LOG_DIR"
    run install -d -m 0755 /var/log/caddy
    if id caddy >/dev/null 2>&1; then
        run chown caddy:caddy /var/log/caddy
    fi
}

deploy_app() {
    log "Deploy application Git checkout"
    run install -d -m 0755 -o "$APP_USER" -g "$APP_USER" "$(dirname "$APP_DIR")"

    if [[ "$DRY_RUN" -eq 1 ]]; then
        printf '[dry-run] if %q exists: runuser -u %q -- git -C %q pull --ff-only origin %q\n' \
            "$APP_DIR/.git" "$APP_USER" "$APP_DIR" "$BRANCH"
        printf '[dry-run] else: runuser -u %q -- git clone --branch %q --single-branch %q %q\n' \
            "$APP_USER" "$BRANCH" "$REPO_URL" "$APP_DIR"
    elif [[ -d "$APP_DIR/.git" ]]; then
        run runuser -u "$APP_USER" -- git -C "$APP_DIR" fetch origin "$BRANCH" --quiet
        run runuser -u "$APP_USER" -- git -C "$APP_DIR" checkout "$BRANCH"
        run runuser -u "$APP_USER" -- git -C "$APP_DIR" pull --ff-only origin "$BRANCH"
    elif [[ -d "$APP_DIR" && -n "$(ls -A "$APP_DIR")" ]]; then
        echo "$APP_DIR exists but is not a Git checkout; move it aside or choose --app-dir." >&2
        exit 1
    else
        run runuser -u "$APP_USER" -- git clone --branch "$BRANCH" --single-branch "$REPO_URL" "$APP_DIR"
    fi

    run chown -R "$APP_USER:$APP_USER" "$APP_DIR" "$STATE_DIR" "$CACHE_DIR" "$LOG_DIR"
    run runuser -u "$APP_USER" -- env \
        HOME="$STATE_DIR" \
        XDG_CACHE_HOME="$CACHE_DIR" \
        /usr/local/bin/uv sync --locked --no-dev --directory "$APP_DIR"
}

install_configs() {
    log "Install Caddy, systemd, fail2ban, Grafana, and Prometheus config"
    render_template "$SCRIPT_DIR/Caddyfile.template" /etc/caddy/Caddyfile 0644
    render_template "$SCRIPT_DIR/systemd/technoeconomics.service.template" \
        /etc/systemd/system/technoeconomics.service 0644
    render_template "$SCRIPT_DIR/systemd/grafana-server.override.conf.template" \
        /etc/systemd/system/grafana-server.service.d/override.conf 0644

    run install -D -m 0644 "$SCRIPT_DIR/fail2ban/jail.local" /etc/fail2ban/jail.d/technoeconomics.local
    run install -D -m 0644 "$SCRIPT_DIR/fail2ban/filter.d/caddy-scanners.conf" \
        /etc/fail2ban/filter.d/caddy-scanners.conf
    run install -D -m 0644 "$SCRIPT_DIR/prometheus/prometheus.yml" /etc/prometheus/prometheus.yml
    run install -D -m 0644 "$SCRIPT_DIR/systemd/prometheus.override.conf" \
        /etc/systemd/system/prometheus.service.d/override.conf
    run install -D -m 0644 "$SCRIPT_DIR/systemd/prometheus-node-exporter.override.conf" \
        /etc/systemd/system/prometheus-node-exporter.service.d/override.conf
    run install -D -m 0644 "$SCRIPT_DIR/grafana/provisioning/datasources/prometheus.yml" \
        /etc/grafana/provisioning/datasources/prometheus.yml
    run install -D -m 0644 "$SCRIPT_DIR/sysctl/99-technoeconomics-hardening.conf" \
        /etc/sysctl.d/99-technoeconomics-hardening.conf
    run install -D -m 0644 "$SCRIPT_DIR/apt/20auto-upgrades" \
        /etc/apt/apt.conf.d/20auto-upgrades
}

enable_services() {
    log "Enable services"
    run sysctl --system
    run systemctl daemon-reload
    run systemctl enable --now prometheus prometheus-node-exporter grafana-server caddy technoeconomics fail2ban
    run systemctl restart prometheus grafana-server caddy technoeconomics fail2ban
}

configure_firewall() {
    log "Configure UFW"
    if [[ "$DRY_RUN" -eq 1 ]]; then
        printf '[dry-run] bash %q --dry-run\n' "$SCRIPT_DIR/ufw-rules.sh"
        bash "$SCRIPT_DIR/ufw-rules.sh" --dry-run
    else
        bash "$SCRIPT_DIR/ufw-rules.sh"
    fi
}

install_packages
install_uv
create_app_user
deploy_app
install_configs
enable_services
configure_firewall

log "Deployment complete"
echo "App:     https://$DOMAIN/"
echo "Grafana: https://$DOMAIN$GRAFANA_PATH/"
echo "Check:   systemctl status technoeconomics caddy grafana-server prometheus fail2ban"
