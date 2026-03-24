# **Jataí 🐝 - Architecture Decision Records (ADR)**

This document details the Architecture Decision Records (ADR) for the Jataí project.

## **1. File-System Based Message Bus (Drop-Folder)**
* **Decision:** Utilize the *drop-folder* pattern. Communication will occur strictly through reading and writing in standardized directories (INBOX/ and OUTBOX/).

## **2. Synchronization and Immutability Strategy**
* **Decision:** We reject the use of *Hardlinks* due to their inability to operate across different volumes/partitions. The final choice is the **physical copying of the file** (preserving metadata).

## **3. Configurable State Machine & Hot-Swap (Prefix Philosophy)**
* **Decision:** File renaming using *configurable* prefixes dictates the state of messages without a database.
  * `_` : Delivered successfully to all active nodes.
  * `!` : Total error (failed for all nodes), pending retry.
  * `!_` : Partial error (delivered to some, failed for others), pending retry.
  * `!!` : Total error, max retries reached (fatal).
  * `!!_` : Partial error, max retries reached for the failing nodes (fatal).
* **Hot-Swap & Rollback:** Changing the prefix in the `.jatai` file triggers the daemon to rename historical files. Collisions trigger an immediate rollback using a `.bkp` configuration file and an error file drop in the INBOX.

## **4. Dual Registry & File-System First Onboarding**
* **Decision:** Jataí uses a dual YAML configuration approach with soft-deletion and auto-creation.
  * **Global (`~/.jatai`):** Stores absolute paths. Adding a path here auto-generates the INBOX/, OUTBOX/, and `.jatai` folders, dropping a `!helloworld.md` tutorial into the new INBOX.
  * **Local (`.jatai` or `._jatai`):** Renaming this file to `._jatai` disables the node (soft-delete). Renaming it back reactivates it (hot-reload).
  * **Overlap Handling & Suggestion:** If a user attempts to configure INBOX and OUTBOX in the exact same directory, Jataí strictly forbids it to avoid infinite broadcast loops. Instead, it will automatically suggest creating two separate subdirectories (e.g., `./dir/INBOX` and `./dir/OUTBOX`) and prompt for the user's interactive confirmation to build them.

## **5. Event-Driven Execution & OS Integration (Daemon)**
* **Decision:** The main synchronization engine operates as a background Daemon based on OS file events (using `watchdog`). Upon installation/setup, Jataí must register itself to **auto-start with the Operating System**. It performs a "Startup Scan" on OS boot to process any files dropped during downtime.
* **Exclusivity (Singleton):** The `jatai start` command must implement a PID/Lock file. If another daemon is already running, the second execution fails gracefully ("Already running") to prevent duplicate broadcasts.

## **6. Dynamic Resiliency and Exponential Retry**
* **Decision:** An exponential retry mechanism managed by a global `~/.retry` state file, calculated dynamically per node: `[Node's RETRY_DELAY_BASE] * (2 ^ retry_index)`.
* **Max Retries:** A strict `MAX_RETRIES` limit exists. Once reached, files transition to `!!` or `!!_` and are no longer retried. Soft-deleted nodes (`._jatai`) are simply ignored and do not count as delivery failures.

## **7. Data Safety and Controlled Garbage Collection**
* **Decision:** Jataí will *only* delete files explicitly marked with the success prefix (`_`). This cleanup can be triggered manually (`jatai clear`) or automatically via configurable retention policies.

## **8. Documentation as Messages (In-Band Help)**
* **Decision:** Comprehensive documentation is stored in a `docs/` folder. Users can request documentation via `jatai docs` and `jatai docs {query}` with **terminal-first output** (content rendered directly in CLI). A file-delivery mode remains available via an explicit option (`--inbox`) when users want the documentation materialized in the node INBOX.

## **9. Atomic Delivery (Preventing Read/Write Race Conditions)**
* **Decision:** Jataí will perform **Atomic Delivery**. Files are first copied to the destination INBOX using a temporary extension (e.g., `.file.ext.tmp`). Only after the `shutil.copy2` operation is 100% complete, the file is atomically renamed to its final name (`.file.ext`).

## **10. Name Collision Resolution (INBOX)**
* **Context:** Simultaneous broadcasts from different nodes can result in files with the same name arriving at the same destination INBOX.
* **Decision:** If a destination file already exists, Jataí will append a numerical suffix (e.g., `file (1).ext`) to ensure no data is ever overwritten.

## **11. Process & File Concurrency (Locks & Validation)**
* **Context:** `jatai init` runs as a separate process from the background daemon. Both may attempt to read/write `~/.jatai` simultaneously. Also, users might try to point INBOX and OUTBOX to the exact same folder.
* **Decision:** 1. **File Locks:** Any read/write operation to `~/.jatai` must be protected by a strict file lock mechanism to prevent corruption.
  2. **Overlap Prevention:** The system strictly validates and prevents INBOX and OUTBOX from sharing the same directory path (resolving the conflict interactively via the prompt defined in ADR 4).

## **12. Terminal-First Operational Retrieval (Logs & Docs)**
* **Context:** Operators need quick inspection of runtime logs and documentation without forcing file drops into node folders.
* **Decision:** Jataí CLI adopts a **terminal-first retrieval model** for operational content:
  * `jatai log` returns the latest log entry set in terminal output.
  * `jatai log --all` (or `jatai log -a`) returns the complete log stream (or paginated/streamed output).
  * `jatai docs` and `jatai docs {query}` return documentation content in terminal output by default.
  * Both log and docs commands support an explicit `--inbox` option to export the retrieved content as file(s) into the current node INBOX when persistence/share is needed.