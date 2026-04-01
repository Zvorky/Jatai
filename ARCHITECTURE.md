
# Jataí 🐝 - Architecture Decision Records (ADR)

This document details the Architecture Decision Records (ADR) for the Jataí project.

## [ADR-1] File-System Based Message Bus (Drop-Folder)

* **[ADR-1.1]** Utilize the *drop-folder* pattern. Communication will occur strictly through reading and writing in standardized directories (INBOX/ and OUTBOX/).

## [ADR-2] Synchronization and Immutability Strategy

* **[ADR-2.1]** We reject the use of *Hardlinks* due to their inability to operate across different volumes/partitions. The final choice is the **physical copying of the file** (preserving metadata).

## [ADR-3] Configurable State Machine & Hot-Swap (Prefix Philosophy)

* **[ADR-3.1]** File renaming using *configurable* prefixes dictates the state of messages without a database.
    * **[ADR-3.1.1]** `_` : **Ignore (OUTBOX) / Read (INBOX).** In OUTBOX, means the file has already been delivered to all active nodes (or is being written/ignored by the user). In INBOX, means it was read/processed locally.
    * **[ADR-3.1.2]** `!` : Total error (failed for all nodes), pending retry.
    * **[ADR-3.1.3]** `!_` : Partial error (delivered to some, failed for others), pending retry.
    * **[ADR-3.1.4]** `!!` : Total error, max retries reached (fatal).
    * **[ADR-3.1.5]** `!!_` : Partial error, max retries reached for the failing nodes (fatal).
* **[ADR-3.2]** Hot-Swap & Rollback: Changing the prefix in the `.jatai` file triggers the daemon to rename historical files. Collisions trigger an immediate rollback using a `.bkp` configuration file and an error file drop in the INBOX.
* **[ADR-3.3]** Anti-Heuristic Rule: Jataí must **never** attempt to "guess" or infer past prefixes by scanning directory contents. Prefix migration must rely strictly on the system's cached configurations located in the OS temporary directory (mapped by UUID) or the local `.jatai.bkp`.

## [ADR-4] Configuration vs. System State Separation (The Dual Registry)

* **[ADR-4.1]** **Global User Config (`~/.jatai`):** A pure YAML configuration file. Contains only global default settings and the list of active registered addresses (node paths). It contains **no** system control data.
* **[ADR-4.2]** **Local User Config (`.jatai`):** Stores node-specific metadata overrides. A `.jatai.bkp` is kept locally so users can manually easily rollback if desired.
* **[ADR-4.3]** **System Control State (`/tmp/jatai/`):** All daemon control data, status flags, and caches are stored in the OS temporary directory, formatted as human-readable UTF-8 YAML files.
    * **[ADR-4.3.1]** `uuid_map.yaml`: Maps every registered directory path to a unique UUID (reused if the path is removed and added back).
    * **[ADR-4.3.2]** `removed.yaml`: A list of soft-deleted/disabled addresses. Paths automatically disabled by the system (e.g., local `.jatai` was deleted) receive an `--autoremoved` flag to differentiate them from paths commented out/ignored manually by the user.
    * **[ADR-4.3.3]** `bkp/` subdirectory: Contains a copy of each local node's configuration named by its UUID (e.g., `<UUID>.yaml`). This acts as the ultimate truth cache for the daemon to perform safe prefix migrations without heuristic guessing.
* **[ADR-4.4]** **Automatic Soft-Remove Marking:** When the daemon detects that a registered node's local `.jatai` file no longer exists, the daemon must:
    * **[ADR-4.4.1]** record the node address in `removed.yaml` with the suffix ` --autoremoved` appended to the stored path to indicate an automatic/daemon-triggered soft-delete;
    * **[ADR-4.4.2]** explicitly avoid recreating or reactivating the node directories or files (INBOX/OUTBOX/.jatai) as a result of this detection; reactivation must require an explicit user action (rename/restore or re-register).
        * Note: The `._jatai` marker is an explicit soft-delete artifact and must only be created by user-driven CLI/TUI operations (for example `jatai remove`, which performs `.jatai` → `._jatai`). The daemon must NOT create `._jatai` when a user manually deletes `.jatai` — doing so would contradict the "do not recreate directories and files" policy and may fail if the directory no longer exists or is not writable.
* **[ADR-4.5]** **Overlap Handling & Suggestion:** If a user attempts to configure INBOX and OUTBOX in the exact same directory, Jataí strictly forbids it to avoid infinite broadcast loops. Instead, it will automatically suggest creating two separate subdirectories (e.g., `./dir/INBOX` and `./dir/OUTBOX`) and prompt for the user's interactive confirmation to build them.

## [ADR-5] Event-Driven Execution & OS Integration (Daemon)

* **[ADR-5.1]** The main synchronization engine operates as a background Daemon based on OS file events (using `watchdog`). Upon installation/setup, Jataí must register itself to **auto-start with the Operating System**. It performs a "Startup Scan" on OS boot to process any files dropped during downtime.
* **[ADR-5.2]** Exclusivity (Singleton): The `jatai start` command must implement a PID/Lock file. If another daemon is already running, the second execution fails gracefully ("Already running") to prevent duplicate broadcasts.
* **[ADR-5.3]** OS Auto-Start Constraints: The primary target is Linux with `systemd`. If `systemd` is unavailable or the enablement command fails, the CLI must not fail silently. It must output a clear, explicit warning to the operator indicating that manual auto-start configuration is required.

## [ADR-6] Dynamic Resiliency and Exponential Retry

* **[ADR-6.1]** An exponential retry mechanism managed by a global `~/.retry` state file, calculated dynamically per node: `[Node's RETRY_DELAY_BASE] * (2 ^ retry_index)`.
* **[ADR-6.2]** Max Retries: A strict `MAX_RETRIES` limit exists. Once reached, files transition to `!!` or `!!_` and are no longer retried. Soft-deleted nodes (`._jatai`) are simply ignored and do not count as delivery failures.

## [ADR-7] Data Safety and Controlled Garbage Collection

* **[ADR-7.1]** Jataí will *only* delete files explicitly marked with the success/ignore prefix (`_`).
* **[ADR-7.2]** GC Rules & Triggers:
    * **[ADR-7.2.1]** Defaults: By default, INBOX files are *never* deleted. OUTBOX files have a default limit of `MAX_SENT_FILES = 11` (keeping only the 11 newest files, deleting the oldest).
    * **[ADR-7.2.2]** Deletion Method: By default, files are moved to the OS Trash (Recycle Bin/Trash) to prevent accidental data loss. This can be configured to "permanent delete" via settings.
    * **[ADR-7.2.3]** Execution Intervals: A standard background sweep occurs every 15 minutes to clean up by age. However, when a quantitative limit is reached (e.g., the 11th file in the OUTBOX), the cleanup must trigger **immediately** upon delivery to prevent queue buildup and avoid freezing older HDDs with mass I/O operations.
    * *Scope Note:* This GC strategy is strictly designed for local file systems. In future versions involving network/cloud protocols, these retention rules must be re-evaluated.

## [ADR-8] Documentation as Messages (In-Band Help)

* **[ADR-8.1]** Comprehensive documentation is stored in a `docs/` folder. Users can request documentation via `jatai docs` and `jatai docs {query}` with **terminal-first output** (content rendered directly in CLI). A file-delivery mode remains available via an explicit option (`--inbox`) when users want the documentation materialized in the node INBOX.

## [ADR-9] Atomic Delivery (Preventing Read/Write Race Conditions)

* **[ADR-9.1]** Jataí will perform **Atomic Delivery**. Files are first copied to the destination INBOX using a temporary extension (e.g., `.file.ext.tmp`). Only after the `shutil.copy2` operation is 100% complete, the file is atomically renamed to its final name (`.file.ext`).

## [ADR-10] Name Collision Resolution (INBOX)

* Context: Simultaneous broadcasts from different nodes can result in files with the same name arriving at the same destination INBOX.
* **[ADR-10.1]** If a destination file already exists, Jataí will append a numerical suffix (e.g., `file (1).ext`) to ensure no data is ever overwritten.

## [ADR-11] Process & File Concurrency (Locks & Validation)

* Context: `jatai init` runs as a separate process from the background daemon. Both may attempt to read/write global or local configurations simultaneously.
* **[ADR-11.1]** File Locks: Any read/write operation to the global `~/.jatai` AND the local `.jatai` files must be strictly protected by a `filelock` mechanism to prevent data corruption during concurrent CLI/Daemon access.
* **[ADR-11.2]** Overlap Prevention: The system strictly validates and prevents INBOX and OUTBOX from sharing the same directory path (resolving the conflict interactively via the prompt defined in ADR 4).

## [ADR-12] Terminal-First Operational Retrieval (Logs & Docs)

* Context: (...)
* **[ADR-12.1]** Log Storage & Rotation: Log files are generated in the system temporary directory (`/tmp/jatai/logs/`) using a datetime suffix format (e.g., `jatai_YYYY-MM-DD_HHMMSS.log`).
* **[ADR-12.2]** Latest Log Pointer: The destination path for the `jatai_latest.log` symlink/alias is configurable via the global `~/.jatai` file (e.g., allowing the user to place the latest log shortcut in their `~/` home directory).

## [ADR-13] CLI Short-Option Policy (Abbreviated Flags)

* Context: CLI usability requires consistent, mnemonic abbreviated options to reduce verbosity in scripts and terminal usage.
* **[ADR-13.1]** Adopt a canonical short-option mapping for all optional flags:
    * **[ADR-13.1.1]** `-a` → `--all` : Show/process complete output (e.g., full logs).
    * **[ADR-13.1.2]** `-i` → `--inbox` : Export/process via current node INBOX.
    * **[ADR-13.1.3]** `-m` → `--move` : Move instead of copy after operation.
    * **[ADR-13.1.4]** `-r` → `--read` : Target/clear read (processed) files.
    * **[ADR-13.1.5]** `-s` → `--sent` : Target/clear sent (processed) files.
    * **[ADR-13.1.6]** `-f` → `--foreground` : Run daemon in foreground (diagnostic/hidden use).
    * **[ADR-13.1.7]** `-G` → `--global` : Operate on global configuration (uppercase to emphasize significance).
* **[ADR-13.2]** Restriction: Config key arguments (positional, not flags) are explicitly excluded from short-option mapping to maintain clarity and prevent future key-name ambiguity.
* **[ADR-13.3]** Config Retrieval and Setting Extension:
    * **[ADR-13.3.1]** `jatai config get [key]` is the strict, canonical way to READ a config.
        * The use of the `get` argument is strict and canonical for reading configuration: `jatai config get [key]`.
            * The `[key]` argument is optional: if omitted, the entire config file is returned (local by default, or global if `--global/-G` is specified).
            * The `-i`/`--inbox` flag is the canonical way to export the config retrieval output to the current node INBOX, for both full and partial config retrieval. This applies to `jatai config get`, as well as to documentation and log export commands.
    * **[ADR-13.3.2]** `jatai config [key] [value]` is the strict, canonical way to SET a config. Both arguments are **mandatory**. Executing `jatai config [key]` without a value must return a clear syntax error, explicitly rejecting the attempt to use it as a shortcut for `get`.

## [ADR-14] TUI Architecture and Default Launch Behavior

* Context: The current TUI bootstrap is intentionally minimal and does not yet provide a coherent operator workflow across the existing CLI surface. Jataí is file-system first, but operators still need a productive terminal control plane for inspection, configuration, and operational actions.
* **[ADR-14.1]** The canonical TUI stack for Jataí must be **Textual**.
    * **[ADR-14.1.1]** Why Textual: It supports structured multi-pane terminal applications, background workers, keyboard-first navigation, reactive state updates, and automated UI testing while remaining compatible with Jataí's terminal-first operating model.
    * **[ADR-14.1.2]** Rejected alternatives:
        * `prompt_toolkit`: strong for prompts and line-oriented flows, but too low-level for a full multi-view operations console.
        * `urwid`: mature, but less ergonomic for modern reactive layouts, styling, and testability.
    * **[ADR-14.1.3]** Interaction model:
        * Running `jatai` with no arguments in an interactive terminal must open the TUI.
        * Running `jatai` with no arguments in a non-interactive context must print the CLI help summary instead of attempting to open the TUI.
    * **[ADR-14.1.4]** Command coverage rule: The TUI must expose all existing CLI capabilities through discoverable screens, actions, or dialogs, including status, start/stop, docs, log, list, send, read, unread, config, remove, clear, and future CLI additions.
    * **[ADR-14.1.5]** Implementation rule: The TUI must not reimplement core behavior independently. It must orchestrate the same application services and command handlers used by the regular CLI so terminal and TUI behavior remain aligned.
    * **[ADR-14.1.6]** File-system first constraint: The TUI is an operator layer, not the primary system interface. It must surface filesystem state clearly and never obscure the underlying INBOX/OUTBOX and prefix-based workflow.
    * **[ADR-14.1.7]** Navigation Feature: The TUI officially supports a "Browse Nodes" feature, allowing operators to navigate the local file system and switch context to different registered nodes interactively, avoiding terminal directory lock-in.

## [ADR-15] System-Generated INBOX Artifact Prefix Policy

* Context: Jataí writes some files directly into INBOX as system-generated artifacts (for example onboarding files, exported operational snapshots, or internal notices). These files must be visually distinguishable from user-delivered payload files.
* **[ADR-15.1]** Any file created by Jataí itself inside an INBOX without originating from another node delivery flow must use filename prefix `!`.
* **[ADR-15.2]** Examples in scope:
    * auto-onboarding welcome files;
    * daemon/system notice files;
    * CLI-generated exports to INBOX (for example docs/log/config exports).
* **[ADR-15.3]** Out of scope: Files delivered from other nodes through normal OUTBOX → INBOX routing are not affected by this rule.
* **[ADR-15.4]** Goal: Preserve operator clarity by making system-originated artifacts immediately recognizable in the filesystem-first workflow.