# Repository Structure

This document describes the Jataí source tree and explains the role of each
module — written for contributors, maintainers, and anyone debugging the system.

## Top-level layout

```
.
├── src/jatai/              # Main package source code
├── tests/                  # Automated test suite (pytest)
├── docs/                   # In-band runtime documentation
├── tools/                  # Developer utilities
├── pyproject.toml          # Package metadata and entrypoint
├── requirements.txt        # Runtime dependencies
├── pytest.ini              # Pytest configuration
└── .gitignore
```

## `src/jatai/`

### `__init__.py`

Exports `__version__` and top-level public symbols. Version is kept in sync with
`pyproject.toml` via `tools/set_version`.

---

### `cli/main.py`

The Typer CLI application. Entry point registered as `jatai` in `pyproject.toml`.

Key responsibilities:
- Defines all CLI commands (`init`, `status`, `start`, `stop`, `docs`).
- Delegates node/registry work to core modules.
- `run()` is the actual console entrypoint; handles the `jatai <path>` alias by
  detecting non-flag, non-command first arguments.

Important constants:
- `KNOWN_COMMANDS` — set of recognized command names; drives the alias dispatch.
- `DOCS_ROOT` — absolute path to the `docs/` directory relative to
  the installed package.

---

### `core/registry.py` — `Registry`

Manages the global registry file (`~/.jatai`).

The registry is a YAML file with two kinds of entries:
- Global config keys (`PREFIX_IGNORE`, `OUTBOX_DIR`, etc.)
- Node entries (dicts with a `path` key)

All reads and writes are protected by a `filelock.FileLock`. Concurrent access
from the daemon and the CLI is safe.

Default config values (code reference: `Registry.DEFAULT_CONFIG`):

| Key | Default |
|---|---|
| `PREFIX_IGNORE` | `_` |
| `PREFIX_ERROR` | `!_` |
| `RETRY_DELAY_BASE` | `60` (seconds) |
| `MAX_RETRIES` | `3` |
| `INBOX_DIR` | `INBOX` |
| `OUTBOX_DIR` | `OUTBOX` |
| `GC_MAX_READ_FILES` | `0` (disabled) |
| `GC_MAX_SENT_FILES` | `0` (disabled) |

---

### `core/node.py` — `Node`

Represents a single node directory. Handles:
- Creating the INBOX/OUTBOX/config structure (`node.create()`).
- Loading `.jatai` or `._jatai` configs.
- Applying effective config by merging local over global.
- Prefix history migration on config change.
- Backup cache in `/tmp/jatai/bkp/<UUID>.yaml` for rollback on naming collisions.
- Dropping rollback notice files into INBOX.

Config files:
- `.jatai` — active configuration
- `._jatai` — soft-deleted (node ignored by daemon, root still monitored)
- `/tmp/jatai/bkp/<UUID>.yaml` — daemon backup cache for prefix-migration rollback

---

### `core/daemon.py` — `JataiDaemon`

The background routing engine. Single process, managed by PID lock at
`/tmp/jatai/jatai.pid`.

Lifecycle:
1. `acquire_singleton()` — write PID, fail if already running.
2. `setup_watchdog()` — schedule watchdog observers on all OUTBOX folders and
   all node roots (for config change detection).
3. `startup_scan()` — process pending files in all active OUTBOXes.
4. Main loop: `stop_event.wait(POLL_INTERVAL_SECONDS)` — retries due files.
5. On `SIGTERM`/`SIGINT`: sets `stop_event`, tears down observer, releases lock.

Node onboarding and validation: `_ensure_node_onboarded()` validates registered
paths, applies effective directory settings for existing nodes, persists UUID
state, and marks missing local configs as `--autoremoved` without recreating
node files or directories.

Logging: rotating daemon logs written to `/tmp/jatai/logs/` via Python's `logging` module
(INFO level, format: `timestamp LEVEL message`).

---

### `core/delivery.py` — `Delivery`

Atomic file copy implementation.

Sequence: write to `.tmp` → `shutil.copy2` → rename to final destination.
Name collisions in the destination INBOX are resolved by appending `(N)` suffixes.

---

### `core/retry.py` — `RetryState`

Manages `/tmp/jatai/retry.yaml` (JSON), protected by `filelock`.

`register_failure()` computes the next retry timestamp using the exponential
formula and returns metadata including `is_fatal` when `MAX_RETRIES` is reached.

---

### `core/prefix.py` — `Prefix`

Pure functions for prefix manipulation:
- Detecting state from filename prefix.
- Stripping and adding prefixes.
- Resolving rename targets during prefix hot-swap.

---

### `core/autostart.py` — `AutoStartRegistrar`

Registers the daemon for OS auto-start. Currently supports:
- **Linux** — writes a systemd user unit under `~/.config/systemd/user/`.
- *(macOS launchd and Windows startup folder planned for future phases.)*

---

## `tests/`

All tests use `pytest`. Run with:

```bash
./venv/bin/python -m pytest ./tests/ -v --tb=short
```

| File | Covers |
|---|---|
| `conftest.py` | Shared fixtures (`temp_dir`, `temp_home`) |
| `test_dummy.py` | Basic pytest sanity |
| `test_registry.py` | Registry load/save, lock contention, adversarial YAML |
| `test_node.py` | Node creation, config override, backup, prefix migration |
| `test_delivery.py` | Atomic delivery, collision resolution |
| `test_prefix.py` | Prefix state machine, max retries |
| `test_retry.py` | Retry scheduling, exponential delay, fatal transitions |
| `test_daemon.py` | Daemon lifecycle, watchdog events, logging, GC, retry, and config/reactivation flows |
| `test_cli.py` | CLI commands via Typer CliRunner |

---

## `tools/`

### `set_version`

Python script that updates all explicit version citations in the codebase
simultaneously. Always use this instead of editing version strings manually.

```bash
tools/set_version 0.5.1
```

Targets registered in the script's `VERSION_TARGETS` list:
- `pyproject.toml`
- `src/jatai/__init__.py`
- `README.md`
- `docs/jatai.1`

---

## `docs/`

In-band runtime documentation served by `jatai docs [query]`. Organized into
subfolders by category:

```
docs/
├── jatai.1                         # Manual page
├── getting-started/
│   ├── quickstart.md
│   └── configuration.md
├── operations/
│   ├── retry-and-health.md
│   ├── cli-reference.md
│   ├── prefix-states.md
│   └── garbage-collection.md
├── security/
│   └── safe-operations.md
└── development/
    └── repository-structure.md     ← this file
```

> Any `.md` file placed here becomes immediately available via `jatai docs`.

---

## Runtime files (user home)

| File | Purpose |
|---|---|
| `~/.jatai` | Global registry (YAML) — node paths and global config |
| `/tmp/jatai/jatai.pid` | Daemon PID (removed on clean stop) |
| `/tmp/jatai/jatai.pid.lock` | Filelock for PID write |
| `/tmp/jatai/retry.yaml` | Retry state (JSON) — per-file failure tracking |
| `/tmp/jatai/retry.yaml.lock` | Filelock for retry state |
| `/tmp/jatai/logs/*.log` | Rotating daemon event logs |

---

## Debugging common issues

### Daemon does not start

Check if a stale PID prevents startup:
```bash
cat /tmp/jatai/jatai.pid          # check what PID is stored
kill -0 $(cat /tmp/jatai/jatai.pid) 2>&1  # check if the process exists
rm /tmp/jatai/jatai.pid           # remove stale PID if process is gone
jatai start
```

### Files not being routed

1. Check the daemon is running: `cat /tmp/jatai/jatai.pid`
2. Review the log: `ls -1t /tmp/jatai/logs | head -n 1`
3. Verify the source node's OUTBOX is registered: `cat ~/.jatai`
4. Check the file does not start with a success/error prefix (those are skipped).

### Retry file is stuck

To inspect pending retries:
```bash
cat /tmp/jatai/retry.yaml
```

To force immediate retry (dangerous — edits the state file):
```bash
# Manually set all next_retry_at to 0
python3 -c "
import json, pathlib
p = pathlib.Path('/tmp/jatai/retry.yaml')
d = json.loads(p.read_text())
for v in d.values():
    v['next_retry_at'] = 0
p.write_text(json.dumps(d, indent=2))
"
```

### Node is not being picked up

Check whether the node's config is in soft-delete state:
```bash
ls -a /path/to/node | grep jatai
# If you see ._jatai instead of .jatai, the node is disabled
mv /path/to/node/._jatai /path/to/node/.jatai
```
