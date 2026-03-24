# **Jataí 🐝 - Implementation Roadmap & To-Do List**

This document organizes the planned development phases for Jataí, ordered by priority.

## **Phase 1: Core Foundation & Basic CLI**

The absolute minimum required to route files safely between folders.

- [x] Set up Python project structure (`core/`, `cli/`, `tests/`).
- [x] Configure `pyproject.toml` with `console_scripts` entry point to expose `jatai` globally via pip.
- [x] Set up pytest framework and write first dummy test.
- [x] Implement typer base setup.
- [x] Write unit tests for global registry parsing (`~/.jatai`).
- [x] Implement `filelock` for concurrent-safe reading/writing of the global registry (`~/.jatai`).
- [x] Create `jatai init [path]` command (and its `jatai [path]` alias) to initialize INBOX/, OUTBOX/, and .jatai.
- [x] Implement path validation forbidding INBOX/OUTBOX overlap, adding an interactive prompt to suggest and create separate subdirectories.
- [x] Implement physical file copying logic (`shutil.copy2`) using **Atomic Delivery** (temporary .tmp extension during copy).
- [x] Implement name collision resolution (appending numerical suffixes like `(1)` to duplicates in INBOX).
- [x] Implement the success prefix logic (adding `_` to processed OUTBOX files).
- [x] Implement `jatai status` command showing node state (INBOX/OUTBOX file counts).
- [x] Write unit tests for genuine concurrent `filelock` contention on `~/.jatai` using threading (REQ §7 — lock concurrency coverage beyond simulation).

## **Phase 2: The Routing Engine (Daemon & Watchdog)**

Making the system reactive and background-driven.

- [x] Implement `jatai start` and `jatai stop` logic.
- [x] Implement **Daemon Exclusivity**: Use a PID/Lock file to gracefully reject duplicate `start` commands.
- [x] Implement **OS Auto-Start Registration** logic (systemd, launchd, or startup folder mapping).
- [x] Implement the **Startup Scan**: on boot, scan all registered OUTBOXes for pending files.
- [x] Integrate watchdog to listen for `on_created` and `on_moved` events in active OUTBOXes.
- [x] Write integration tests simulating watchdog file drop events.
- [x] Implement logic to ignore files currently being written (files starting with the success prefix).

## **Phase 3: Resilience & Error Handling**

Ensuring no data is lost during I/O failures.

- [x] Implement the 5-state prefix matrix (`_`, `!`, `!_`, `!!`, `!!_`) for success, partial, and total failures.
- [x] Create the `~/.retry` global state file to track retry indices.
- [x] Implement the dynamic exponential retry loop and the `MAX_RETRIES` transition to fatal prefixes (`!!`).
- [x] Write unit tests for the exponential retry math (`RETRY_DELAY_BASE` * (2 ^ index)) and state transitions.
- [x] Setup global logging (logging to `~/.jatai.log`).

## **Phase 4: Configuration & File-System Reactivity**

Giving power back to the user via YAML and File-System manipulation.

- [x] Parse and apply local `.jatai` configurations (overriding global defaults).
- [x] Implement `.jatai.bkp` mechanism for configuration rollback on collisions.
- [x] Implement **Soft-Delete**: Daemon strictly ignores node contents where config is named `._jatai`, monitoring only the root.
- [x] Implement **Hot-Reload**: Watchdog listening to node root for `._jatai` -> `.jatai` renames.
- [x] Implement **Prefix Hot-Swap & Rollback**: Auto-rename local history if prefix config changes, aborting via `.bkp` on collisions.
- [x] Drop an error notification file into the originating node's INBOX when a prefix hot-swap rollback is triggered by a naming collision (ADR 3).

## **Phase 5: Onboarding & Documentation (In-Band Help)**

The "File-System First" user experience.

- [x] Curate project documentation to reflect only the current implementation state and real repository structure.
- [x] Move the version utility to `tools/set_version`, update all references, and add a directory-scoped permissive license in `tools/LICENSE`.
- [x] Define and document that README "File Structure" must list only non-ignored system files, allowing `docs/` as the only documentation directory, while excluding governance/project documentation files.
- [x] Implement Auto-Onboarding: Daemon detects paths added manually to `~/.jatai` and generates missing folders.
- [x] Add `!helloworld.md` file drop to newly created INBOXes.
- [x] Create the `docs/` folder structure (markdown files in subfolders).
- [x] Implement `jatai docs` to drop a category index file.
- [x] Implement `jatai docs [query]` to copy matching markdown files directly to the local INBOX.

## **Phase 6: Extended CLI Toolbox, TUI & Garbage Collection**

Adding convenience commands and storage management.

- [x] **[ARCH]** Define and document the CLI short-option policy (abbreviated flags), including canonical mappings such as `-a` for `--all` and `-G` for `--global`.
- [x] Implement canonical short-option flags in CLI: `-a`, `-i`, `-m`, `-r`, `-s`, `-f`, `-G` (excluding config keys per ADR 13).
- [x] Implement `jatai log` (latest log view in terminal).
- [x] Implement `jatai log --all|-a` (full log output in terminal).
- [x] Refactor `jatai docs` and `jatai docs [query]` to terminal-first output by default.
- [x] Add `--inbox` option to `jatai docs` and `jatai docs [query]` to export files into current node INBOX.
- [x] Add `--inbox` option to `jatai log` (latest/all) to export rendered output into current node INBOX.
- [x] Implement `jatai list`, `jatai send`, `jatai read`, `jatai unread`.
- [x] Implement `jatai config` to read/write settings via CLI.
- [ ] Implement `jatai config get [key]` with optional `-G|--global` scope and optional `-i|--inbox` export.
- [x] Implement `jatai remove` (CLI wrapper for renaming to `._jatai`).
- [x] Implement **Garbage Collection (Auto-Remove):** Background daemon logic to delete `_` prefixed files based on config thresholds.
- [x] Implement `jatai clear [--read] [--sent]` manual CLI command.
- [x] Build the interactive TUI (invoked by `jatai` with no arguments).

## **Phase 7: Advanced / Future Expansion (Post-Core)**

- [ ] **[ARCH]** Define directory structure logic for Smart Routing & Topics.
- [ ] **[ARCH]** Design the Node Addressing protocol (ID generation and resolution mapping).
- [ ] **[ARCH]** Design payload structures and UI for the Built-in Chat Application.
- [ ] Implement Built-in Chat Application using INBOX/OUTBOX for transport.
- [ ] Implement Jataí Over Internet (IP/Port exposition).
- [ ] Implement Global P2P & SaaS (Addressing providers).