# Configuration Reference

Jataí uses two layers of YAML configuration that are merged at runtime. This
document describes all available keys, their defaults, and where to set them.

## Configuration layers

### Global registry — `~/.jatai`

Defines system-wide defaults for all nodes and stores their paths.
Protected by a file lock. Edited by `jatai init` automatically; can also be
edited manually (the daemon auto-onboards any new path it finds there).

Example `~/.jatai`:
```yaml
PREFIX_PROCESSED: "_"
PREFIX_ERROR: "!_"
RETRY_DELAY_BASE: 60
MAX_RETRIES: 3
INBOX_DIR: INBOX
OUTBOX_DIR: OUTBOX

my-project:
  path: /home/user/my-project

other-agent:
  path: /home/user/other-agent
```

### Local node config — `.jatai`

Placed at the root of each node directory. Overrides global defaults for that
node only. Written by `jatai init`; editable at any time — the daemon hot-reloads
it automatically when the file changes.

Soft-deleting a node: rename `.jatai` → `._jatai`. The daemon ignores the node's
contents but continues watching the root for reactivation.

## All configuration keys

| Key | Default | Scope | Description |
|---|---|---|---|
| `PREFIX_PROCESSED` | `_` | global / local | Prefix added to OUTBOX files after successful delivery; also used in INBOX to mark read files |
| `PREFIX_ERROR` | `!_` | global / local | Base error prefix; daemon derives `!!` and `!!_` variants from this |
| `RETRY_DELAY_BASE` | `60` | global / local | Base delay in seconds for exponential backoff: `base * (2 ^ index)` |
| `MAX_RETRIES` | `3` | global / local | Maximum delivery attempts before transitioning to fatal prefix |
| `INBOX_DIR` | `INBOX` | global / local | Subdirectory name or absolute path for the node's incoming folder |
| `OUTBOX_DIR` | `OUTBOX` | global / local | Subdirectory name or absolute path for the node's outgoing folder |

### Relative vs absolute paths for INBOX/OUTBOX

If `INBOX_DIR` or `OUTBOX_DIR` is a relative path (e.g., `INBOX`), it resolves
relative to the node directory. An absolute path is used as-is.

```yaml
# Relative (resolves to /home/user/my-project/INBOX)
INBOX_DIR: INBOX

# Absolute
INBOX_DIR: /data/shared/incoming
```

Jataí strictly prevents `INBOX_DIR` and `OUTBOX_DIR` from resolving to the same
path. See [Safe Operations](../security/safe-operations.md).

## Effective config merge order

When the daemon activates a node, it resolves the effective configuration as:

```
Registry defaults  ←  global ~/.jatai keys  ←  local .jatai keys
```

Local keys always win. Missing local keys fall back to global, which falls back
to the compiled-in `DEFAULT_CONFIG` defaults.

## Hot-reload behavior

The daemon monitors each node root for changes to `.jatai` and `._jatai`. When
a change is detected:

1. The node config is re-read.
2. If the prefix keys changed, historical file renames are attempted.
3. If a rename collision occurs, the previous config is restored from `.jatai.bkp`
   and a notice file is dropped in INBOX. See [Prefix States](../operations/prefix-states.md).
4. Watchdog observers are updated to reflect any changed OUTBOX paths.

## Editing config via CLI

> **Future (Phase 6):** `jatai config [--global] <key> <value>` will allow reading
> and writing config keys from the terminal without manually editing YAML files.

Until then, edit `.jatai` or `~/.jatai` directly with any text editor. The daemon
picks up changes automatically.

## Example: per-node retry tuning

Increase retry patience for a slow network drive while keeping the global default
aggressive:

```yaml
# ~/.jatai (global)
RETRY_DELAY_BASE: 30
MAX_RETRIES: 3

# /mnt/slow-drive/agent/.jatai (local override)
RETRY_DELAY_BASE: 120
MAX_RETRIES: 5
```

## Example: custom folder names

```yaml
# .jatai in the node root
INBOX_DIR: messages/incoming
OUTBOX_DIR: messages/outgoing
```

This creates:
```
my-project/
├── messages/
│   ├── incoming/
│   └── outgoing/
└── .jatai
```
