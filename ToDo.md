# **Jataí 🐝 - Implementation Roadmap & To-Do List**

This document organizes the planned development phases for Jataí, ordered by priority.

## **Phase 1 to Phase 5: Core & Configuration**
*(All tasks completed successfully in previous cycles. See repository history).*

## **Phase 6: CLI, TUI & Architecture Bugfixes**
Completing the operational toolset and fixing architectural compliance gaps from the Phase 1-5 audit.

- [x] **[ARCH]** Define and document the CLI short-option policy (abbreviated flags).
- [x] Implement canonical short-option flags in CLI (`-a`, `-i`, `-m`, etc.).
- [x] Implement `jatai log`, `jatai log --all`, and `jatai docs` with terminal-first output.
- [x] Add `--inbox` option to export logs and docs directly to current node INBOX.
- [x] Implement `jatai list`, `jatai send`, `jatai read`, `jatai unread`, `jatai remove`.
- [x] Implement `jatai config` and `jatai config get`.
- [x] Build the interactive TUI with Textual and implement "Browse Nodes".
- [x] **[BUGFIX] OS Auto-Start Enable:** Ensure the daemon installation not only creates the `.service`/`.plist` file, but actually runs the OS command to enable/load it (e.g., `systemctl --user enable`).
- [x] **[BUGFIX] Unify Helloworld Drop:** Modify the Daemon auto-onboarding to read `!helloworld.md` from the `docs/` folder instead of using a hardcoded string, matching the `jatai init` behavior.
- [x] **[BUGFIX] TUI Feature Parity:** Expose the `--inbox` option inside the TUI for `docs` and `log` commands.
- [x] **[BUGFIX] Code Cleanup:** Remove dead code (`deliver_copy_to_outbox()` in `delivery.py`).
- [x] **[BUGFIX] Enforce Config Syntax:** Modify `jatai config [key]` to throw a syntax error if `[value]` is missing, enforcing the use of `config get` for reads.
- [x] **[BUGFIX] Rename internal methods:** Rename misleading methods like `is_being_written` to `has_ignore_prefix` or similar to reflect the state machine accurately.
- [x] **[BUGFIX] Update CLI/TUI Tests:** Update/fix CLI and TUI automated tests to match the new config get/set enforcement and TUI async/modal prompt behavior. Ensure tests reflect ADRs and REQUIREMENTS, and are compatible with Textual's event loop requirements.
- [x] **[BUGFIX] OS Auto-Start Enable & Warnings:** Ensure the daemon installation runs `systemctl --user enable`. Catch failures (or missing systemd) and output an explicit error message to the user.
- [x] **[BUGFIX] Retry Math Correction:** Ensure the code logic accurately reflects `1 original attempt + MAX_RETRIES` before hitting the fatal prefix state.
- [x] **[BUGFIX] Local File Locks:** Implement `filelock` on `Node.save_config` and `Node.load_config` to match the global registry concurrency protection.

## **Phase 7: Advanced Logging & Immediate Garbage Collection**
Refining the internal engines for long-term disk safety and observability.

- [ ] **State Architecture Refactor:** Strip "prefix guessing" logic. Move all system control data out of `~/.jatai`. Implement `/tmp/jatai/` structure handling `uuid_map.yaml`, `removed.yaml` (with `--autoremoved` tagging), and `bkp/<UUID>.yaml` caching for robust prefix migrations.
- [ ] Implement Log Rotation: Name log files with datetime suffix + `.log` and store them in `/tmp/jatai/logs/`.
- [ ] Implement Configurable Latest Log: Maintain a `jatai_latest.log` symlink/copy whose target location is defined by a global configuration key.
- [ ] Implement GC Deletion Engine: Move deleted files to the OS Trash by default, with an override setting for permanent deletion.
- [ ] Implement GC 15-Minute Sweep: Background daemon loop to sweep old files every 15 minutes.
- [ ] Implement GC Immediate Threshold: Logic to instantly delete the oldest file locally the moment the 11th file (or configured limit) hits the OUTBOX.
- [ ] Implement default configuration constants: INBOX keeps all, OUTBOX keeps max 11 files.
- [ ] Rename `_` semantic references in code/docs from "processed" to "ignore" for OUTBOX contexts.
- [BUGFIX] Fix node lifecycle in daemon/node onboarding when local folder is deleted: avoid re-creating `.jatai` and instead enforce softdeleted state with `--autoremoved` metadata.
- [BUGFIX] Remove/disable TUI "Browse Nodes" button in the current phase so crashes are not user-visible until rework in future phases.
- [BUGFIX] Apply local `.jatai` locking in `Node.save_config` and `Node.load_config` to match global registry lock style.
- [BUGFIX] Adjust GC execution path to run immediate outbound processed-file sweep when OUTBOX crosses `GC_MAX_SENT_FILES`.
- [BUGFIX] Align `Registry.DEFAULT_CONFIG` to ADR/REQUIREMENTS with `GC_MAX_SENT_FILES: 11` and `GC_MAX_READ_FILES: 0`.

---

## **Future / Expansion (Post-Core)**
Architectural discussions and network expansions.

- [ ] Implement OS Auto-Start fallbacks (e.g., `crontab @reboot` for Alpine/minimal Linux) and native compatibility for Windows/macOS.
- [ ] **[ARCH]** Define detailed TUI Navigation rules (separating INBOX/OUTBOX views, webapp layout mirroring).
- [ ] **[ARCH]** Define the Prefix Customization Schema (how users will change `_`, `!`, etc., in the `.jatai` file).
- [ ] **[ARCH]** Define directory structure logic for Smart Routing & Topics.
- [ ] **[ARCH]** Design the Node Addressing protocol (ID generation based on the existing UUID map for direct resolution).
- [ ] **[ARCH]** Design payload structures and UI for the Built-in Chat Application.
- [ ] Implement Built-in Chat Application using INBOX/OUTBOX for transport.
- [ ] Implement Jataí Over Internet (IP/Port exposition).
- [ ] Implement Global P2P & SaaS (Addressing providers).