# Configuration Reference

Jataí uses two layers of YAML configuration that are merged at runtime. This
document describes all available keys, their defaults, and where to set them.

## Configuration layers

### Global registry — `~/.jatai`

Defines system-wide defaults for all nodes and stores their paths.
Protected by a file lock. Edited by `jatai init` automatically; can also be
edited manually.

Example `~/.jatai`:
```yaml
PREFIX_IGNORE: "_"
PREFIX_ERROR: "!_"
RETRY_DELAY_BASE: 60
MAX_RETRIES: 3
INBOX_DIR: INBOX
OUTBOX_DIR: OUTBOX
GC_MAX_READ_FILES: 0
GC_MAX_SENT_FILES: 11
GC_DELETE_MODE: trash
LATEST_LOG_PATH: ~/.jatai_latest.log

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
| `PREFIX_IGNORE` | `_` | global / local | Prefix added to OUTBOX files after successful delivery (ignore/skip in OUTBOX); also used in INBOX to mark files as read |
| `PREFIX_ERROR` | `!_` | global / local | Base error prefix; daemon derives `!!` and `!!_` variants from this |
| `RETRY_DELAY_BASE` | `60` | global / local | Base delay in seconds for exponential backoff: `base * (2 ^ index)` |
| `MAX_RETRIES` | `3` | global / local | Maximum delivery attempts before transitioning to fatal prefix |
| `INBOX_DIR` | `INBOX` | global / local | Subdirectory name or absolute path for the node's incoming folder |
| `OUTBOX_DIR` | `OUTBOX` | global / local | Subdirectory name or absolute path for the node's outgoing folder |
| `GC_MAX_READ_FILES` | `0` | global / local | Maximum number of `_`-prefixed files to keep in INBOX. `0` keeps all read history |
| `GC_MAX_SENT_FILES` | `11` | global / local | Maximum number of `_`-prefixed files to keep in OUTBOX before oldest sent history is trimmed |
| `GC_DELETE_MODE` | `trash` | global / local | Deletion backend for GC: `trash` by default, or permanent delete when configured otherwise |
| `LATEST_LOG_PATH` | `~/.jatai_latest.log` | global | Location of the latest-log symlink/copy used by `jatai log` |

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
3. If a rename collision occurs, the previous config is restored from the daemon cache in `/tmp/jatai/bkp/<UUID>.yaml`
   and a notice file is dropped in INBOX. See [Prefix States](../operations/prefix-states.md).
4. Watchdog observers are updated to reflect any changed OUTBOX paths.

## Editing config via CLI

`jatai config` writes settings. `jatai config get` is the canonical read path.

```bash
# Read single key
jatai config get PREFIX_IGNORE
jatai config get -G PREFIX_IGNORE

# Write key/value
jatai config PREFIX_IGNORE __
jatai config -G MAX_RETRIES 5
```

Policy note:

- `-G` is the canonical short option for `--global`.
- Config keys are positional arguments and do not use short-option aliases.

### Read-only retrieval with `config get`

```bash
# Show full local config
jatai config get

# Show a local key
jatai config get MAX_RETRIES

# Show full global config
jatai config get -G

# Export retrieval output to current node INBOX
jatai config get PREFIX_IGNORE -i
```

`config get` is the safe read-only form for config inspection.

## Automatic garbage collection

The daemon enforces file count limits on processed (`_`-prefixed) history files.
This prevents INBOX and OUTBOX from growing unbounded over time.

- `GC_MAX_READ_FILES`: caps the number of `_`-prefixed files retained in INBOX.
- `GC_MAX_SENT_FILES`: caps the number of `_`-prefixed files retained in OUTBOX.

When the limit is exceeded, the oldest processed files (by modification time) are
deleted automatically during the startup scan and on every delivery cycle.

Set `GC_MAX_READ_FILES` to `0` to keep all read history. OUTBOX history keeps 11
files by default unless `GC_MAX_SENT_FILES` is overridden.

See [Garbage Collection](../operations/garbage-collection.md) for the full reference.

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
