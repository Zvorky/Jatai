"""
Main CLI module for Jataí using Typer.
"""

import os
import signal
import subprocess
import sys
import time
import typer
from pathlib import Path
from typing import Optional

from jatai.core.autostart import AutoStartRegistrar
from jatai.core.daemon import AlreadyRunningError, JataiDaemon
from jatai.core.delivery import Delivery
from jatai.core.docs import deliver_docs
from jatai.core.prefix import Prefix
from jatai.core.registry import Registry
from jatai.core.node import Node

app = typer.Typer(
    name="jatai",
    help="Jataí 🐝 - The local micro-email and messaging bus for your file system.",
)

KNOWN_COMMANDS = {"init", "status", "start", "stop", "_daemon-run", "docs", "list", "send", "read", "unread", "config", "remove", "clear"}


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
        node.drop_helloworld()
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
def remove(
    path: Optional[str] = typer.Argument(None, help="Path to the node to disable (default: current directory)"),
) -> None:
    """Disable a node by renaming .jatai to ._jatai (soft-delete)."""
    node_path = Path(path).resolve() if path else Path.cwd()
    node = Node(node_path)

    if not node.is_enabled():
        if node.is_disabled():
            typer.echo(f"✗ Node is already disabled: {node_path}", err=True)
        else:
            typer.echo(f"✗ Not a Jataí node: {node_path}", err=True)
        raise typer.Exit(code=1)

    try:
        node.disable()
        typer.echo(f"✓ Node disabled (soft-deleted): {node_path}")
        typer.echo(f"  Config renamed to: {node.disabled_config_path.name}")
    except Exception as e:
        typer.echo(f"✗ Error disabling node: {e}", err=True)
        raise typer.Exit(code=1)


@app.command()
def config(
    key: str = typer.Argument(..., help="Configuration key to set"),
    value: str = typer.Argument(..., help="Value to assign"),
    global_flag: bool = typer.Option(False, "--global", help="Write to the global ~/.jatai config"),
) -> None:
    """Set a configuration value in the local node or global registry."""
    if global_flag:
        try:
            registry = Registry()
            try:
                registry.load()
            except FileNotFoundError:
                pass
            registry.set_config(key, value)
            registry.save()
            typer.echo(f"✓ Global config updated: {key} = {value}")
        except Exception as e:
            typer.echo(f"✗ Error updating global config: {e}", err=True)
            raise typer.Exit(code=1)
        return

    node_path = Path.cwd()
    node = Node(node_path)

    if not node.is_enabled():
        typer.echo("✗ Current directory is not a Jataí node", err=True)
        raise typer.Exit(code=1)

    try:
        node.load_config()
        node.set_config(key, value)
        typer.echo(f"✓ Node config updated: {key} = {value}")
    except Exception as e:
        typer.echo(f"✗ Error updating node config: {e}", err=True)
        raise typer.Exit(code=1)


@app.command(name="list")
def list_cmd(
    target: Optional[str] = typer.Argument(
        None,
        help="What to list: 'addrs' (all nodes), 'inbox', or 'outbox'",
    ),
) -> None:
    """List registered nodes or files in the local INBOX/OUTBOX."""
    if target == "addrs" or target == "nodes":
        try:
            registry = Registry()
            registry.load()
        except FileNotFoundError:
            typer.echo("(no nodes registered)")
            return

        nodes = registry.list_nodes()
        if not nodes:
            typer.echo("(no nodes registered)")
            return

        for name, path in nodes.items():
            typer.echo(f"{name}: {path}")
        return

    node_path = Path.cwd()
    node = Node(node_path)

    if not node.is_enabled():
        typer.echo("✗ Current directory is not a Jataí node", err=True)
        raise typer.Exit(code=1)

    try:
        node.load_config()
    except Exception as e:
        typer.echo(f"✗ Error loading node config: {e}", err=True)
        raise typer.Exit(code=1)

    show_inbox = target in (None, "inbox")
    show_outbox = target in (None, "outbox")

    if show_inbox:
        files = sorted(node.list_inbox())
        typer.echo(f"INBOX ({len(files)} file(s)):")
        for f in files:
            typer.echo(f"  {f.name}")

    if show_outbox:
        files = sorted(node.list_outbox())
        typer.echo(f"OUTBOX ({len(files)} file(s)):")
        for f in files:
            typer.echo(f"  {f.name}")


@app.command()
def send(
    file: str = typer.Argument(..., help="Path to the file to send"),
    move: bool = typer.Option(False, "--move", help="Move the file instead of copying it"),
) -> None:
    """Copy (or move) a file into the local OUTBOX."""
    node_path = Path.cwd()
    node = Node(node_path)

    if not node.is_enabled():
        typer.echo("✗ Current directory is not a Jataí node", err=True)
        raise typer.Exit(code=1)

    source = Path(file).resolve()
    if not source.exists():
        typer.echo(f"✗ File not found: {file}", err=True)
        raise typer.Exit(code=1)

    if not source.is_file():
        typer.echo(f"✗ Not a file: {file}", err=True)
        raise typer.Exit(code=1)

    try:
        node.load_config()
        delivery = Delivery(source, node.outbox_path)
        dest = delivery.deliver()
        if move:
            source.unlink(missing_ok=True)
            typer.echo(f"✓ Moved to OUTBOX: {dest.name}")
        else:
            typer.echo(f"✓ Sent to OUTBOX: {dest.name}")
    except Exception as e:
        typer.echo(f"✗ Error sending file: {e}", err=True)
        raise typer.Exit(code=1)


@app.command()
def read(
    file: str = typer.Argument(..., help="Filename (in INBOX) to mark as read"),
) -> None:
    """Mark an INBOX file as read by adding the success prefix."""
    node_path = Path.cwd()
    node = Node(node_path)

    if not node.is_enabled():
        typer.echo("✗ Current directory is not a Jataí node", err=True)
        raise typer.Exit(code=1)

    try:
        node.load_config()
    except Exception as e:
        typer.echo(f"✗ Error loading node config: {e}", err=True)
        raise typer.Exit(code=1)

    # Accept filename or full path
    file_path = Path(file)
    if not file_path.is_absolute():
        file_path = node.inbox_path / file_path.name

    if not file_path.exists():
        typer.echo(f"✗ File not found in INBOX: {file}", err=True)
        raise typer.Exit(code=1)

    try:
        success_prefix = str(node.get_config("PREFIX_PROCESSED", "_"))
        prefix = Prefix(success_prefix=success_prefix)
        new_path = prefix.add_success_prefix(file_path)
        typer.echo(f"✓ Marked as read: {new_path.name}")
    except ValueError as e:
        typer.echo(f"✗ {e}", err=True)
        raise typer.Exit(code=1)
    except Exception as e:
        typer.echo(f"✗ Error: {e}", err=True)
        raise typer.Exit(code=1)


@app.command()
def unread(
    file: str = typer.Argument(..., help="Filename (in INBOX) to mark as unread"),
) -> None:
    """Remove the success prefix from an INBOX file (mark as unread)."""
    node_path = Path.cwd()
    node = Node(node_path)

    if not node.is_enabled():
        typer.echo("✗ Current directory is not a Jataí node", err=True)
        raise typer.Exit(code=1)

    try:
        node.load_config()
    except Exception as e:
        typer.echo(f"✗ Error loading node config: {e}", err=True)
        raise typer.Exit(code=1)

    file_path = Path(file)
    if not file_path.is_absolute():
        file_path = node.inbox_path / file_path.name

    if not file_path.exists():
        typer.echo(f"✗ File not found in INBOX: {file}", err=True)
        raise typer.Exit(code=1)

    try:
        success_prefix = str(node.get_config("PREFIX_PROCESSED", "_"))
        prefix = Prefix(success_prefix=success_prefix)
        new_path = prefix.remove_success_prefix(file_path)
        typer.echo(f"✓ Marked as unread: {new_path.name}")
    except ValueError as e:
        typer.echo(f"✗ {e}", err=True)
        raise typer.Exit(code=1)
    except Exception as e:
        typer.echo(f"✗ Error: {e}", err=True)
        raise typer.Exit(code=1)


@app.command()
def docs(
    query: Optional[str] = typer.Argument(None, help="Search query for documentation topics"),
) -> None:
    """Fetch documentation into the local node INBOX."""
    node_path = Path.cwd()
    node = Node(node_path)

    if not node.is_enabled():
        typer.echo("✗ Current directory is not a Jataí node", err=True)
        raise typer.Exit(code=1)

    try:
        node.load_config()
        delivered = deliver_docs(query=query, inbox_path=node.inbox_path)
    except Exception as e:
        typer.echo(f"✗ Error delivering docs: {e}", err=True)
        raise typer.Exit(code=1)

    if not delivered:
        if query:
            typer.echo(f"✗ No documentation found matching '{query}'", err=True)
        else:
            typer.echo("✗ No documentation files found", err=True)
        raise typer.Exit(code=1)

    for path in delivered:
        typer.echo(f"✓ {path.name} → {node.inbox_path}")


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
