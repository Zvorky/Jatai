# CLI Reference

Complete reference for all Jataí command-line commands.

## Currently implemented commands

### `jatai init [path]`

Initialize a directory as a Jataí node.

```bash
jatai init                  # initializes the current directory
jatai init ./my-project     # initializes an explicit path
jatai ./my-project          # shorthand alias, equivalent to jatai init <path>
```

Creates:
- `INBOX/` — incoming messages
- `OUTBOX/` — messages to broadcast
- `.jatai` — local configuration file
- `INBOX/!helloworld.md` — onboarding tutorial

Registers the node in the global registry (`~/.jatai`). Fails with a friendly
message if `INBOX_DIR` and `OUTBOX_DIR` would resolve to the same path.

If a user manually deletes `.jatai` from an already registered node directory,
daemon maintenance records the path in `/tmp/jatai/removed.yaml` with
`--autoremoved` and does not recreate `.jatai`, `._jatai`, `INBOX`, or `OUTBOX`.

---

### `jatai status`

Show file counts for the current node.

```bash
cd my-project
jatai status
```

Output example:
```
Node:   /home/user/my-project
Config: /home/user/my-project/.jatai
INBOX:  3 file(s)
OUTBOX: 1 file(s)
```

Must be run from a directory that is an active Jataí node (has `.jatai`).

---

### `jatai start`

Start the background daemon and register it for OS auto-start.

```bash
jatai start
```

- Performs a startup scan to process any pending files from downtime.
- Registers for systemd auto-start on Linux, launchd on macOS.
- Fails gracefully if a daemon is already running.

---

### `jatai stop`

Stop the background daemon.

```bash
jatai stop
```

Sends `SIGTERM` and waits up to 5 seconds for the process to exit.

---

### `jatai docs [query] [-i|--inbox]`

Show documentation in terminal by default. Optionally export to the current
node `INBOX/`.

```bash
# Print docs category index in terminal
jatai docs

# Print matching docs in terminal
jatai docs retry
jatai docs configuration
jatai docs prefix
jatai docs security

# Export docs index to INBOX
jatai docs -i

# Export matching docs to INBOX
jatai docs retry -i
```

The query matches against the file name and path (case-insensitive substring).
With `--inbox`, all matching `.md` files from the `docs/` tree are copied to the
node's `INBOX` with the `!` prefix applied, marking them as system-generated
artifacts (for example `!retry-and-health.md`, `!quickstart.md`).

---

### `jatai log [-a|--all] [-i|--inbox]`

Inspect daemon logs in terminal, optionally exporting the rendered output to INBOX.

```bash
# Last log lines in terminal
jatai log

# Full log output in terminal
jatai log -a

# Export latest log snapshot to INBOX
jatai log -i

# Export full log to INBOX
jatai log -a -i
```

---

### `jatai list [addrs|inbox|outbox]`

List addresses from global registry or file names from the current node INBOX/OUTBOX.

```bash
jatai list addrs
jatai list inbox
jatai list outbox
```

When using `addrs`, output starts with the registry source path:

```text
# registry: /home/user/.jatai
my-node: /home/user/my-node
```

---

### `jatai send <file> [-m|--move]`

Enqueue an external file into the current node OUTBOX.

```bash
# Copy file into OUTBOX
jatai send /tmp/note.txt

# Move file into OUTBOX (source is deleted)
jatai send /tmp/note.txt -m
```

---

### `jatai read <file>` and `jatai unread <file>`

Mark INBOX files as read/unread by adding or removing the success prefix.

```bash
jatai read message.txt
jatai unread _message.txt
```

---

### `jatai config [key] [value] [-G|--global]`

Write config values locally (default) or globally.

```bash
# Write a key
jatai config MAX_RETRIES 5
jatai config -G MAX_RETRIES 5
```

Config keys are positional arguments and intentionally do not have short-option aliases.

If `value` is missing, the command fails with a syntax error and instructs the
operator to use `jatai config get [key]` for reads.

### `jatai config get [key] [-G|--global] [-i|--inbox]`

Read-only config retrieval for local/global scope.

```bash
# Show full local config
jatai config get

# Show one local key
jatai config get MAX_RETRIES

# Show full global config
jatai config get -G

# Show one global key
jatai config get MAX_RETRIES -G

# Export rendered output to current node INBOX
jatai config get -i
jatai config get PREFIX_IGNORE -i
```

Behavior:

- default scope is local node config
- `-G|--global` switches scope to global registry config
- `-i|--inbox` exports output into the current node INBOX
- missing key returns a clear error

When printing to terminal (without `--inbox`), output starts with `# source: ...`
showing the exact config file used. INBOX exports keep only the rendered config
content.

---

### `jatai remove [path]`

Soft-delete a node by renaming `.jatai` to `._jatai`.

```bash
jatai remove
jatai remove /path/to/node
```

---

### `jatai clear [-r|--read] [-s|--sent]`

Clear processed (`_`-prefixed) files from INBOX and/or OUTBOX.

```bash
# Clear both INBOX and OUTBOX processed history
jatai clear

# Clear only INBOX processed files
jatai clear -r

# Clear only OUTBOX processed files
jatai clear -s
```

---

### `jatai cleanup --full [--dry-run] [--remove-logs] [-y|--yes]`

Optional helper to prepare complete uninstall cleanup.

```bash
# Preview what would be removed
jatai cleanup --full --dry-run

# Apply cleanup (with interactive confirmation)
jatai cleanup --full

# Apply cleanup non-interactively and also remove logs
jatai cleanup --full --remove-logs --yes
```

Behavior:

- preserves INBOX/OUTBOX payload contents
- removes local `.jatai` / `._jatai` from known nodes
- removes global `~/.jatai`
- removes control-state under `/tmp/jatai/` (logs preserved unless `--remove-logs`)

---

## Short-option policy

Canonical mapping:

- `-a` = `--all`
- `-i` = `--inbox`
- `-m` = `--move`
- `-r` = `--read`
- `-s` = `--sent`
- `-f` = `--foreground`
- `-G` = `--global`
- `-d` = `--dry-run`
- `-l` = `--remove-logs`
- `-y` = `--yes`

---

## Interactive TUI

Running `jatai` with no arguments in an interactive terminal opens the
**Textual**-powered TUI. In non-interactive execution (scripts, cron jobs),
`jatai` without arguments prints the CLI help summary instead.

The TUI exposes all CLI commands through a two-pane layout:
- Left pane: scrollable command menu (16 actions, keyboard or mouse selection)
- Right pane: command output display

Actions available in the TUI:
`init node`, `status`, `docs index`, `docs query`, `log latest`, `log all`, `list`,
`send file`, `read file`, `unread file`, `config get`, `config set`,
`remove node`, `clear processed`, `start daemon`, `stop daemon`.

Press `Q` to quit. The TUI opens modal input dialogs for commands that require
parameters (e.g. query text, file paths, config keys).
