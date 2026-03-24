"""
Main CLI module for Jataí using Typer.
"""

import os
import signal
import shutil
import subprocess
import sys
import time
import typer
from pathlib import Path
from typing import List, Optional

from jatai.core.autostart import AutoStartRegistrar
from jatai.core.daemon import AlreadyRunningError, JataiDaemon
from jatai.core.registry import Registry
from jatai.core.node import Node

app = typer.Typer(
    name="jatai",
    help="Jataí 🐝 - The local micro-email and messaging bus for your file system.",
)

KNOWN_COMMANDS = {"init", "status", "start", "stop", "docs", "_daemon-run"}
DOCS_ROOT = Path(__file__).resolve().parents[3] / "docs"


def _to_path(node_path: Path, raw_value: str) -> Path:
    """Convert INBOX/OUTBOX config values into absolute paths."""
    candidate = Path(raw_value)
    if candidate.is_absolute():
        return candidate
    return node_path / candidate


def _initialize_node(path: Optional[str] = None) -> None:
    """Initialize and register a Jataí node for the provided path."""
    if path is None:
        path = str(Path.cwd())

    node_path = Path(path).resolve()
    node = Node(node_path)

    # Load global registry to get default config
    try:
        registry = Registry()
        registry.load()
        global_config = registry.global_config
    except FileNotFoundError:
        # If global registry doesn't exist, use defaults
        global_config = Registry.DEFAULT_CONFIG.copy()

    inbox_cfg = str(global_config.get("INBOX_DIR", Node.INBOX_DIRNAME))
    outbox_cfg = str(global_config.get("OUTBOX_DIR", Node.OUTBOX_DIRNAME))
    inbox_path = _to_path(node_path, inbox_cfg)
    outbox_path = _to_path(node_path, outbox_cfg)

    if inbox_path.resolve() == outbox_path.resolve():
        base_dir = inbox_path.resolve()
        suggested_inbox = base_dir / "INBOX"
        suggested_outbox = base_dir / "OUTBOX"
        typer.echo("✗ INBOX_DIR and OUTBOX_DIR cannot be the same path.")
        typer.echo(
            "Suggested split: "
            f"INBOX={suggested_inbox} OUTBOX={suggested_outbox}"
        )
        confirmed = typer.confirm(
            "Create and use suggested INBOX/OUTBOX subdirectories?",
            default=True,
        )
        if not confirmed:
            raise typer.Exit(code=1)
        inbox_path = suggested_inbox
        outbox_path = suggested_outbox

    try:
        node.create(
            global_config=global_config,
            inbox_path=inbox_path,
            outbox_path=outbox_path,
        )
        typer.echo(f"✓ Initialized node at {node_path}")
        typer.echo(f"  INBOX:  {node.inbox_path}")
        typer.echo(f"  OUTBOX: {node.outbox_path}")
        typer.echo(f"  Config: {node.local_config_path}")

        # Add to global registry (optional, use node name from path)
        registry_to_update = Registry()
        try:
            registry_to_update.load()
        except FileNotFoundError:
            pass

        node_name = node_path.name
        registry_to_update.add_node(node_name, str(node_path), global_config)
        registry_to_update.save()
        typer.echo(f"✓ Added to global registry as '{node_name}'")

    except Exception as e:
        typer.echo(f"✗ Error initializing node: {e}", err=True)
        raise typer.Exit(code=1)


def _load_node_from_cwd() -> Node:
    node = Node(Path.cwd())
    if not node.is_enabled():
        raise FileNotFoundError("current directory is not a Jataí node")
    node.load_config()
    return node


def _docs_markdown_files() -> List[Path]:
    if not DOCS_ROOT.exists():
        return []
    return sorted(path for path in DOCS_ROOT.rglob("*.md") if path.is_file())


def _render_docs_index(markdown_files: List[Path]) -> str:
    categories: dict[str, list[str]] = {}
    for file_path in markdown_files:
        relative = file_path.relative_to(DOCS_ROOT)
        category = relative.parts[0] if len(relative.parts) > 1 else "general"
        categories.setdefault(category, []).append(relative.as_posix())

    lines = ["# Jatai Documentation Index", "", "Available categories and files:", ""]
    for category in sorted(categories):
        lines.append(f"## {category}")
        for doc_path in sorted(categories[category]):
            lines.append(f"- {doc_path}")
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def _safe_copy_to_inbox(source: Path, inbox_path: Path) -> Path:
    inbox_path.mkdir(parents=True, exist_ok=True)
    destination = inbox_path / source.name
    if not destination.exists():
        shutil.copy2(source, destination)
        return destination

    stem = source.stem
    suffix = source.suffix
    counter = 1
    while True:
        candidate = inbox_path / f"{stem}-{counter}{suffix}"
        if not candidate.exists():
            shutil.copy2(source, candidate)
            return candidate
        counter += 1


def _spawn_daemon_process() -> subprocess.Popen:
    """Spawn the background daemon process detached from the current terminal."""
    return subprocess.Popen(
        [sys.executable, "-m", "jatai.cli.main", "_daemon-run"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


@app.command()
def init(
    path: Optional[str] = typer.Argument(None, help="Path to initialize as a Jataí node"),
) -> None:
    """Initialize a new Jataí node."""
    _initialize_node(path)


@app.command()
def status() -> None:
    """Show status of the current node."""
    node_path = Path.cwd()
    node = Node(node_path)

    if not node.is_enabled():
        typer.echo("✗ Current directory is not a Jataí node", err=True)
        raise typer.Exit(code=1)

    try:
        node.load_config()
        inbox_files = node.list_inbox()
        outbox_files = node.list_outbox()

        typer.echo(f"Node: {node.node_path}")
        typer.echo(f"INBOX:  {len(inbox_files)} file(s)")
        typer.echo(f"OUTBOX: {len(outbox_files)} file(s)")

    except Exception as e:
        typer.echo(f"✗ Error: {e}", err=True)
        raise typer.Exit(code=1)


@app.command()
def start(
    foreground: bool = typer.Option(False, "--foreground", hidden=True),
) -> None:
    """Start the Jataí daemon."""
    daemon = JataiDaemon()

    if foreground:
        try:
            daemon.run()
        except AlreadyRunningError as e:
            typer.echo(f"✗ {e}", err=True)
            raise typer.Exit(code=1)
        return

    if daemon.is_running():
        typer.echo("✗ Already running", err=True)
        raise typer.Exit(code=1)

    service_path = AutoStartRegistrar().register()
    _spawn_daemon_process()
    typer.echo("✓ Daemon started")
    typer.echo(f"✓ Auto-start registered at {service_path}")


@app.command(name="_daemon-run", hidden=True)
def daemon_run() -> None:
    """Internal command used to run the daemon in the background."""
    daemon = JataiDaemon()
    try:
        daemon.run()
    except AlreadyRunningError as e:
        typer.echo(f"✗ {e}", err=True)
        raise typer.Exit(code=1)


@app.command()
def stop() -> None:
    """Stop the Jataí daemon."""
    daemon = JataiDaemon()
    pid = daemon.read_pid()

    if pid is None or not daemon.is_process_running(pid):
        daemon.release_singleton()
        typer.echo("✗ Daemon is not running", err=True)
        raise typer.Exit(code=1)

    os.kill(pid, signal.SIGTERM)
    deadline = 5.0
    start_time = time.monotonic()
    while time.monotonic() - start_time < deadline:
        if not daemon.is_process_running(pid):
            daemon.release_singleton()
            typer.echo("✓ Daemon stopped")
            return
        time.sleep(0.1)

    typer.echo("✗ Failed to stop daemon within timeout", err=True)
    raise typer.Exit(code=1)


@app.command()
def docs(
    query: Optional[str] = typer.Argument(None, help="Optional query to match local docs."),
) -> None:
    """Copy local docs index or matching docs into the current node INBOX."""
    try:
        node = _load_node_from_cwd()
    except Exception as e:
        typer.echo(f"✗ Error: {e}", err=True)
        raise typer.Exit(code=1)

    docs_files = _docs_markdown_files()
    if not docs_files:
        typer.echo("✗ Error: no markdown docs available in docs/", err=True)
        raise typer.Exit(code=1)

    if query is None:
        target = node.inbox_path / "!docs-index.md"
        target.write_text(_render_docs_index(docs_files), encoding="utf-8")
        typer.echo(f"✓ Docs index dropped at {target}")
        return

    normalized = query.strip().lower()
    matches = [
        file_path
        for file_path in docs_files
        if normalized in file_path.name.lower()
        or normalized in file_path.relative_to(DOCS_ROOT).as_posix().lower()
    ]
    if not matches:
        typer.echo(f"✗ Error: no docs matched '{query}'", err=True)
        raise typer.Exit(code=1)

    for match in matches:
        _safe_copy_to_inbox(match, node.inbox_path)
    typer.echo(f"✓ Copied {len(matches)} docs to {node.inbox_path}")


def run() -> None:
    """Entrypoint for console_scripts supporting `jatai [path]` alias."""
    args = sys.argv[1:]
    if not args:
        # No arguments: show help until TUI is implemented.
        app(["--help"])
        return
    if not args[0].startswith("-") and args[0] not in KNOWN_COMMANDS:
        _initialize_node(args[0])
        return
    app()


if __name__ == "__main__":
    run()
