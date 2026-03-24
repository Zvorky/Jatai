# Retry and Health

Jataí is resilient by design. When a delivery fails (e.g., disk error, locked file),
files are not lost — they are marked and retried automatically using exponential
backoff.

## Retry state file

Retry metadata is persisted in `~/.retry` (JSON), protected by a file lock.
The daemon reads and updates this file on every delivery attempt.

## Exponential backoff formula

The delay between retries grows exponentially per node:

```
delay = RETRY_DELAY_BASE * (2 ^ (retry_index - 1))
```

Default `RETRY_DELAY_BASE` is **60 seconds**. With the default `MAX_RETRIES = 3`:

| Attempt | Delay       |
|---------|-------------|
| 1st     | 60 seconds  |
| 2nd     | 120 seconds |
| 3rd     | fatal       |

Each node can override these values independently via its local `.jatai` config.

## Prefix state transitions on failure

Files in `OUTBOX` are renamed using prefix markers that encode their delivery state.
On failure, the daemon applies an error prefix before scheduling the retry:

| State       | Prefix | Meaning                                                      |
|-------------|--------|--------------------------------------------------------------|
| Pending     | _(none)_ | Unprocessed — daemon will act immediately                  |
| Error       | `!`    | Total failure (all nodes), pending retry                     |
| Partial     | `!_`   | Partial failure (some nodes), pending retry                  |
| Fatal total | `!!`   | Max retries reached, all nodes failed                        |
| Fatal part. | `!!_`  | Max retries reached, some nodes failed                       |
| Delivered   | `_`    | Successfully broadcast to all active nodes                   |

Files with `!!` or `!!_` are **not retried further**. They stay in OUTBOX as a
permanent record that delivery failed. See [Prefix States](prefix-states.md) for
the full reference.

## Soft-deleted nodes are not counted as failures

A node disabled by renaming `.jatai` to `._jatai` is simply skipped during
delivery. It does not generate error prefixes for files routed while it is
inactive.

## Monitoring with the log file

The daemon writes all delivery events — successes, failures, retries, and
onboarding events — to `~/.jatai.log`.

Log format:
```
2026-03-23 12:00:00,123 INFO Delivery succeeded: /home/user/node_a/OUTBOX/msg.txt
2026-03-23 12:00:05,456 WARNING Delivery failed: /home/user/node_a/OUTBOX/msg.txt
```

To follow the log in real time:
```bash
tail -f ~/.jatai.log
```

To inspect the retry state file directly:
```bash
cat ~/.retry
```

> **Future:** `jatai status` and `jatai list` commands will surface file counts and
> delivery states inline in the terminal without needing to read raw files.
