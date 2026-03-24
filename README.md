# **Jataí 🐝**
**The local micro-email and messaging bus for your file system. Connect scripts and AI agents instantly using a zero-config drop-folder pattern. Jataí uses OS file events to route data across directories via standardized INBOX/OUTBOX folders, without complex APIs or sockets. Drop a file, and it's delivered!**

**Version:** `0.6.5` (_Alpha_) · **Author:** Zvorky

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
# .jatai # Settings, you may want to synchronize them
```

## **🐝 Usage (The File-System Way)**

Current implementation status: core modules, basic CLI, daemon lifecycle, startup scan, watchdog-based routing, 5-state prefix handling, exponential retry management, global logging, local config override handling, soft-delete/hot-reload monitoring, prefix hot-swap rollback, auto-onboarding with `!helloworld.md` drops, in-band documentation system (`jatai docs`), extended CLI toolbox (`jatai list`, `jatai send`, `jatai read`, `jatai unread`, `jatai config`, `jatai remove`, `jatai clear`), and background garbage collection are all available.

1. **Initialize a Node (current command):** `jatai init ./my-folder`
2. **Initialize via Alias (current command):** `jatai ./my-folder`
3. **Check Node Status (current command):** `jatai status`
4. **Start the Daemon (current command):** `jatai start`
5. **Stop the Daemon (current command):** `jatai stop`
6. **Auto-Onboarding already implemented:** Daemon detects paths added manually to `~/.jatai` and generates missing INBOX/OUTBOX folders, dropping `!helloworld.md` into the new INBOX.
7. **Extended CLI toolbox already implemented:** `jatai list [addrs|inbox|outbox]`, `jatai send <file> [--move]`, `jatai read <file>`, `jatai unread <file>`, `jatai config [--global] <key> <val>`, `jatai remove [path]`, `jatai clear [inbox|outbox]`.
8. **In-band documentation:** `jatai docs` drops a category index into the local INBOX. `jatai docs <query>` copies matching docs.
9. **Garbage Collection:** Daemon automatically removes `_` prefixed files based on `GC_ENABLED`, `GC_MAX_AGE_DAYS`, and `GC_MAX_FILES` config keys.
10. **Resilience behavior already implemented in core:** 5-state prefix matrix (`_`, `!`, `!_`, `!!`, `!!_`), global `.retry` state with exponential backoff, and `MAX_RETRIES` fatal transitions are covered by current code/tests.
11. **Observability already implemented in core:** Global daemon log file output to `~/.jatai.log` is active.
12. **Configuration reactivity already implemented in core:** Local `.jatai` overrides are applied over global defaults, `._jatai` nodes are ignored while their roots remain monitored, and reactivation via rename is handled by the daemon.
13. **Prefix migration safety already implemented in core:** Prefix changes trigger historical file renames; collisions restore the previous config from `.jatai.bkp` and drop an error notice into the node INBOX.

The command surface in the sections below remains the product target roadmap, not a statement that every command is already available.

## **🛠️ CLI & TUI Toolbox**

| Command | Action |
| :---- | :---- |
| `jatai` | Opens the interactive Text User Interface (TUI). **[TEMP]** Currently aliased to `jatai --help`. |
| `jatai init [path]` | Initializes a node. Note: `jatai [path]` works as a direct alias. |
| `jatai start` | Starts the daemon and registers it for OS auto-start. Fails safely if already running. |
| `jatai stop` | Stops the background daemon. |
| `jatai status` | Returns file counters for the current node. |
| `jatai config [--global] <key> <val>` | Sets a configuration parameter locally or globally. |
| `jatai list [addrs\|inbox\|outbox]` | Lists files in current node (inbox/outbox) or all nodes (addrs). |
| `jatai send <file> [--move]` | Copies (or moves) an external file into the local OUTBOX. |
| `jatai read <file>` | Renames a file in the INBOX, adding the success prefix. |
| `jatai unread <file>` | Removes the success prefix from a file in the INBOX. |
| `jatai remove [path]` | Disables the node (current dir by default). Renames `.jatai` → `._jatai`. |
| `jatai clear [inbox\|outbox]` | Clears processed files (`_`) in both folders or a specific one. |
| `jatai docs [query]` | Fetches deep documentation from docs/ into the INBOX. |

## **🏗️ Architecture & Requirements**

* [**Architecture Decision Records (ADR)**](ARCHITECTURE.md)
* [**Technical Requirements**](REQUIREMENTS.md)
* **Deep Documentation:** Planned to be stored in the `docs/` folder (can be fetched via jatai docs).

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
│   │   ├── docs.py               # In-band documentation delivery (jatai docs)
│   │   ├── gc.py                 # Garbage collection (auto-remove processed files)
│   │   ├── prefix.py             # Prefix/state handling helpers
│   │   ├── retry.py              # Global retry state and exponential backoff scheduling
│   │   └── node.py               # Node representation, config override, backup, and prefix migration
│   ├── cli/                       # Command-line interface
│   │   ├── __init__.py
│   │   └── main.py               # Typer CLI app and commands
│   └── docs/                      # Bundled in-band documentation (markdown)
│       ├── getting-started/
│       │   ├── quickstart.md
│       │   └── installation.md
│       ├── cli/
│       │   └── reference.md
│       ├── configuration/
│       │   └── options.md
│       └── architecture/
│           └── overview.md
├── tests/                         # Test suite (pytest)
│   ├── conftest.py               # pytest fixtures and configuration
│   ├── test_dummy.py             # Basic pytest setup test
│   ├── test_daemon.py            # Daemon lifecycle, watchdog, auto-start, hot-reload, and rollback tests
│   ├── test_registry.py          # Registry module tests (happy/error/adversarial/locks)
│   ├── test_delivery.py          # Delivery module tests (atomic delivery & naming collision)
│   ├── test_docs.py              # Docs module and jatai docs CLI tests
│   ├── test_gc.py                # Garbage collection tests
│   ├── test_prefix.py            # Prefix state machine & max retries tests
│   ├── test_retry.py             # Retry state and exponential delay tests
│   ├── test_node.py              # Node module tests (config override, backup, and path validation)
│   └── test_cli.py               # CLI tests using Typer's CliRunner
├── requirements.txt               # Python dependencies currently in use
├── pyproject.toml                 # Packaging metadata and console_scripts entrypoint
├── pytest.ini                     # Pytest configuration
├── .gitignore                     # Git ignore rules
└── docs/jatai.1                   # Manual page used by the system CLI
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
