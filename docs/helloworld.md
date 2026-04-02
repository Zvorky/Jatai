# !helloworld.md

> Note: this file is written by Jatai into a node INBOX during explicit node initialization flows such as `jatai init`.

Welcome to Jatai.

Your node is ready to use. Jatai is file-system first: drop files in OUTBOX to broadcast, and read files from INBOX.

## Quick next steps

1. Check your node status:

```bash
jatai status
```

2. Start the daemon:

```bash
jatai start
```

3. Read docs in terminal:

```bash
jatai docs
jatai docs quickstart
```

4. Open the interactive TUI (run `jatai` with no arguments in a terminal):

```bash
jatai
```

5. Mark a file as read and clean up processed history:

```bash
jatai read message.txt     # adds _ prefix to file in INBOX
jatai clear                # removes all _-prefixed files from INBOX and OUTBOX
```

6. Disable this node temporarily (re-enable by renaming `._jatai` back to `.jatai`):

```bash
jatai remove
```

7. Export docs to your INBOX when needed:

```bash
jatai docs -i
jatai docs quickstart -i
```

## Documentation map

- `docs/getting-started/quickstart.md`
- `docs/getting-started/configuration.md`
- `docs/operations/cli-reference.md`
- `docs/operations/prefix-states.md`
- `docs/operations/retry-and-health.md`
- `docs/operations/garbage-collection.md`
- `docs/security/safe-operations.md`

## Repository

- GitHub: <https://github.com/Zvorky/Jatai>
