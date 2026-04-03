# **Jataí 🐝**
**The local micro-email and messaging bus for your file system. Connect scripts and AI agents instantly using a zero-config drop-folder pattern. Jataí uses OS file events to route data across directories via standardized INBOX/OUTBOX folders, without complex APIs or sockets. Drop a file, and it's delivered!**

**Version:** `0.7.4` (_Alpha_) · **Author:** Zvorky

## **🎯 Philosophy & Goal**

The main objective of Jataí is to eliminate the need for complex network setups (REST APIs, WebSockets, Localhost Ports) when making local scripts or AI agents talk to each other.
By utilizing standardized directories (INBOX/ and OUTBOX/) and operating system file events, Jataí creates a zero-configuration, asynchronous communication mesh across different directories or disk volumes on your machine.

**Core Tenets:**

1. **Language Agnostic:** If it can write a file, it can use Jataí.
2. **Controlled Deletion:** Jataí protects your data by *never* deleting pending or unprocessed files (it only copies or renames them to mark state). Deletions occur strictly on processed history files (`_`) when explicitly triggered by you (via the clear command) or by your configurable auto-retention rules to save disk space.
3. **File-System First:** You don't need a CLI to use Jataí daily. The entire system is responsive to native file explorer actions.

## **📦 Installation**

Jataí is currently in active development and is not published as a pip package yet.
Use a local virtual environment and install in editable mode.

```bash
python3 -m venv venv
. venv/bin/activate
pip install -e .
```

Add the following entries to your project's `.gitignore` to avoid committing Jataí artifacts:

```gitignore
# Jataí
INBOX/
OUTBOX/
.jatai.lock
# .jatai # Settings, you may want to synchronize them
```

## **🐝 Usage (The File-System Way)**

Current implementation status: core modules, basic CLI, daemon lifecycle, startup scan, watchdog-based routing, 5-state prefix handling, exponential retry management, rotating logs under `/tmp/jatai/logs/`, local config override handling, soft-delete/hot-reload monitoring, prefix hot-swap rollback, and in-band docs delivery are available for local development and testing.

1. **Initialize a Node (current command):** `jatai init ./my-folder`
2. **Initialize via Alias (current command):** `jatai ./my-folder`
3. **Check Node Status (current command):** `jatai status`
4. **Start the Daemon (current command):** `jatai start`
5. **Stop the Daemon (current command):** `jatai stop`
6. **Resilience behavior already implemented in core:** 5-state prefix matrix (`_`, `!`, `!_`, `!!`, `!!_`), retry state in `/tmp/jatai/retry.yaml` with exponential backoff, and `MAX_RETRIES` fatal transitions are covered by current code/tests.
7. **Observability already implemented in core:** Daemon logs rotate under `/tmp/jatai/logs/`, and `jatai log` resolves the latest log via the configured `LATEST_LOG_PATH` pointer with fallback to the newest rotated log.
8. **Configuration reactivity already implemented in core:** Local `.jatai` overrides are applied over global defaults, `._jatai` nodes are ignored while their roots remain monitored, and reactivation via rename is handled by the daemon.
9. **Prefix migration safety already implemented in core:** Prefix changes trigger historical file renames; collisions restore the previous config from `/tmp/jatai/bkp/<UUID>.yaml` and drop an error notice into the node INBOX.
10. **Onboarding and docs already implemented in core/CLI:** `jatai init` drops `!helloworld.md` in the node INBOX, `jatai docs` renders documentation in terminal by default, and `jatai docs [query]` renders matching markdown docs in terminal by default (`-i|--inbox` exports to files).
11. **Manual local-config deletion safety:** If `.jatai` is manually deleted from an existing registered node directory, the daemon will record the node as auto-removed in `/tmp/jatai/removed.yaml` (appending ` --autoremoved` to the stored path) and will NOT recreate `._jatai`, `.jatai`, `INBOX`, or `OUTBOX` automatically. The `._jatai` soft-delete marker is only created by explicit CLI/TUI removal actions (for example `jatai remove`, which performs `.jatai` → `._jatai`).
12. **First-run interactive bootstrap:** Opening the TUI (`jatai` with no args in interactive terminal) creates `~/.jatai` with default settings if it does not exist yet.
13. **Directory deletion resilience:** Deleting `INBOX` or `OUTBOX` does not soft-delete the node while `.jatai` still exists. `INBOX` is recreated when new deliveries arrive, and `OUTBOX` is recreated when enqueueing files (CLI `send`) or when recreated manually before new file drops.

## **🛠️ CLI & TUI Toolbox**

| Command | Action |
| :---- | :---- |
| `jatai` | Opens the interactive Text User Interface (TUI) when run in an interactive terminal; otherwise prints CLI help. |
| `jatai init [path]` | Initializes a node, registers it globally, and drops `!helloworld.md` into INBOX. Note: `jatai [path]` works as a direct alias. |
| `jatai start` | Starts the daemon and registers it for OS auto-start. Fails safely if already running. |
| `jatai stop` | Stops the background daemon. |
| `jatai status` | Returns node path, local config path, and file counters for the current node. |
| `jatai config [-G\|--global] [key] [value]` | Reads/writes configuration in local/global scope. |
| `jatai config get [key] [-G\|--global] [-i\|--inbox]` | Read-only config retrieval (single key or full scope); terminal mode shows source config path, and `--inbox` exports to current node INBOX. |
| `jatai list [addrs\|inbox\|outbox]` | Lists files in current node (inbox/outbox) or all nodes (addrs); `addrs` output shows global registry path. |
| `jatai send <file> [-m\|--move]` | Copies (or moves) an external file into the local OUTBOX. |
| `jatai read <file>` | Renames a file in the INBOX, adding the success prefix. |
| `jatai unread <file>` | Removes the success prefix from a file in the INBOX. |
| `jatai remove [path]` | Disables the node (current dir by default). Safeguarded against global origin. |
| `jatai clear [-r\|--read] [-s\|--sent]` | Clears processed files (`_`) in INBOX/OUTBOX (both by default). |
| `jatai cleanup --full [--dry-run] [--remove-logs] [-y\|--yes]` | Optional uninstall helper: removes local/global config artifacts and `/tmp/jatai` control state while preserving INBOX/OUTBOX contents (logs kept unless `--remove-logs`). |
| `jatai log` | Prints the latest log content in terminal (use `-i\|--inbox` to export). |
| `jatai log -a\|--all` | Prints the complete log output in terminal (use `-i\|--inbox` to export). |
| `jatai docs [query]` | Prints matching documentation in terminal by default (use `-i\|--inbox` to export file(s)). |

### TUI Workflow (current alpha)

`jatai` in an interactive terminal opens a menu-driven TUI that exposes the same handlers as CLI commands:

- `status`, `start`, `stop`
- `init` (initialize current/target node)
- `docs` (index/query), `log` (latest/all)
- `list`, `send`, `read`, `unread`
- `config get`, `config set` (local/global, optional INBOX export for get)
- `remove`, `clear`, `help`, `quit`

This keeps command behavior consistent between interactive and non-interactive usage.

### CLI Short-Option Policy (ADR 13)

Canonical abbreviated flags:

- `-a` = `--all`
- `-i` = `--inbox`
- `-m` = `--move`
- `-r` = `--read`
- `-s` = `--sent`
- `-f` = `--foreground`
- `-G` = `--global`
- `-d` = `--dry-run`
- `-l` = `--remove-logs`
- `-y` = `--yes`

Config keys are positional arguments (for example, `PREFIX_IGNORE`) and intentionally do not use short-option aliases.

## **🏗️ Architecture & Requirements**

* [**Architecture Decision Records (ADR)**](ARCHITECTURE.md)
* [**Technical Requirements**](REQUIREMENTS.md)
* **Deep Documentation:** Stored in the `docs/` folder (can be fetched via `jatai docs` and `jatai docs [query]`).

## **🗂️ File Structure**

```
.
├── src/jatai/                     # Main package source code
│   ├── __init__.py               # Package metadata and version info
│   ├── core/                      # Core modules
│   │   ├── __init__.py
│   │   ├── autostart.py          # OS auto-start registration helpers
│   │   ├── daemon.py             # Background daemon, PID lock, watchdog integration, hot-reload
│   │   ├── registry.py           # Global registry (~/.jatai) management
│   │   ├── delivery.py           # Atomic file delivery (shutil.copy2 with .tmp)
│   │   ├── prefix.py             # Prefix/state handling helpers
│   │   ├── retry.py              # Global retry state and exponential backoff scheduling
│   │   ├── node.py               # Node representation, config override, backup, and prefix migration
│   │   ├── sysstate.py           # System state storage under /tmp/jatai (uuid_map, removed, bkp)
│   │   └── uninstall.py          # Optional uninstall cleanup helper logic
│   ├── tui.py                    # Textual interactive terminal UI
│   └── cli/                       # Command-line interface
│       ├── __init__.py
│       └── main.py               # Typer CLI app and commands
├── tests/                         # Test suite (pytest)
│   ├── conftest.py               # pytest fixtures and configuration
│   ├── test_dummy.py             # Basic pytest setup test
│   ├── test_daemon.py            # Daemon lifecycle, watchdog, auto-start, hot-reload, and rollback tests
│   ├── test_registry.py          # Registry module tests (happy/error/adversarial/locks)
│   ├── test_delivery.py          # Delivery module tests (atomic delivery & naming collision)
│   ├── test_prefix.py            # Prefix state machine & max retries tests
│   ├── test_retry.py             # Retry state and exponential delay tests
│   ├── test_node.py              # Node module tests (config override, backup, and path validation)
│   ├── test_cli.py               # CLI tests using Typer's CliRunner
│   ├── test_uninstall.py         # Uninstall cleanup helper and CLI cleanup tests
│   └── test_sysstate.py          # /tmp/jatai system-state behavior tests
├── pyproject.toml                 # Packaging metadata and console_scripts entrypoint
├── pytest.ini                     # Pytest configuration
├── .gitignore                     # Git ignore rules
└── docs/                           # Runtime in-band documentation and manual page
    ├── jatai.1                    # Manual page used by the system CLI
    ├── getting-started/           # Quickstart, configuration reference
    ├── operations/                # CLI reference, prefix states, retry & health, garbage collection
    ├── security/                  # Safe usage and hardening notes
    └── development/               # Repository structure and debug guides
```

## **🚀 Future Ideas & Roadmap**

* **Phase 2:** Smart Routing & Topics (Pub/Sub channels using subdirectories).
* **Phase 3:** Node Addressing & Built-in Chat (Assigning unique IDs to directories for direct 1-to-1 delivery, plus a chat application that uses the Jataí transport).
* **Phase 4:** Jataí Over Internet (Direct IP/Port connection, allowing remote access beyond the local LAN).
* **Phase 5:** Global P2P Mesh Network & SaaS Control Plane (Addressing providers and mediators for offline message buffering, with free/paid storage tiers).

## **📄 License**

Jataí is released under the [Mozilla Public License 2.0 (MPL-2.0)](LICENSE).
**What this means:**

* **Free for all:** You can use, modify, and distribute Jataí freely, including in commercial or closed-source environments.
* **File-level Copyleft:** If you modify the *existing* Jataí source code files, you must share those specific modifications under the same MPL-2.0 license.
* **Your code is yours:** Larger projects or proprietary tools that merely use Jataí (or communicate with it via the file system) are not "infected" and can remain completely closed-source.
