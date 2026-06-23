#!/usr/bin/env bash
set -euo pipefail

DRY_RUN=0

usage() {
    cat <<EOF
Usage: $0 [--dry-run]

Configure UFW for the native technoeconomics deployment.
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run)
            DRY_RUN=1
            shift
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

if [[ "$DRY_RUN" -eq 0 && "${EUID:-$(id -u)}" -ne 0 ]]; then
    echo "Run as root, or pass --dry-run to inspect actions safely." >&2
    exit 1
fi

run() {
    if [[ "$DRY_RUN" -eq 1 ]]; then
        printf '[dry-run]'
        printf ' %q' "$@"
        printf '\n'
    else
        "$@"
    fi
}

run ufw default deny incoming
run ufw default allow outgoing

# Keep the current SSH entry point open before enabling the firewall.
run ufw allow 22/tcp comment "SSH"
run ufw allow 80/tcp comment "HTTP for Caddy ACME redirects"
run ufw allow 443/tcp comment "HTTPS for Caddy"

run ufw logging on
run ufw --force enable
run ufw status verbose
