# **Jataí 🐝 - Technical Requirements**

This document defines the functional and technical requirements for building Jataí.

## **1. Technology Stack**

* **Language:** Python 3.8+
* **Packaging:** Distributed as a standard Python package via `pyproject.toml`, exporting `jatai` as a global `console_scripts` entry point.
* **Standard Libraries (Native):** os, shutil, time, logging, pathlib, json.
* **External Libraries (Approved):**
  * `typer`: For CLI.
  * `pyyaml`: For YAML configurations.
  * `watchdog`: For file system events.
  * `pytest`: For automated testing.
  * `filelock`: For process concurrency management on configuration files.

## **2. State Machine (The Prefix Philosophy)**

Jataí dictates message state via filename prefixes. Base prefixes are configurable, but default to the following exact matrix:

* **Success/Ignore States:**
  * `_` : **Ignore/Delivered (OUTBOX).** Reached all active nodes, or explicitly marked by the user to be ignored during write.
  * `_` : **Read (INBOX).** Read/processed locally.
* **Retry / Error States:**
  * `!` : **Total Error.** Failed to deliver to ALL active nodes. Pending retry.
  * `!_` : **Partial Error.** Delivered to some nodes, failed for others. Pending retry.
* **Fatal Error States (Max Retries Reached):**
  * `!!` : **Fatal Total Error.** Failed for all, will no longer retry.
  * `!!_` : **Fatal Partial Error.** Reached retry limit for the failing nodes.
* **Pending State:**
  * **{No Prefix}:** Pending file. Jataí acts immediately.

*Note: Nodes in soft-delete (`._jatai`) are ignored and do NOT generate delivery errors.*

## **3. Topology and Configuration**

* **Node Structure:** Configurable input and output subfolders.
* **Global Registry (`~/.jatai`):** YAML file containing absolute paths of all nodes. **Must be protected by a file lock** during reads/writes.
* **Local Configuration (`.jatai`):** Stores node metadata. Backups (`.jatai.bkp`) are maintained for rollback scenarios.

Jataí explicitly separates user configuration from system state.

* **User Configuration (File-System):**
  * **Global Registry (`~/.jatai`):** YAML file containing absolute paths of active nodes and global settings. **Must be protected by a filelock.**
  * **Local Configuration (`.jatai`):** Stores node metadata. Manual backups (`.jatai.bkp`) are maintained locally. Operations on `.jatai` (save/load) **must also be protected by a filelock**.
* **System Control State (OS Temporary Directory):**
  * Located at `/tmp/jatai/` (or OS equivalent). Contains UTF-8 YAML files.
  * `uuid_map.yaml`: Dictionary mapping node paths to unique UUIDs.
  * `removed.yaml`: List of soft-deleted addresses. Auto-removed addresses are explicitly marked (e.g., via an `--autoremoved` flag or property).
  * `bkp/<UUID>.yaml`: Cached copies of local node configurations, used by the daemon as the ultimate source of truth for safe prefix rollbacks.

### **3.1 Validation & Initialization**
* **Overlap Prevention:** `jatai init` and the Daemon must strictly validate that `INBOX_DIR` and `OUTBOX_DIR` are NOT the same path.
* **Collision Handling:** If a file being delivered to an INBOX already exists, a numerical suffix (e.g., `(1)`) must be appended.

### **3.2 Migration, Removal & Data Retention**
* **Soft-Delete:** Renaming `.jatai` to `._jatai` disables the node. The daemon strictly ignores the folder contents, only monitoring the root for reactivation.
* **Automatic Soft-Remove Marking:** When the daemon detects that a registered node's local `.jatai` file no longer exists, it must:
  * add the node address to `removed.yaml` using an appended ` --autoremoved` suffix on the stored path to indicate the entry was automatically created by the daemon;
  * explicitly avoid recreating or reactivating the node's directories or files (INBOX/OUTBOX/.jatai) as part of this operation; reactivation requires explicit user action (restore/rename or re-registration).
* **Data Retention & Garbage Collection:** * Applies *only* to `_` prefixed files.
  * **Defaults:** INBOX retains everything (`0` or `null` limit). OUTBOX retains a maximum of 11 files (`GC_MAX_SENT_FILES=11`), deleting the oldest first.
  * **Deletion Engine:** Uses OS Trash by default. Configurable to hard delete.
  * **Triggers:** Global sweep every 15 minutes. Immediate local sweep triggered instantly when a quantitative threshold (like the 11 file limit) is hit.

## **4. Routing Engine (Daemon & Watchdog)**

* **Exclusivity:** The daemon must implement a PID/Lock file (e.g., `~/.jatai.pid`). Subsequent `jatai start` calls must abort with a friendly "Already running" message.
* **OS Auto-Start:** The daemon registers itself with the host OS (focusing on Linux/systemd). If registration fails or the OS is incompatible, the system must catch the exception and print an explicit warning to the user rather than failing silently.
* **Startup Scan:** Processes pending files on boot.
* **Real-Time Trigger:** `watchdog` listens for file creations/moves in `OUTBOX` folders.

## **5. Retry Mechanism (Failure Management)**

* **Exponential Logic:** Delay is `[Node's RETRY_DELAY_BASE] * (2 ^ retry_index)`. 
* **Limits:** A `MAX_RETRIES` parameter dictates when a file moves from `!` / `!_` to the fatal `!!` / `!!_` states. The calculation is `1 (Initial Attempt) + MAX_RETRIES (Retries)`.

## **6. Observability and Logging**


* Exclusive use of the native logging library.
* **Log Location:** All rotated logs with datetime stamps are stored in `/tmp/jatai/logs/`.
* **Latest Log Pointer:** A fixed `jatai_latest.log` shortcut pointing to the current run is maintained. The path for this specific shortcut is user-configurable in the global `~/.jatai` registry.

## **7. Automated Testing Strategy**

* **Framework:** `pytest` in `./tests/`.
* Must cover lock concurrency, the 5-state prefix matrix, naming collisions, and atomic delivery.

## **8. Deep Documentation (`docs/`)**

* Handled via `jatai docs` and `jatai docs {query}`.
* Default behavior is terminal output (rendered content preview).
* `--inbox` option exports selected documentation file(s) to current node INBOX.
* Any file generated by Jataí itself into INBOX (without node-to-node delivery origin) must use filename prefix `!`.

## **9. CLI and TUI (The Toolbox)**

* **Initialization:** `jatai init [path]` handles node setup. `jatai [path]` acts as a direct alias.
* **Default no-argument behavior:** Running `jatai` with no arguments in an interactive terminal must open the TUI. In non-interactive execution, `jatai` with no arguments must print the CLI help summary.
* **Operational Retrieval:** `jatai log` and `jatai log --all` (`-a`) must be available.
* **Output Mode Policy:** `docs` and `log` are terminal-first and only write files when `--inbox` is explicitly requested.
* **System-Generated INBOX Prefix Policy:** Any CLI/daemon artifact exported or dropped into INBOX by Jataí itself must be prefixed with `!` to differentiate it from node-delivered payload files.
* **Canonical Short-Option Mapping:** All optional flags must support abbreviated forms:
  * `-a` = `--all`, `-i` = `--inbox`, `-m` = `--move`, `-r` = `--read`, `-s` = `--sent`, `-f` = `--foreground`, `-G` = `--global`.
  * Config key arguments (positional) explicitly exclude short-option mapping.
  * (See ADR 13 for full policy and rationale).
* **Config Operations:** * `jatai config get [key]` for reading.
  * `jatai config [key] [value]` for setting. If `value` is missing, the CLI must raise an error.
* **TUI Framework:** The interactive TUI must be implemented with **Textual**.
* **TUI Coverage:** The TUI must provide operator access to all CLI capabilities through interactive views and actions, without reducing the existing CLI command surface.
* **TUI Consistency Rule:** TUI actions must reuse the same underlying application logic as the CLI commands rather than maintaining separate behavior paths.
* **TUI Context:** The TUI includes "Browse Nodes" for interactive directory switching.