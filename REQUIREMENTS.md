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

* **Success States:**
  * `_` : **Delivered.** In OUTBOX, it reached all active nodes. In INBOX, it was read/processed locally.
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

### **3.1 Validation & Initialization**
* **Overlap Prevention:** `jatai init` and the Daemon must strictly validate that `INBOX_DIR` and `OUTBOX_DIR` are NOT the same path.
* **Collision Handling:** If a file being delivered to an INBOX already exists, a numerical suffix (e.g., `(1)`) must be appended.

### **3.2 Migration, Removal & Data Retention**
* **Soft-Delete:** Renaming `.jatai` to `._jatai` disables the node. The daemon strictly ignores the folder contents, only monitoring the root for reactivation.
* **Data Retention:** Manual (`jatai clear`) or automatic cleanup applies *only* to successfully processed files (`_`).

## **4. Routing Engine (Daemon & Watchdog)**

* **Exclusivity:** The daemon must implement a PID/Lock file (e.g., `~/.jatai.pid`). Subsequent `jatai start` calls must abort with a friendly "Already running" message.
* **OS Auto-Start:** The daemon registers itself with the host OS to run silently in the background.
* **Startup Scan:** Processes pending files on boot.
* **Real-Time Trigger:** `watchdog` listens for file creations/moves in `OUTBOX` folders.

## **5. Retry Mechanism (Failure Management)**

* **Exponential Logic:** Delay is `[Node's RETRY_DELAY_BASE] * (2 ^ retry_index)`. 
* **Limits:** A `MAX_RETRIES` parameter dictates when a file moves from `!` / `!_` to the fatal `!!` / `!!_` states.

## **6. Observability and Logging**

* Exclusive use of the native logging library (`~/.jatai.log`).
* CLI retrieval must support:
  * `jatai log` for latest log output in terminal.
  * `jatai log --all` (or `jatai log -a`) for complete log output in terminal.
* Log retrieval commands must support `--inbox` to export the rendered result to current node INBOX.

## **7. Automated Testing Strategy**

* **Framework:** `pytest` in `./tests/`.
* Must cover lock concurrency, the 5-state prefix matrix, naming collisions, and atomic delivery.

## **8. Deep Documentation (`docs/`)**

* Handled via `jatai docs` and `jatai docs {query}`.
* Default behavior is terminal output (rendered content preview).
* `--inbox` option exports selected documentation file(s) to current node INBOX.

## **9. CLI and TUI (The Toolbox)**

* **Initialization:** `jatai init [path]` handles node setup. `jatai [path]` acts as a direct alias.
* **Operational Retrieval:** `jatai log` and `jatai log --all` (`-a`) must be available.
* **Output Mode Policy:** `docs` and `log` are terminal-first and only write files when `--inbox` is explicitly requested.
* **Canonical Short-Option Mapping:** All optional flags must support abbreviated forms:
  * `-a` = `--all`, `-i` = `--inbox`, `-m` = `--move`, `-r` = `--read`, `-s` = `--sent`, `-f` = `--foreground`, `-G` = `--global`.
  * Config key arguments (positional) explicitly exclude short-option mapping.
  * (See ADR 13 for full policy and rationale).
*(Refer to the README for the full CLI command table).*