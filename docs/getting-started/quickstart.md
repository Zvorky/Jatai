# Quickstart

Jataí is a local micro-messaging bus for your file system. It routes files between
directories — called **nodes** — using a zero-config drop-folder pattern. No APIs,
no sockets: drop a file in OUTBOX, and it arrives in every other node's INBOX.

## Installation

Jataí requires Python 3.8+ and is installed in editable mode from source (not yet
on PyPI):

```bash
python3 -m venv venv
. venv/bin/activate
pip install -e .
```

## Setting up a node

A **node** is any directory registered with Jataí. It gets two subfolders:
`INBOX/` (incoming messages) and `OUTBOX/` (messages to broadcast).

```bash
# Initialize the current directory as a node
jatai init

# Or initialize an explicit path
jatai init ./my-project

# Shorthand alias (same as jatai init <path>)
jatai ./my-project
```

After initialization, the node directory contains:

```
my-project/
├── INBOX/
├── OUTBOX/
└── .jatai       ← local configuration
```

Jataí also drops `!helloworld.md` into `INBOX/` as the first onboarding
message for the node.

## Starting the daemon

The daemon watches all registered nodes and routes files in real time:

```bash
jatai start
```

The daemon registers itself for OS auto-start (systemd on Linux). It also performs
a **startup scan** on launch to process any files dropped while it was offline.

To stop it:

```bash
jatai stop
```

## Sending and receiving

**Send:** drop any file into a node's `OUTBOX/`. The daemon copies it to every
other active node's `INBOX/` automatically.

**Receive:** read from your `INBOX/`. Jataí never deletes pending files — they stay
until you process them.

## Checking status

```bash
cd my-project
jatai status
```

Shows the count of files in `INBOX` and `OUTBOX` for the current node.
The output also shows the active local config file path (`.jatai`) so operators
can quickly confirm which directory and config are active.

## Auto-onboarding

If you manually add a path to the global registry (`~/.jatai`) without running
`jatai init`, Jataí creates the missing structure automatically the next time the
daemon starts. A `!helloworld.md` tutorial file is dropped in the new node's
`INBOX` on first onboarding.

If `.jatai` is manually deleted from an existing registered node directory,
daemon maintenance creates `._jatai` to keep the node in soft-delete state
instead of silently recreating it as active.

## Reading documentation and logs in-band

Show a category index of all available docs directly in terminal:

```bash
cd my-project
jatai docs
```

Copy docs to INBOX only when explicitly requested:

```bash
jatai docs -i
jatai docs retry -i
```

Inspect logs in terminal:

```bash
jatai log
jatai log -a
```

Export logs to INBOX:

```bash
jatai log -i
jatai log -a -i
```

Global config updates use uppercase short flag by policy:

```bash
jatai config -G MAX_RETRIES 5
```

## .gitignore recommendations

Add these lines to your project's `.gitignore` to avoid committing Jataí artifacts:

```gitignore
INBOX/
OUTBOX/
# .jatai   ← omit this line if you want to commit node settings
```

## Next steps

- [Configuration reference](configuration.md) — customize prefixes, retry logic, folder names, and garbage collection limits
- [Prefix states](../operations/prefix-states.md) — understand what `_`, `!`, `!!` mean
- [Retry and health](../operations/retry-and-health.md) — how failures are handled
- [Garbage collection](../operations/garbage-collection.md) — manual and automatic cleanup of processed files
- [CLI reference](../operations/cli-reference.md) — full command-line reference

> Running `jatai` with no arguments opens the **Textual**-powered interactive TUI
> in a terminal session. In non-interactive usage (scripts, cron), the same
> command prints the CLI help summary.
>
> The TUI provides a two-pane layout: a scrollable command menu on the left and
> a live output display on the right. It covers the full CLI command set,
> including node initialization and alpha directory navigation between
> registered nodes.
