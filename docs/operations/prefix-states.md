# Prefix State Machine

This document describes the state machine based on Jataí's file prefix philosophy.

## State Transitions

Jataí uses filename prefixes to track the state of messages in INBOX and OUTBOX.

```mermaid
sequenceDiagram
    participant User
    participant OUTBOX (Node A)
    participant Jatai Daemon
    participant INBOX (Node B)

    User->>OUTBOX (Node A): Drop file.txt
    Jatai Daemon->>OUTBOX (Node A): Detect file.txt
    Jatai Daemon->>INBOX (Node B): Copy as .file.txt.tmp
    Jatai Daemon->>INBOX (Node B): Rename to file.txt
    Jatai Daemon->>OUTBOX (Node A): Rename to _file.txt (Ignored/Sent)
```

## Retry and Recovery Flows

When a delivery fails, Jataí enters a retry state and uses exponential backoff.

```mermaid
sequenceDiagram
    participant Jatai Daemon
    participant OUTBOX (Node A)
    participant INBOX (Offline Node)

    Jatai Daemon->>INBOX (Offline Node): Attempt Delivery (file.txt)
    INBOX (Offline Node)-->>Jatai Daemon: Delivery Failed (I/O Error)
    Jatai Daemon->>OUTBOX (Node A): Rename to !file.txt (Total Error)
    
    loop Exponential Backoff
        Jatai Daemon->>INBOX (Offline Node): Retry Delivery (!file.txt)
        INBOX (Offline Node)-->>Jatai Daemon: Delivery Failed
    end
    
    Jatai Daemon->>OUTBOX (Node A): Max retries reached
    Jatai Daemon->>OUTBOX (Node A): Rename to !!file.txt (Fatal Error)
```

## Orphaned Directories Recovery

When a `.jatai` configuration is removed, the node becomes an orphaned directory and goes into soft-delete. Reactivation requires user intervention.

```mermaid
sequenceDiagram
    participant User
    participant Node
    participant Jatai Daemon
    participant /tmp/jatai/

    User->>Node: Delete .jatai
    Jatai Daemon->>Node: Detect missing .jatai
    Jatai Daemon->>/tmp/jatai/: Add to removed.yaml (--autoremoved)
    Jatai Daemon->>Node: Ignore node operations
    
    User->>Node: Create new .jatai or jatai init
    Jatai Daemon->>Node: Detect new .jatai
    Jatai Daemon->>/tmp/jatai/: Remove from removed.yaml
    Jatai Daemon->>Node: Resume normal operations
```
