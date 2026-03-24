# CLI Reference

Complete reference for all `jatai` commands.

## Node Management

| Command | Description |
|---------|-------------|
| `jatai init [path]` | Initialize a node. Alias: `jatai [path]` |
| `jatai status` | Show INBOX/OUTBOX file counts for the current node |
| `jatai remove [path]` | Disable a node (soft-delete: renames `.jatai` → `._jatai`) |

## Daemon

| Command | Description |
|---------|-------------|
| `jatai start` | Start the background daemon and register OS auto-start |
| `jatai stop` | Stop the background daemon |

## File Operations

| Command | Description |
|---------|-------------|
| `jatai list [addrs\|inbox\|outbox]` | List registered nodes or INBOX/OUTBOX contents |
| `jatai send <file> [--move]` | Copy (or move) a file into the local OUTBOX |
| `jatai read <file>` | Mark an INBOX file as read (adds success prefix `_`) |
| `jatai unread <file>` | Mark an INBOX file as unread (removes success prefix) |
| `jatai clear [inbox\|outbox]` | Delete processed (`_`) files from both or one folder |

## Configuration

| Command | Description |
|---------|-------------|
| `jatai config <key> <value>` | Set a local config value in the current node's `.jatai` |
| `jatai config --global <key> <value>` | Set a global config value in `~/.jatai` |

## Documentation

| Command | Description |
|---------|-------------|
| `jatai docs` | Drop a documentation index into the local INBOX |
| `jatai docs <query>` | Copy matching documentation files into the local INBOX |

## Global Options

| Option | Description |
|--------|-------------|
| `--help` | Show help for any command |
| `--version` | Show the installed version |

## Examples

```bash
# Initialize a node
jatai init ~/projects/agent-a

# Start the routing daemon
jatai start

# List all registered nodes
jatai list addrs

# Send a file to all other nodes
jatai send ~/report.pdf

# Clear delivered files from the OUTBOX
jatai clear outbox

# Set a custom success prefix
jatai config PREFIX_PROCESSED done_

# Fetch architecture docs
jatai docs architecture
```
