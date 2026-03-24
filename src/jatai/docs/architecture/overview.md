# Architecture Overview

Jataí is built around a small set of composable principles.

## Core Concepts

### Drop-Folder Pattern

Communication happens entirely through the file system. Every node has:
- **INBOX**: Receives files from other nodes.
- **OUTBOX**: Publishes files to all other nodes.

No network stack, no API, no database — just files.

### Dual Registry

- **Global registry** (`~/.jatai`): Lists all node paths. Protected by a file
  lock to prevent corruption during concurrent access.
- **Local config** (`.jatai`): Per-node overrides for prefixes, directories,
  and retry parameters.

### State Machine via Prefixes

File state is encoded in the filename prefix:

| Prefix | State | Meaning |
|--------|-------|---------|
| *(none)* | Pending | Not yet processed |
| `_` | Processed | Delivered to all nodes |
| `!` | Error (total) | Failed for all nodes, retry pending |
| `!_` | Error (partial) | Delivered to some, failed for others |
| `!!` | Fatal (total) | Max retries reached, all nodes |
| `!!_` | Fatal (partial) | Max retries reached, some nodes |

Prefixes are configurable per node.

### Atomic Delivery

Files are copied using a `.tmp` extension during transfer, then atomically
renamed to their final name. This prevents partial reads by receiving processes.

### Event-Driven Daemon

The background daemon uses `watchdog` to listen for file creation and move
events in registered OUTBOXes. On startup it performs a scan to process any
files dropped during downtime.

### Exponential Retry

Failed deliveries are retried with exponential backoff:
```
delay = RETRY_DELAY_BASE * (2 ^ retry_index)
```

After `MAX_RETRIES` failures, the file is marked with the fatal prefix (`!!`)
and retrying stops.

### Soft-Delete & Hot-Reload

Renaming `.jatai` to `._jatai` disables a node without deleting any data.
Renaming it back reactivates the node. The daemon monitors node roots for
these changes and responds in real time.

## Further Reading

- [Architecture Decision Records](../../../../ARCHITECTURE.md)
- [Technical Requirements](../../../../REQUIREMENTS.md)
