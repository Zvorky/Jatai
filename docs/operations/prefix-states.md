# Prefix States

Jataí uses filename prefixes as a state machine. Every file in an OUTBOX or
INBOX carries its delivery status encoded in its name — no database needed.

## The 5-state matrix

| Prefix | State | Location | Meaning |
|--------|-------|----------|---------|
| _(none)_ | **Pending** | OUTBOX | Unprocessed — daemon will act immediately on this file |
| `_` | **Delivered** | OUTBOX | Broadcast to all active nodes successfully |
| `!` | **Total Error** | OUTBOX | Failed to deliver to all active nodes — pending retry |
| `!_` | **Partial Error** | OUTBOX | Delivered to some nodes, failed for others — pending retry |
| `!!` | **Fatal Total Error** | OUTBOX | Max retries reached, all nodes failed — will not retry |
| `!!_` | **Fatal Partial Error** | OUTBOX | Max retries reached, some nodes failed — will not retry |

Additionally, files in INBOX may also carry a success prefix once read:

| Prefix | State | Location | Meaning |
|--------|-------|----------|---------|
| _(none)_ | Unread | INBOX | Incoming file, not yet processed locally |
| `_` | Read | INBOX | Marked as processed (via `jatai read`, planned Phase 6) |
| `!` | Error | INBOX | Rollback/error notices dropped by the daemon |

## How the daemon applies prefixes

On each delivery attempt, the daemon:

1. Looks for files in OUTBOX **without** prefixes.
2. Attempts delivery to all other active nodes.
3. Renames the file in OUTBOX to reflect the outcome.

State flow:

```
[no prefix]  →  delivery succeeds  →  _filename
             →  all nodes fail     →  !filename       (retry scheduled)
             →  some nodes fail    →  !_filename      (retry scheduled)

!filename    →  retry succeeds     →  _filename
             →  still failing      →  !filename       (next retry)
             →  max retries hit    →  !!filename      (fatal, no more retries)

!_filename   →  retry succeeds     →  _filename
             →  still partial      →  !_filename      (next retry)
             →  max retries hit    →  !!_filename     (fatal, no more retries)
```

## Configuring prefixes

Both prefixes are configurable. Defaults:

- `PREFIX_PROCESSED` = `_` (success prefix for delivered files)
- `PREFIX_ERROR` = `!_` (base error prefix; daemon derives error variants from it)

Set per-node in `.jatai` or globally in `~/.jatai`:

```yaml
PREFIX_PROCESSED: "done_"
PREFIX_ERROR: "err_"
```

## Prefix hot-swap and rollback

When you change a prefix in `.jatai`, the daemon automatically renames all
existing historical files in INBOX and OUTBOX to match the new prefix.

If any rename would cause a name collision with an existing file, the daemon aborts
the migration entirely:
- The previous config is restored from `.jatai.bkp`.
- An error notice file is dropped into the node's INBOX describing the collision.

## What the daemon ignores

Files that already have a prefix (any of `_`, `!`, `!_`, `!!`, `!!_`) are skipped
during the delivery scan. This prevents reprocessing of already-handled files.

Nodes in soft-delete state (`._jatai`) are also skipped and do **not** generate
error prefixes for files routed while they are disabled.

## Error notice files

The daemon drops `.md` files with error prefixes into a node's INBOX to communicate
system events:

| Pattern | When dropped |
|---|---|
| `!_config-migration-error*.md` | Prefix migration aborted due to collision |
| `!helloworld.md` | First-time auto-onboarding welcome message |

These files follow the same prefix conventions and can be cleared using the
`jatai clear` command (planned for Phase 6).
