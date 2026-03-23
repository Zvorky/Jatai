"""
Main CLI module for Jataí using Typer.
"""

import sys
import typer
from pathlib import Path
from typing import Optional

from jatai.core.registry import Registry
from jatai.core.node import Node

app = typer.Typer(
    name="jatai",
    help="Jataí 🐝 - The local micro-email and messaging bus for your file system.",
)

KNOWN_COMMANDS = {"init", "status"}


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


def run() -> None:
    """Entrypoint for console_scripts supporting `jatai [path]` alias."""
    args = sys.argv[1:]
    if args and not args[0].startswith("-") and args[0] not in KNOWN_COMMANDS:
        _initialize_node(args[0])
        return
    app()


if __name__ == "__main__":
    run()
