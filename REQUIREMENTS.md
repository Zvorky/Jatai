# **Jataí 🐝 - Technical Requirements**

This document defines the functional and technical requirements for building Jataí.

## **[REQ-1] Technology Stack**

* **[REQ-1.1]** Language: Python 3.8+
* **[REQ-1.2]** Packaging: Distributed as a standard Python package via `pyproject.toml`, exporting `jatai` as a global `console_scripts` entry point.
* **[REQ-1.3]** Standard Libraries (Native): os, shutil, time, logging, pathlib, json.
* **[REQ-1.4]** External Libraries (Approved):
  * **[REQ-1.4.1]** `typer`: For CLI.
  * **[REQ-1.4.2]** `pyyaml`: For YAML configurations.
  * **[REQ-1.4.3]** `watchdog`: For file system events.
  * **[REQ-1.4.4]** `pytest`: For automated testing.
  * **[REQ-1.4.5]** `filelock`: For process concurrency management on configuration files.

## **[REQ-2] State Machine (The Prefix Philosophy)**

Jataí dictates message state via filename prefixes. Base prefixes are configurable, but default to the following exact matrix:

* **[REQ-2.1]** Success/Ignore States:
  * **[REQ-2.1.1]** `_` : **Ignore/Delivered (OUTBOX).** Reached all active nodes, or explicitly marked by the user to be ignored during write.
  * **[REQ-2.1.2]** `_` : **Read (INBOX).** Read/processed locally.
* **[REQ-2.2]** Retry / Error States:
  * **[REQ-2.2.1]** `!` : **Total Error.** Failed to deliver to ALL active nodes. Pending retry.
  * **[REQ-2.2.2]** `!_` : **Partial Error.** Delivered to some nodes, failed for others. Pending retry.
* **[REQ-2.3]** Fatal Error States (Max Retries Reached):
  * **[REQ-2.3.1]** `!!` : **Fatal Total Error.** Failed for all, will no longer retry.
  * **[REQ-2.3.2]** `!!_` : **Fatal Partial Error.** Reached retry limit for the failing nodes.
* **[REQ-2.4]** Pending State:
  * **[REQ-2.4.1]** {No Prefix}: Pending file. Jataí acts immediately.

*Note: Nodes in soft-delete (`._jatai`) are ignored and do NOT generate delivery errors.*

## **[REQ-3] Topology and Configuration**

* **[REQ-3.1]** Node Structure: Configurable input and output subfolders.
* **[REQ-3.2]** Global Registry (`~/.jatai`): YAML file containing absolute paths of all nodes. **Must be protected by a file lock** during reads/writes.
* **[REQ-3.3]** Local Configuration (`.jatai`): Stores node metadata. Backups (`.jatai.bkp`) are maintained for rollback scenarios.

Jataí explicitly separates user configuration from system state.

* **[REQ-3.4]** User Configuration (File-System):
  * **[REQ-3.4.1]** Global Registry (`~/.jatai`): YAML file containing absolute paths of active nodes and global settings. **Must be protected by a filelock.**
  * **[REQ-3.4.2]** Local Configuration (`.jatai`): Stores node metadata. Manual backups (`.jatai.bkp`) are maintained locally. Operations on `.jatai` (save/load) **must also be protected by a filelock**.
* **[REQ-3.5]** System Control State (OS Temporary Directory):
  * **[REQ-3.5.1]** Located at `/tmp/jatai/` (or OS equivalent). Contains UTF-8 YAML files.
  * **[REQ-3.5.2]** `uuid_map.yaml`: Dictionary mapping node paths to unique UUIDs.
  * **[REQ-3.5.3]** `removed.yaml`: List of soft-deleted addresses. Auto-removed addresses are explicitly marked (e.g., via an `--autoremoved` flag or property).
  * **[REQ-3.5.4]** `bkp/<UUID>.yaml`: Cached copies of local node configurations, used by the daemon as the ultimate source of truth for safe prefix rollbacks.

### **[REQ-3.6] Validation & Initialization**
* **[REQ-3.6.1]** Overlap Prevention: `jatai init` and the Daemon must strictly validate that `INBOX_DIR` and `OUTBOX_DIR` are NOT the same path.
* **[REQ-3.6.2]** Collision Handling: If a file being delivered to an INBOX already exists, a numerical suffix (e.g., `(1)`) must be appended.

### **[REQ-3.7] Migration, Removal & Data Retention**
* **[REQ-3.7.1]** Soft-Delete: Renaming `.jatai` to `._jatai` disables the node. The daemon strictly ignores the folder contents, only monitoring the root for reactivation.
* **[REQ-3.7.2]** Automatic Soft-Remove Marking: When the daemon detects that a registered node's local `.jatai` file no longer exists, it must:
  * **[REQ-3.7.2.1]** add the node address to `removed.yaml` using an appended ` --autoremoved` suffix on the stored path to indicate the entry was automatically created by the daemon;
  * **[REQ-3.7.2.2]** explicitly avoid recreating or reactivating the node's directories or files (INBOX/OUTBOX/.jatai) as part of this operation; reactivation requires explicit user action (restore/rename or re-registration).
* **[REQ-3.7.3]** Data Retention & Garbage Collection: Applies only to `_` prefixed files.
  * **[REQ-3.7.3.1]** Defaults: INBOX retains everything (`0` or `null` limit). OUTBOX retains a maximum of 11 files (`GC_MAX_SENT_FILES=11`), deleting the oldest first.
  * **[REQ-3.7.3.2]** Deletion Engine: Uses OS Trash by default. Configurable to hard delete.
  * **[REQ-3.7.3.3]** Triggers: Global sweep every 15 minutes. Immediate local sweep triggered instantly when a quantitative threshold (like the 11 file limit) is hit.

## **[REQ-4] Routing Engine (Daemon & Watchdog)**

* **[REQ-4.1]** Exclusivity: The daemon must implement a PID/Lock file (e.g., `~/.jatai.pid`). Subsequent `jatai start` calls must abort with a friendly "Already running" message.
* **[REQ-4.2]** OS Auto-Start: The daemon registers itself with the host OS (focusing on Linux/systemd). If registration fails or the OS is incompatible, the system must catch the exception and print an explicit warning to the user rather than failing silently.
* **[REQ-4.3]** Startup Scan: Processes pending files on boot.
* **[REQ-4.4]** Real-Time Trigger: `watchdog` listens for file creations/moves in `OUTBOX` folders.

## **[REQ-5] Retry Mechanism (Failure Management)**

* **[REQ-5.1]** Exponential Logic: Delay is `[Node's RETRY_DELAY_BASE] * (2 ^ retry_index)`.
* **[REQ-5.2]** Limits: A `MAX_RETRIES` parameter dictates when a file moves from `!` / `!_` to the fatal `!!` / `!!_` states. The calculation is `1 (Initial Attempt) + MAX_RETRIES (Retries)`.

## **[REQ-6] Observability and Logging**

* **[REQ-6.1]** Exclusive use of the native logging library.
* **[REQ-6.2]** Log Location: All rotated logs with datetime stamps are stored in `/tmp/jatai/logs/`.
* **[REQ-6.3]** Latest Log Pointer: A fixed `jatai_latest.log` shortcut pointing to the current run is maintained. The path for this specific shortcut is user-configurable in the global `~/.jatai` registry.

## **[REQ-7] Automated Testing Strategy**

* **[REQ-7.1]** Framework: `pytest` in `./tests/`.
* **[REQ-7.2]** Must cover lock concurrency, the 5-state prefix matrix, naming collisions, and atomic delivery.

## **[REQ-8] Deep Documentation (`docs/`)**

* **[REQ-8.1]** Handled via `jatai docs` and `jatai docs {query}`.
* **[REQ-8.2]** Default behavior is terminal output (rendered content preview).
* **[REQ-8.3]** `--inbox` option exports selected documentation file(s) to current node INBOX.
* **[REQ-8.4]** Any file generated by Jataí itself into INBOX (without node-to-node delivery origin) must use filename prefix `!`.

## **[REQ-9] CLI and TUI (The Toolbox)**

* **[REQ-9.1]** Initialization: `jatai init [path]` handles node setup. `jatai [path]` acts as a direct alias.
* **[REQ-9.2]** Default no-argument behavior: Running `jatai` with no arguments in an interactive terminal must open the TUI. In non-interactive execution, `jatai` with no arguments must print the CLI help summary.
* **[REQ-9.3]** Operational Retrieval: `jatai log` and `jatai log --all` (`-a`) must be available.
* **[REQ-9.4]** Output Mode Policy: `docs` and `log` are terminal-first and only write files when `--inbox` is explicitly requested.
* **[REQ-9.5]** System-Generated INBOX Prefix Policy: Any CLI/daemon artifact exported or dropped into INBOX by Jataí itself must be prefixed with `!` to differentiate it from node-delivered payload files.
* **[REQ-9.6]** Canonical Short-Option Mapping: All optional flags must support abbreviated forms:
  * **[REQ-9.6.1]** `-a` = `--all`, `-i` = `--inbox`, `-m` = `--move`, `-r` = `--read`, `-s` = `--sent`, `-f` = `--foreground`, `-G` = `--global`.
  * **[REQ-9.6.2]** Config key arguments (positional) explicitly exclude short-option mapping.
  * **[REQ-9.6.3]** (See ADR 13 for full policy and rationale).
* **[REQ-9.7]** Config Operations: `jatai config get [key]` for reading.
  * **[REQ-9.7.1]** `jatai config [key] [value]` for setting. If `value` is missing, the CLI must raise an error.
* **[REQ-9.8]** TUI Framework: The interactive TUI must be implemented with **Textual**.
* **[REQ-9.9]** TUI Coverage: The TUI must provide operator access to all CLI capabilities through interactive views and actions, without reducing the existing CLI command surface.
* **[REQ-9.10]** TUI Consistency Rule: TUI actions must reuse the same underlying application logic as the CLI commands rather than maintaining separate behavior paths.
* **[REQ-9.11]** TUI Context: The TUI includes "Browse Nodes" for interactive directory switching.