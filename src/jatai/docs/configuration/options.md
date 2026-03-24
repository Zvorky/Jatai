# Configuration Options

Jataí uses a layered configuration system:
- **Global** (`~/.jatai`): Applies to all nodes as defaults.
- **Local** (`.jatai` in each node directory): Overrides global defaults for that node.

## Available Options

| Key | Default | Description |
|-----|---------|-------------|
| `PREFIX_PROCESSED` | `_` | Prefix added to files after successful delivery |
| `PREFIX_ERROR` | `!_` | Prefix added to files that failed delivery |
| `RETRY_DELAY_BASE` | `60` | Base delay in seconds for exponential retry (`base * 2^n`) |
| `MAX_RETRIES` | `3` | Maximum retry attempts before a file is marked fatal (`!!`) |
| `INBOX_DIR` | `INBOX` | Name or path of the INBOX directory |
| `OUTBOX_DIR` | `OUTBOX` | Name or path of the OUTBOX directory |
| `GC_ENABLED` | `false` | Enable automatic garbage collection of processed files |
| `GC_MAX_AGE_DAYS` | `30` | Delete `_` files older than this many days (requires `GC_ENABLED`) |
| `GC_MAX_FILES` | `0` | Keep at most this many `_` files per folder (0 = unlimited) |

## Setting Configuration

### Via CLI (recommended)

```bash
# Local (current node)
jatai config RETRY_DELAY_BASE 30
jatai config MAX_RETRIES 5

# Global (all nodes)
jatai config --global PREFIX_PROCESSED done_
```

### Manually Editing `.jatai`

```yaml
PREFIX_PROCESSED: done_
PREFIX_ERROR: err_
RETRY_DELAY_BASE: 30
MAX_RETRIES: 5
GC_ENABLED: true
GC_MAX_AGE_DAYS: 7
```

## Prefix Hot-Swap

Changing `PREFIX_PROCESSED` or `PREFIX_ERROR` in `.jatai` while the daemon is
running triggers an automatic rename of all historical files in INBOX and OUTBOX.

If a naming collision occurs during migration, the configuration change is
rolled back automatically (the old config is restored from `.jatai.bkp`) and
an error notice is dropped into the node's INBOX.
