# Safe Operations

Jataí is designed for local-first communication with deterministic, non-destructive
file operations. This document describes the safety model and hardening
recommendations.

## Data safety model

Jataí **never deletes pending or unprocessed files**. The only files eligible for
deletion are those already marked with the success prefix (`_`), and only when
explicitly triggered:

- **Manually:** via `jatai clear` — removes `_`-prefixed files from INBOX and/or
  OUTBOX on demand.
- **Automatically:** via configurable retention limits (`GC_MAX_READ_FILES` and
  `GC_MAX_SENT_FILES`). Set either to `0` (the default) to disable auto-cleanup.
  See [Garbage Collection](../operations/garbage-collection.md) for details.

All other state transitions are renames, not deletions.

## Atomic delivery

Files are never written directly to an INBOX. The delivery sequence is:

1. Copy file to `INBOX/.filename.ext.tmp`
2. Only after `shutil.copy2` completes, rename to `INBOX/filename.ext`

This prevents any consumer from reading a partially written file.

## Name collision safety

If a file with the same name already exists in the destination INBOX, Jataí
appends a numerical suffix rather than overwriting:

```
message.txt      ← first delivery
message (1).txt  ← collision resolved
message (2).txt  ← second collision
```

## Overlap prevention

Jataí refuses to operate if `INBOX_DIR` and `OUTBOX_DIR` resolve to the same path.
This would cause infinite broadcast loops. If the overlap is detected during
`jatai init`, an interactive prompt suggests separate subdirectories.

## Registry access control

The global registry (`~/.jatai`) is protected by a file lock on every read and
write. Concurrent processes (daemon + CLI) cannot corrupt it through simultaneous
access.

## Recommendations

- **Do not run Jataí with root or elevated privileges.** All files are user-owned
  and should remain that way.
- **Keep node folders under user-owned paths.** Avoid placing INBOX or OUTBOX under
  system directories.
- **Do not symlink INBOX or OUTBOX to sensitive directories.** Jataí resolves paths
  and copies files without special symlink guards beyond what the OS provides.
- **Validate entries before adding them manually to `~/.jatai`.** Auto-onboarding
  will attempt to create directories for any path in the registry at daemon startup.

## Hardening checklist

- [ ] Daemon runs as an unprivileged user.
- [ ] Node paths are under `$HOME` or equivalent user-owned locations.
- [ ] `~/.jatai`, `~/.retry`, and `~/.jatai.log` have `600` permissions.
- [ ] Review `~/.jatai.log` periodically for unexpected errors or delivery failures.
- [ ] Dependencies (`pyyaml`, `watchdog`, `filelock`, `typer`) are kept up to date.

## File permission note

Jataí does not currently enforce file permission checks on registry entries. The
operator is responsible for ensuring that paths added to `~/.jatai` are
appropriate for the running user.

