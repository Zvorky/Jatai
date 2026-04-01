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
import yaml
from pathlib import Path
from typing import List, Optional

from jatai.core.autostart import AutoStartRegistrar
from jatai.core.daemon import AlreadyRunningError, JataiDaemon
from jatai.core.delivery import Delivery
from jatai.core.prefix import Prefix
from jatai.core.registry import Registry
from jatai.core.node import Node
from jatai.core.uninstall import cleanup_install_artifacts

app = typer.Typer(
    name="jatai",
    help="Jataí 🐝 - The local micro-email and messaging bus for your file system.",
)

KNOWN_COMMANDS = {
    "init",
    "status",
    "start",
    "stop",
    "docs",
    "log",
    "list",
    "send",
    "read",
    "unread",
    "config",
    "remove",
    "clear",
    "cleanup",
    "_daemon-run",
}
DOCS_ROOT = Path(__file__).resolve().parents[3] / "docs"


def _drop_helloworld_tutorial(node: Node) -> None:
    """Drop !helloworld.md in node INBOX for newly initialized nodes."""
    source = DOCS_ROOT / "helloworld.md"
    if not source.exists():
        return
    node.inbox_path.mkdir(parents=True, exist_ok=True)
    target = node.inbox_path / "!helloworld.md"
    if target.exists():
        return
    shutil.copy2(source, target)


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
        _drop_helloworld_tutorial(node)
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
    base = source.name
    dest_name = base if base.startswith("!") else f"!{base}"
    destination = inbox_path / dest_name
    if not destination.exists():
        shutil.copy2(source, destination)
        return destination

    suffix = source.suffix
    stem = dest_name[: -len(suffix)] if suffix else dest_name
    counter = 1
    while True:
        candidate = inbox_path / f"{stem}-{counter}{suffix}"
        if not candidate.exists():
            shutil.copy2(source, candidate)
            return candidate
        counter += 1


def _export_text_to_inbox(node: Node, content: str, base_name: str) -> Path:
    node.inbox_path.mkdir(parents=True, exist_ok=True)
    target = node.inbox_path / base_name
    if not target.exists():
        target.write_text(content, encoding="utf-8")
        return target

    stem = target.stem
    suffix = target.suffix
    index = 1
    while True:
        candidate = node.inbox_path / f"{stem}-{index}{suffix}"
        if not candidate.exists():
            candidate.write_text(content, encoding="utf-8")
            return candidate
        index += 1


def _render_docs_terminal(matches: List[Path]) -> str:
    blocks: List[str] = []
    for path in matches:
        rel = path.relative_to(DOCS_ROOT).as_posix()
        content = path.read_text(encoding="utf-8")
        blocks.append(f"# {rel}\n\n{content.strip()}\n")
    return "\n---\n\n".join(blocks).strip() + "\n"


def _tail_lines(text: str, max_lines: int) -> str:
    lines = text.splitlines()
    if len(lines) <= max_lines:
        return text if text.endswith("\n") else text + "\n"
    clipped = lines[-max_lines:]
    return "\n".join(clipped) + "\n"


def _coerce_config_value(raw_value: str):
    lowered = raw_value.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    if raw_value.isdigit() or (raw_value.startswith("-") and raw_value[1:].isdigit()):
        return int(raw_value)
    return raw_value


def _format_config_output(config_data: dict, key: Optional[str]) -> str:
    if key is None:
        text = yaml.safe_dump(config_data, sort_keys=True)
        return text if text.endswith("\n") else text + "\n"
    if key not in config_data:
        raise KeyError(key)
    return f"{key}={config_data[key]}\n"


def _config_get(
    key: Optional[str],
    global_scope: bool,
    inbox: bool,
) -> None:
    config_data: dict
    scope_label = "global" if global_scope else "local"

    if global_scope:
        registry = Registry()
        try:
            registry.load()
        except FileNotFoundError:
            pass
        config_data = registry.global_config
        config_path = registry.registry_path
    else:
        node = _load_node_from_cwd()
        config_data = node.local_config
        config_path = node.local_config_path

    try:
        rendered = _format_config_output(config_data, key)
    except KeyError:
        typer.echo(f"✗ Error: unknown {scope_label} config key: {key}", err=True)
        raise typer.Exit(code=1)

    if not inbox:
        typer.echo(f"# source: {config_path}")
        typer.echo(rendered, nl=False)
        return

    try:
        node_for_export = _load_node_from_cwd()
    except Exception as e:
        typer.echo(f"✗ Error: {e}", err=True)
        raise typer.Exit(code=1)

    if key is None:
        filename = f"!config-{scope_label}.yaml"
    else:
        filename = f"!config-{scope_label}-{key}.txt"
    target = _export_text_to_inbox(node_for_export, rendered, filename)
    typer.echo(f"✓ Config exported to {target}")


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

        typer.echo(f"Node:   {node.node_path}")
        typer.echo(f"Config: {node.local_config_path}")
        typer.echo(f"INBOX:  {len(inbox_files)} file(s)")
        typer.echo(f"OUTBOX: {len(outbox_files)} file(s)")

    except Exception as e:
        typer.echo(f"✗ Error: {e}", err=True)
        raise typer.Exit(code=1)


@app.command()
def start(
    foreground: bool = typer.Option(False, "--foreground", "-f", hidden=True),
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
    inbox: bool = typer.Option(False, "--inbox", "-i", help="Export docs content to current node INBOX."),
) -> None:
    """Show docs in terminal by default, or export them to INBOX with --inbox."""
    node: Optional[Node] = None
    if inbox:
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
        content = _render_docs_index(docs_files)
        if inbox:
            assert node is not None
            target = _export_text_to_inbox(node, content, "!docs-index.md")
            typer.echo(f"✓ Docs index dropped at {target}")
        else:
            typer.echo(content, nl=False)
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

    if inbox:
        assert node is not None
        for match in matches:
            _safe_copy_to_inbox(match, node.inbox_path)
        typer.echo(f"✓ Copied {len(matches)} docs to {node.inbox_path}")
        return

    typer.echo(_render_docs_terminal(matches), nl=False)


@app.command()
def log(
    all_logs: bool = typer.Option(False, "--all", "-a", help="Show full log output."),
    inbox: bool = typer.Option(False, "--inbox", "-i", help="Export log output to current node INBOX."),
) -> None:
    """Show daemon logs in terminal, with optional export to INBOX."""
    log_path = Path.home() / ".jatai.log"
    if not log_path.exists():
        typer.echo(f"✗ Error: log file not found at {log_path}", err=True)
        raise typer.Exit(code=1)

    full_text = log_path.read_text(encoding="utf-8")
    rendered = full_text if all_logs else _tail_lines(full_text, 40)

    if inbox:
        try:
            node = _load_node_from_cwd()
        except Exception as e:
            typer.echo(f"✗ Error: {e}", err=True)
            raise typer.Exit(code=1)
        base_name = "!log-all.txt" if all_logs else "!log-latest.txt"
        target = _export_text_to_inbox(node, rendered, base_name)
        typer.echo(f"✓ Log exported to {target}")
        return

    typer.echo(rendered, nl=False)


@app.command(name="list")
def list_command(
    scope: str = typer.Argument("inbox", help="One of: addrs, inbox, outbox"),
) -> None:
    """List known node addresses or files from INBOX/OUTBOX."""
    normalized = scope.strip().lower()
    if normalized == "addrs":
        registry = Registry()
        try:
            registry.load()
        except FileNotFoundError:
            typer.echo("✗ Error: global registry not found", err=True)
            raise typer.Exit(code=1)

        typer.echo(f"# registry: {registry.registry_path}")
        for name, data in sorted(registry.nodes.items()):
            typer.echo(f"{name}: {data.get('path', '')}")
        return

    try:
        node = _load_node_from_cwd()
    except Exception as e:
        typer.echo(f"✗ Error: {e}", err=True)
        raise typer.Exit(code=1)

    if normalized == "inbox":
        files = sorted(node.list_inbox())
    elif normalized == "outbox":
        files = sorted(node.list_outbox())
    else:
        typer.echo("✗ Error: scope must be one of addrs, inbox, outbox", err=True)
        raise typer.Exit(code=1)

    for file_path in files:
        typer.echo(file_path.name)


@app.command()
def send(
    file_path: str = typer.Argument(..., help="Path to external file to send via OUTBOX."),
    move: bool = typer.Option(False, "--move", "-m", help="Move instead of copy after enqueue."),
) -> None:
    """Copy or move a file into the current node OUTBOX."""
    try:
        node = _load_node_from_cwd()
    except Exception as e:
        typer.echo(f"✗ Error: {e}", err=True)
        raise typer.Exit(code=1)

    source = Path(file_path).expanduser().resolve()
    if not source.exists() or not source.is_file():
        typer.echo(f"✗ Error: file not found: {source}", err=True)
        raise typer.Exit(code=1)

    try:
        delivered = Delivery(source, node.outbox_path).deliver()
        if move:
            source.unlink()
        typer.echo(f"✓ Enqueued at {delivered}")
    except Exception as e:
        typer.echo(f"✗ Error: {e}", err=True)
        raise typer.Exit(code=1)


@app.command()
def read(
    file_name: str = typer.Argument(..., help="INBOX file name to mark as read."),
) -> None:
    """Mark an INBOX file as read by adding success prefix."""
    try:
        node = _load_node_from_cwd()
    except Exception as e:
        typer.echo(f"✗ Error: {e}", err=True)
        raise typer.Exit(code=1)

    target = node.inbox_path / file_name
    if not target.exists():
        typer.echo(f"✗ Error: inbox file not found: {target}", err=True)
        raise typer.Exit(code=1)

    prefix = Prefix(
        success_prefix=str(node.get_config("PREFIX_IGNORE", "_")),
        error_prefix=str(node.get_config("PREFIX_ERROR", "!_")),
    )
    try:
        new_path = prefix.add_ignore_prefix(target)
        typer.echo(f"✓ Marked as read: {new_path.name}")
    except Exception as e:
        typer.echo(f"✗ Error: {e}", err=True)
        raise typer.Exit(code=1)


@app.command()
def unread(
    file_name: str = typer.Argument(..., help="INBOX file name to mark as unread."),
) -> None:
    """Mark an INBOX file as unread by removing success prefix."""
    try:
        node = _load_node_from_cwd()
    except Exception as e:
        typer.echo(f"✗ Error: {e}", err=True)
        raise typer.Exit(code=1)

    target = node.inbox_path / file_name
    if not target.exists():
        typer.echo(f"✗ Error: inbox file not found: {target}", err=True)
        raise typer.Exit(code=1)

    prefix = Prefix(
        success_prefix=str(node.get_config("PREFIX_IGNORE", "_")),
        error_prefix=str(node.get_config("PREFIX_ERROR", "!_")),
    )
    try:
        new_path = prefix.remove_ignore_prefix(target)
        typer.echo(f"✓ Marked as unread: {new_path.name}")
    except Exception as e:
        typer.echo(f"✗ Error: {e}", err=True)
        raise typer.Exit(code=1)


@app.command()
def config(
    key: Optional[str] = typer.Argument(None, help="Config key."),
    value: Optional[str] = typer.Argument(None, help="Config value to set."),
    global_scope: bool = typer.Option(False, "--global", "-G", help="Operate on global registry config."),
    inbox: bool = typer.Option(False, "--inbox", "-i", help="Export config retrieval output to current node INBOX (for config get)."),
) -> None:
    """Read or write configuration values."""
    if key == "get":
        return _config_get(value, global_scope, inbox)

    if inbox:
        typer.echo("✗ Error: --inbox is only supported with 'config get'", err=True)
        raise typer.Exit(code=1)

    if value is None:
        typer.echo("✗ Syntax error: 'jatai config [key]' is not allowed. Use 'jatai config get [key]' to read config values.", err=True)
        raise typer.Exit(code=1)

    if global_scope:
        registry = Registry()
        try:
            registry.load()
        except FileNotFoundError:
            pass

        registry.set_config(key, _coerce_config_value(value))
        registry.save()
        typer.echo(f"✓ Updated global config: {key}")
        return

    try:
        node = _load_node_from_cwd()
    except Exception as e:
        typer.echo(f"✗ Error: {e}", err=True)
        raise typer.Exit(code=1)

    node.set_config(key, _coerce_config_value(value))
    typer.echo(f"✓ Updated local config: {key}")


@app.command()
def remove(
    path: Optional[str] = typer.Argument(None, help="Node path to soft-delete (defaults to current directory)."),
) -> None:
    """Soft-delete a node by renaming .jatai to ._jatai."""
    node_path = Path(path).resolve() if path else Path.cwd()
    node = Node(node_path)
    try:
        node.disable()
        typer.echo(f"✓ Disabled node at {node.node_path}")
    except Exception as e:
        typer.echo(f"✗ Error: {e}", err=True)
        raise typer.Exit(code=1)


@app.command()
def clear(
    read: bool = typer.Option(False, "--read", "-r", help="Clear processed files from INBOX."),
    sent: bool = typer.Option(False, "--sent", "-s", help="Clear processed files from OUTBOX."),
) -> None:
    """Clear processed history files from INBOX and/or OUTBOX."""
    try:
        node = _load_node_from_cwd()
    except Exception as e:
        typer.echo(f"✗ Error: {e}", err=True)
        raise typer.Exit(code=1)

    if not read and not sent:
        read = True
        sent = True

    success_prefix = str(node.get_config("PREFIX_IGNORE", "_"))
    removed = 0

    if read:
        for file_path in node.list_inbox():
            if file_path.name.startswith(success_prefix):
                file_path.unlink()
                removed += 1

    if sent:
        for file_path in node.list_outbox():
            if file_path.name.startswith(success_prefix):
                file_path.unlink()
                removed += 1

    typer.echo(f"✓ Removed {removed} processed file(s)")


@app.command()
def cleanup(
    full: bool = typer.Option(
        False,
        "--full",
        "-f",
        help="Enable full uninstall cleanup mode.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        "-d",
        help="Show what would be removed without changing files.",
    ),
    remove_logs: bool = typer.Option(
        False,
        "--remove-logs",
        "-l",
        help="Also remove /tmp/jatai/logs during cleanup.",
    ),
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Skip interactive confirmation.",
    ),
) -> None:
    """
    Optional uninstall helper for cleaning Jatai config/control artifacts.

    This command keeps INBOX/OUTBOX message contents untouched.
    """
    if not full:
        typer.echo("✗ Refusing to run without --full.", err=True)
        typer.echo("Use: jatai cleanup --full --dry-run", err=True)
        raise typer.Exit(code=1)

    if not yes and not dry_run:
        confirmed = typer.confirm(
            "This will remove Jatai config/control artifacts. Continue?",
            default=False,
        )
        if not confirmed:
            typer.echo("Cancelled.")
            raise typer.Exit(code=1)

    actions = cleanup_install_artifacts(remove_logs=remove_logs, dry_run=dry_run)
    if not actions:
        typer.echo("No cleanup actions required.")
        return

    mode = "dry-run" if dry_run else "applied"
    typer.echo(f"Cleanup {mode}: {len(actions)} action(s)")
    for action in actions:
        typer.echo(f"- {action}")


def _run_tui() -> None:
    """Launch the Textual-based interactive TUI."""
    from jatai.tui import JataiApp
    JataiApp().run()


def run() -> None:
    """Entrypoint for console_scripts supporting `jatai [path]` alias."""
    args = sys.argv[1:]
    if not args:
        if sys.stdin.isatty() and sys.stdout.isatty():
            _run_tui()
            return
        app(["--help"])
        return
    if not args[0].startswith("-") and args[0] not in KNOWN_COMMANDS:
        _initialize_node(args[0])
        return
    app()


if __name__ == "__main__":
    run()
