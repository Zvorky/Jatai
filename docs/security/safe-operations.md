# Safe Operations

Jataí is designed for local-first communication with deterministic, non-destructive
file operations. This document describes the safety model and hardening
recommendations.

## Data safety model

Jataí **never deletes pending or unprocessed files**. The only files eligible for
delete are those already marked with the success prefix (`_`), and only when
explicitly triggered.

## Atomic delivery

Files are never written directly to an INBOX. The delivery sequence is:

1. Copy file to `INBOX/.filename.ext.tmp`
2. After copy completes, rename to `INBOX/filename.ext`

## Name collision safety

If a file with the same name already exists in the destination INBOX, Jataí
appends a numerical suffix rather than overwriting.

## Overlap prevention

Jataí refuses to operate if `INBOX_DIR` and `OUTBOX_DIR` resolve to the same path.

## Registry access control

The global registry (`~/.jatai`) is protected by a file lock on every read and
write. Concurrent processes (daemon + CLI) cannot corrupt it through simultaneous
access.

## Node local config locking

Local node configs (`.jatai`, `._jatai`) are protected by a file lock
(`.jatai.lock`) when saving/loading, preventing simultaneous process races.

