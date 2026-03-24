# Garbage Collection

Jataí never deletes pending or unprocessed files. The only files eligible for
removal are those already marked with the success prefix (`_`). Two mechanisms
exist for cleaning them up: manual and automatic.

## Manual cleanup — `jatai clear`

Run from a node directory to remove processed history files immediately:

```bash
# Remove _-prefixed files from both INBOX and OUTBOX
jatai clear

# Remove only from INBOX (read files)
jatai clear -r

# Remove only from OUTBOX (sent files)
jatai clear -s
```

Only files whose names begin with the configured `PREFIX_PROCESSED` (default `_`)
are affected. Pending files, error files, and fatal error files are never touched.

## Automatic cleanup — `GC_MAX_READ_FILES` and `GC_MAX_SENT_FILES`

The daemon enforces optional file count limits on processed history. When the
count of `_`-prefixed files in a folder exceeds the configured maximum, the
oldest files (by modification time) are deleted automatically.

| Config key | Default | Applies to |
|---|---|---|
| `GC_MAX_READ_FILES` | `0` | INBOX — `_`-prefixed (read) files |
| `GC_MAX_SENT_FILES` | `0` | OUTBOX — `_`-prefixed (sent/delivered) files |

`0` means no limit — auto-cleanup is disabled by default.

### Setting limits

Set globally to apply to all nodes:

```bash
jatai config -G GC_MAX_READ_FILES 100
jatai config -G GC_MAX_SENT_FILES 50
```

Or per-node to override the global value:

```bash
# From inside the node directory
jatai config GC_MAX_READ_FILES 20
jatai config GC_MAX_SENT_FILES 10
```

Equivalently, edit `.jatai` directly:

```yaml
GC_MAX_READ_FILES: 20
GC_MAX_SENT_FILES: 10
```

### When auto-cleanup runs

- On each **startup scan** (when the daemon starts or restarts).
- After each **delivery cycle** for the node that sent files.

Auto-cleanup only removes files that already carry the success prefix. Undelivered
files (no prefix), error files (`!`, `!_`), and fatal files (`!!`, `!!_`) are
never touched.

## Interaction with `jatai clear`

Both mechanisms target the same set of files. Running `jatai clear` is always
safe even if auto-GC is enabled; it simply removes eligible files immediately
rather than waiting for the next daemon cycle.

## Relationship to prefix states

For a full description of the prefix states and which files are considered
"processed", see [Prefix States](prefix-states.md).
