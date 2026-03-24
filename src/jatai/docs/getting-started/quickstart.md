# Quick Start Guide

Get up and running with Jataí in minutes.

## 1. Installation

Install Jataí in a virtual environment:

```bash
python3 -m venv venv
. venv/bin/activate
pip install -e .
```

## 2. Initialize Your First Node

```bash
jatai init ~/my-node
```

This creates:
- `~/my-node/INBOX/` — receives files from other nodes
- `~/my-node/OUTBOX/` — drop files here to broadcast them
- `~/my-node/.jatai` — local configuration

## 3. Start the Daemon

```bash
jatai start
```

The daemon watches all registered OUTBOXes and routes files automatically.

## 4. Send Your First Message

Drop any file into the OUTBOX of a node:

```bash
cp message.txt ~/my-node/OUTBOX/
```

Jataí will copy it to the INBOX of every other registered node and rename the
original to `_message.txt` (success prefix) once delivery is complete.

## 5. Check Status

```bash
jatai status
```

## Next Steps

- Read [CLI Reference](../cli/reference.md) for all available commands.
- See [Configuration Options](../configuration/options.md) to customize behavior.
