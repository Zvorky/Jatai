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

Registers the node in the global registry (`~/.jatai`). Fails with a friendly
message if `INBOX_DIR` and `OUTBOX_DIR` would resolve to the same path.

---

### `jatai status`

Show file counts for the current node.

```bash
cd my-project
jatai status
```

Output example:
```
Node: /home/user/my-project
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

### `jatai docs [query]`

Deliver documentation files into the current node's `INBOX/`.

```bash
# Drop a docs category index as !docs-index.md in INBOX
jatai docs

# Copy docs matching a keyword into INBOX
jatai docs retry
jatai docs configuration
jatai docs prefix
jatai docs security
```

The query matches against the file name and path (case-insensitive substring).
All matching `.md` files from the `docs/` tree are copied to the node's `INBOX`.

---

## Planned commands (Phase 6+)

The following commands are planned for upcoming phases. They are not yet implemented.

| Command | Action |
|---|---|
| `jatai config [--global] <key> <val>` | Set a config key locally or in the global registry |
| `jatai list [addrs\|inbox\|outbox]` | List files in node or all registered nodes |
| `jatai send <file> [--move]` | Copy (or move) a file into the current OUTBOX |
| `jatai read <file>` | Mark a file in INBOX as read (adds success prefix) |
| `jatai unread <file>` | Remove the success prefix from an INBOX file |
| `jatai remove [path]` | Soft-delete a node (rename `.jatai` → `._jatai`) |
| `jatai clear [inbox\|outbox]` | Delete processed (`_`-prefixed) history files |

> **Future:** Bare `jatai` with no arguments will open an interactive TUI. Currently
> it shows the help screen.
