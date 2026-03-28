# **Jataí 🐝 - Architecture Decision Records (ADR)**

This document details the Architecture Decision Records (ADR) for the Jataí project.

## **1. File-System Based Message Bus (Drop-Folder)**
* **Decision:** Utilize the *drop-folder* pattern. Communication will occur strictly through reading and writing in standardized directories (INBOX/ and OUTBOX/).

## **2. Synchronization and Immutability Strategy**
* **Decision:** We reject the use of *Hardlinks* due to their inability to operate across different volumes/partitions. The final choice is the **physical copying of the file** (preserving metadata).

## **3. Configurable State Machine & Hot-Swap (Prefix Philosophy)**
* **Decision:** File renaming using *configurable* prefixes dictates the state of messages without a database.
  * `_` : **Ignore (OUTBOX) / Read (INBOX).** In OUTBOX, means the file has already been delivered to all active nodes (or is being written/ignored by the user). In INBOX, means it was read/processed locally.
  * `!` : Total error (failed for all nodes), pending retry.
  * `!_` : Partial error (delivered to some, failed for others), pending retry.
  * `!!` : Total error, max retries reached (fatal).
  * `!!_` : Partial error, max retries reached for the failing nodes (fatal).
* **Hot-Swap & Rollback:** Changing the prefix in the `.jatai` file triggers the daemon to rename historical files. Collisions trigger an immediate rollback using a `.bkp` configuration file and an error file drop in the INBOX.
* **Anti-Heuristic Rule:** Jataí must **never** attempt to "guess" or infer past prefixes by scanning directory contents. Prefix migration must rely strictly on the system's cached configurations located in the OS temporary directory (mapped by UUID) or the local `.jatai.bkp`.

## **4. Configuration vs. System State Separation (The Dual Registry)**
* **Decision:** Jataí strictly separates user-facing configuration from internal daemon control states.
  * **Global User Config (`~/.jatai`):** A pure YAML configuration file. Contains only global default settings and the list of active registered addresses (node paths). It contains **no** system control data.
  * **Local User Config (`.jatai`):** Stores node-specific metadata overrides. A `.jatai.bkp` is kept locally so users can manually easily rollback if desired.
  * **System Control State (`/tmp/jatai/`):** All daemon control data, status flags, and caches are stored in the OS temporary directory, formatted as human-readable UTF-8 YAML files.
    * `uuid_map.yaml`: Maps every registered directory path to a unique UUID (reused if the path is removed and added back).
    * `removed.yaml`: A list of soft-deleted/disabled addresses. Paths automatically disabled by the system (e.g., local `.jatai` was deleted) receive an `--autoremoved` flag to differentiate them from paths commented out/ignored manually by the user.
    * `bkp/` subdirectory: Contains a copy of each local node's configuration named by its UUID (e.g., `<UUID>.yaml`). This acts as the ultimate truth cache for the daemon to perform safe prefix migrations without heuristic guessing.
  * **Overlap Handling & Suggestion:** If a user attempts to configure INBOX and OUTBOX in the exact same directory, Jataí strictly forbids it to avoid infinite broadcast loops. Instead, it will automatically suggest creating two separate subdirectories (e.g., `./dir/INBOX` and `./dir/OUTBOX`) and prompt for the user's interactive confirmation to build them.

## **5. Event-Driven Execution & OS Integration (Daemon)**
* **Decision:** The main synchronization engine operates as a background Daemon based on OS file events (using `watchdog`). Upon installation/setup, Jataí must register itself to **auto-start with the Operating System**. It performs a "Startup Scan" on OS boot to process any files dropped during downtime.
* **Exclusivity (Singleton):** The `jatai start` command must implement a PID/Lock file. If another daemon is already running, the second execution fails gracefully ("Already running") to prevent duplicate broadcasts.
* **OS Auto-Start Constraints:** The primary target is Linux with `systemd`. If `systemd` is unavailable or the enablement command fails, the CLI must not fail silently. It must output a clear, explicit warning to the operator indicating that manual auto-start configuration is required.

## **6. Dynamic Resiliency and Exponential Retry**
* **Decision:** An exponential retry mechanism managed by a global `~/.retry` state file, calculated dynamically per node: `[Node's RETRY_DELAY_BASE] * (2 ^ retry_index)`.
* **Max Retries:** A strict `MAX_RETRIES` limit exists. Once reached, files transition to `!!` or `!!_` and are no longer retried. Soft-deleted nodes (`._jatai`) are simply ignored and do not count as delivery failures.

## **7. Data Safety and Controlled Garbage Collection**
* **Decision:** Jataí will *only* delete files explicitly marked with the success/ignore prefix (`_`).
* **GC Rules & Triggers:**
  * **Defaults:** By default, INBOX files are *never* deleted. OUTBOX files have a default limit of `MAX_SENT_FILES = 11` (keeping only the 11 newest files, deleting the oldest).
  * **Deletion Method:** By default, files are moved to the OS Trash (Recycle Bin/Trash) to prevent accidental data loss. This can be configured to "permanent delete" via settings.
  * **Execution Intervals:** A standard background sweep occurs every 15 minutes to clean up by age. However, when a quantitative limit is reached (e.g., the 11th file in the OUTBOX), the cleanup must trigger **immediately** upon delivery to prevent queue buildup and avoid freezing older HDDs with mass I/O operations.
  * *Scope Note:* This GC strategy is strictly designed for local file systems. In future versions involving network/cloud protocols, these retention rules must be re-evaluated.

## **8. Documentation as Messages (In-Band Help)**
* **Decision:** Comprehensive documentation is stored in a `docs/` folder. Users can request documentation via `jatai docs` and `jatai docs {query}` with **terminal-first output** (content rendered directly in CLI). A file-delivery mode remains available via an explicit option (`--inbox`) when users want the documentation materialized in the node INBOX.

## **9. Atomic Delivery (Preventing Read/Write Race Conditions)**
* **Decision:** Jataí will perform **Atomic Delivery**. Files are first copied to the destination INBOX using a temporary extension (e.g., `.file.ext.tmp`). Only after the `shutil.copy2` operation is 100% complete, the file is atomically renamed to its final name (`.file.ext`).

## **10. Name Collision Resolution (INBOX)**
* **Context:** Simultaneous broadcasts from different nodes can result in files with the same name arriving at the same destination INBOX.
* **Decision:** If a destination file already exists, Jataí will append a numerical suffix (e.g., `file (1).ext`) to ensure no data is ever overwritten.

## **11. Process & File Concurrency (Locks & Validation)**
* **Context:** `jatai init` runs as a separate process from the background daemon. Both may attempt to read/write global or local configurations simultaneously.
* **Decision:** 1. **File Locks:** Any read/write operation to the global `~/.jatai` AND the local `.jatai` files must be strictly protected by a `filelock` mechanism to prevent data corruption during concurrent CLI/Daemon access.
 2. **Overlap Prevention:** The system strictly validates and prevents INBOX and OUTBOX from sharing the same directory path (resolving the conflict interactively via the prompt defined in ADR 4).

## **12. Terminal-First Operational Retrieval (Logs & Docs)**
* **Context:** (...)
* **Log Storage & Rotation:** Log files are generated in the system temporary directory (`/tmp/jatai/logs/`) using a datetime suffix format (e.g., `jatai_YYYY-MM-DD_HHMMSS.log`).
* **Latest Log Pointer:** The destination path for the `jatai_latest.log` symlink/alias is configurable via the global `~/.jatai` file (e.g., allowing the user to place the latest log shortcut in their `~/` home directory).

## **13. CLI Short-Option Policy (Abbreviated Flags)**
* **Context:** CLI usability requires consistent, mnemonic abbreviated options to reduce verbosity in scripts and terminal usage.
* **Decision:** Adopt a canonical short-option mapping for all optional flags:
  * `-a` → `--all` : Show/process complete output (e.g., full logs).
  * `-i` → `--inbox` : Export/process via current node INBOX.
  * `-m` → `--move` : Move instead of copy after operation.
  * `-r` → `--read` : Target/clear read (processed) files.
  * `-s` → `--sent` : Target/clear sent (processed) files.
  * `-f` → `--foreground` : Run daemon in foreground (diagnostic/hidden use).
  * `-G` → `--global` : Operate on global configuration (uppercase to emphasize significance).
* **Restriction:** Config key arguments (positional, not flags) are explicitly excluded from short-option mapping to maintain clarity and prevent future key-name ambiguity.
* **Config Retrieval and Setting Extension:** * `jatai config get [key]` is the strict, canonical way to READ a config.
  * The use of the `get` argument is strict and canonical for reading configuration: `jatai config get [key]`.
    * The `[key]` argument is optional: if omitted, the entire config file is returned (local by default, or global if `--global/-G` is specified).
    * The `-i`/`--inbox` flag is the canonical way to export the config retrieval output to the current node INBOX, for both full and partial config retrieval. This applies to `jatai config get`, as well as to documentation and log export commands.
  * `jatai config [key] [value]` is the strict, canonical way to SET a config. Both arguments are **mandatory**. Executing `jatai config [key]` without a value must return a clear syntax error, explicitly rejecting the attempt to use it as a shortcut for `get`.

## **14. TUI Architecture and Default Launch Behavior**
* **Context:** The current TUI bootstrap is intentionally minimal and does not yet provide a coherent operator workflow across the existing CLI surface. Jataí is file-system first, but operators still need a productive terminal control plane for inspection, configuration, and operational actions.
* **Decision:** The canonical TUI stack for Jataí must be **Textual**.
  * **Why Textual:** It supports structured multi-pane terminal applications, background workers, keyboard-first navigation, reactive state updates, and automated UI testing while remaining compatible with Jataí's terminal-first operating model.
  * **Rejected alternatives:**
    * `prompt_toolkit`: strong for prompts and line-oriented flows, but too low-level for a full multi-view operations console.
    * `urwid`: mature, but less ergonomic for modern reactive layouts, styling, and testability.
* **Interaction model:**
  * Running `jatai` with no arguments in an interactive terminal must open the TUI.
  * Running `jatai` with no arguments in a non-interactive context must print the CLI help summary instead of attempting to open the TUI.
* **Command coverage rule:** The TUI must expose all existing CLI capabilities through discoverable screens, actions, or dialogs, including status, start/stop, docs, log, list, send, read, unread, config, remove, clear, and future CLI additions.
* **Implementation rule:** The TUI must not reimplement core behavior independently. It must orchestrate the same application services and command handlers used by the regular CLI so terminal and TUI behavior remain aligned.
* **File-system first constraint:** The TUI is an operator layer, not the primary system interface. It must surface filesystem state clearly and never obscure the underlying INBOX/OUTBOX and prefix-based workflow.
* **Navigation Feature:** The TUI officially supports a "Browse Nodes" feature, allowing operators to navigate the local file system and switch context to different registered nodes interactively, avoiding terminal directory lock-in.

## **15. System-Generated INBOX Artifact Prefix Policy**
* **Context:** Jataí writes some files directly into INBOX as system-generated artifacts (for example onboarding files, exported operational snapshots, or internal notices). These files must be visually distinguishable from user-delivered payload files.
* **Decision:** Any file created by Jataí itself inside an INBOX without originating from another node delivery flow must use filename prefix `!`.
* **Examples in scope:**
  * auto-onboarding welcome files;
  * daemon/system notice files;
  * CLI-generated exports to INBOX (for example docs/log/config exports).
* **Out of scope:** Files delivered from other nodes through normal OUTBOX → INBOX routing are not affected by this rule.
* **Goal:** Preserve operator clarity by making system-originated artifacts immediately recognizable in the filesystem-first workflow.