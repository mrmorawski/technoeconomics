#!/usr/bin/env python3
"""Pull updates and supervise the native FastAPI process."""

from __future__ import annotations

import argparse
import logging
import logging.handlers
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

APP_DIR = Path(os.environ.get("TECHNOECONOMICS_APP_DIR", "/opt/technoeconomics/app"))
STATE_DIR = Path(os.environ.get("TECHNOECONOMICS_STATE_DIR", "/var/lib/technoeconomics"))
CACHE_DIR = Path(os.environ.get("TECHNOECONOMICS_CACHE_DIR", "/var/cache/technoeconomics"))
LOG_DIR = Path(os.environ.get("TECHNOECONOMICS_LOG_DIR", "/var/log/technoeconomics"))
UV_BIN = os.environ.get("TECHNOECONOMICS_UV", "/usr/local/bin/uv")
BRANCH = os.environ.get("TECHNOECONOMICS_BRANCH", "deploy")
HOST = os.environ.get("TECHNOECONOMICS_HOST", "127.0.0.1")
PORT = int(os.environ.get("TECHNOECONOMICS_PORT", "8000"))
UPDATE_INTERVAL = int(os.environ.get("TECHNOECONOMICS_UPDATE_INTERVAL", "300"))
LOG_MAX_BYTES = 10 * 1024 * 1024
LOG_BACKUP_COUNT = 5

running = True
app_proc: subprocess.Popen[str] | None = None
proc_lock = threading.Lock()


def parse_args() -> argparse.Namespace:
    """Parse supervisor options."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app-dir", type=Path, default=APP_DIR)
    parser.add_argument("--branch", default=BRANCH)
    parser.add_argument("--interval", type=int, default=UPDATE_INTERVAL)
    parser.add_argument("--host", default=HOST)
    parser.add_argument("--port", type=int, default=PORT)
    parser.add_argument("--uv", default=UV_BIN)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--once", action="store_true", help="check/update once, then exit")
    return parser.parse_args()


def setup_logging(dry_run: bool) -> logging.Logger:
    """Configure supervisor logging."""
    logger = logging.getLogger("technoeconomics-supervisor")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    formatter = logging.Formatter(
        "[%(asctime)s] %(levelname)s %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )
    stream = logging.StreamHandler(sys.stdout)
    stream.setFormatter(formatter)
    logger.addHandler(stream)

    if not dry_run:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            LOG_DIR / "supervisor.log",
            maxBytes=LOG_MAX_BYTES,
            backupCount=LOG_BACKUP_COUNT,
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


def run(
    cmd: list[str], logger: logging.Logger, *, cwd: Path, dry_run: bool
) -> subprocess.CompletedProcess[str]:
    """Run a command with logging."""
    logger.info("$ %s", " ".join(cmd))
    if dry_run:
        return subprocess.CompletedProcess(cmd, 0, "", "")

    result = subprocess.run(cmd, cwd=cwd, text=True, capture_output=True, check=False)
    if result.stdout.strip():
        logger.info(result.stdout.strip())
    if result.stderr.strip():
        logger.warning(result.stderr.strip())
    if result.returncode != 0:
        raise subprocess.CalledProcessError(
            result.returncode, cmd, output=result.stdout, stderr=result.stderr
        )
    return result


def ensure_git_checkout(app_dir: Path) -> None:
    """Ensure the application directory is a Git checkout."""
    if not (app_dir / ".git").is_dir():
        raise RuntimeError(f"{app_dir} is not a Git checkout; rerun setup.sh")


def remote_sha(app_dir: Path, branch: str, logger: logging.Logger, dry_run: bool) -> str:
    """Fetch and return the remote branch SHA."""
    run(["git", "fetch", "origin", branch, "--quiet"], logger, cwd=app_dir, dry_run=dry_run)
    if dry_run:
        return "REMOTE"
    return run(
        ["git", "rev-parse", "FETCH_HEAD"], logger, cwd=app_dir, dry_run=False
    ).stdout.strip()


def local_sha(app_dir: Path, logger: logging.Logger, dry_run: bool) -> str:
    """Return the local checkout SHA."""
    if dry_run:
        return "LOCAL"
    return run(["git", "rev-parse", "HEAD"], logger, cwd=app_dir, dry_run=False).stdout.strip()


def sync_dependencies(app_dir: Path, uv_bin: str, logger: logging.Logger, dry_run: bool) -> None:
    """Install locked production dependencies."""
    run([uv_bin, "sync", "--locked", "--no-dev"], logger, cwd=app_dir, dry_run=dry_run)


def pull_updates(app_dir: Path, branch: str, logger: logging.Logger, dry_run: bool) -> bool:
    """Pull the configured branch if the remote SHA differs."""
    remote = remote_sha(app_dir, branch, logger, dry_run)
    local = local_sha(app_dir, logger, dry_run)
    if remote == local:
        logger.info("No app update available")
        return False

    logger.info("Updating app: %s -> %s", local, remote)
    run(["git", "pull", "--ff-only", "origin", branch], logger, cwd=app_dir, dry_run=dry_run)
    return True


def app_environment() -> dict[str, str]:
    """Build the child process environment."""
    return {
        **os.environ,
        "HOME": str(STATE_DIR),
        "XDG_CACHE_HOME": str(CACHE_DIR),
        "PYTHONUNBUFFERED": "1",
    }


def app_command(app_dir: Path, host: str, port: int) -> list[str]:
    """Build the uvicorn command."""
    return [
        str(app_dir / ".venv" / "bin" / "uvicorn"),
        "technoeconomics.web.main:app",
        "--host",
        host,
        "--port",
        str(port),
        "--proxy-headers",
        "--forwarded-allow-ips=127.0.0.1",
    ]


def drain_output(proc: subprocess.Popen[str], logger: logging.Logger) -> None:
    """Forward child output into supervisor logs."""
    if proc.stdout is None:
        return
    for line in proc.stdout:
        logger.info("[app] %s", line.rstrip("\n"))


def start_app(app_dir: Path, host: str, port: int, logger: logging.Logger, dry_run: bool) -> None:
    """Start the FastAPI child process."""
    global app_proc

    cmd = app_command(app_dir, host, port)
    logger.info("Starting app: %s", " ".join(cmd))
    if dry_run:
        return

    proc = subprocess.Popen(
        cmd,
        cwd=app_dir,
        env=app_environment(),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    with proc_lock:
        app_proc = proc
    threading.Thread(target=drain_output, args=(proc, logger), daemon=True).start()


def stop_app(logger: logging.Logger) -> None:
    """Stop the child process if it is running."""
    global app_proc

    with proc_lock:
        proc = app_proc
    if proc is None or proc.poll() is not None:
        return

    logger.info("Stopping app pid=%s", proc.pid)
    proc.terminate()
    try:
        proc.wait(timeout=20)
    except subprocess.TimeoutExpired:
        logger.warning("App did not stop gracefully; killing pid=%s", proc.pid)
        proc.kill()
        proc.wait(timeout=10)


def restart_app(app_dir: Path, host: str, port: int, logger: logging.Logger, dry_run: bool) -> None:
    """Restart the child process."""
    stop_app(logger)
    start_app(app_dir, host, port, logger, dry_run)


def check_process(
    app_dir: Path, host: str, port: int, logger: logging.Logger, dry_run: bool
) -> None:
    """Respawn the child if it exited."""
    with proc_lock:
        proc = app_proc
    if proc is None:
        start_app(app_dir, host, port, logger, dry_run)
    elif proc.poll() is not None:
        logger.warning("App exited with code %s; respawning", proc.returncode)
        start_app(app_dir, host, port, logger, dry_run)


def update_once(args: argparse.Namespace, logger: logging.Logger) -> bool:
    """Check for app updates once; restart after successful update."""
    if not args.dry_run:
        ensure_git_checkout(args.app_dir)

    changed = pull_updates(args.app_dir, args.branch, logger, args.dry_run)
    if changed:
        sync_dependencies(args.app_dir, args.uv, logger, args.dry_run)
        restart_app(args.app_dir, args.host, args.port, logger, args.dry_run)
    return changed


def shutdown(signum: int | None, _frame: object, logger: logging.Logger) -> None:
    """Handle process termination."""
    global running
    running = False
    logger.info("Received signal %s; shutting down", signum)
    stop_app(logger)


def main() -> int:
    """Run supervisor."""
    args = parse_args()
    logger = setup_logging(args.dry_run)

    signal.signal(signal.SIGINT, lambda signum, frame: shutdown(signum, frame, logger))
    signal.signal(signal.SIGTERM, lambda signum, frame: shutdown(signum, frame, logger))

    if args.dry_run:
        logger.info("Dry run enabled; no services will be started or changed")

    if not args.dry_run:
        ensure_git_checkout(args.app_dir)
    sync_dependencies(args.app_dir, args.uv, logger, args.dry_run)
    if args.once:
        update_once(args, logger)
        return 0

    start_app(args.app_dir, args.host, args.port, logger, args.dry_run)
    while running:
        time.sleep(args.interval)
        try:
            update_once(args, logger)
            check_process(args.app_dir, args.host, args.port, logger, args.dry_run)
        except Exception:
            logger.exception("Update loop failed; keeping current app process")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
