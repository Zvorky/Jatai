# **Jataí 🐝 - Implementation Roadmap & To-Do List**

This document organizes the planned development phases for Jataí, ordered by priority.

## **Phase 1 to Phase 5: Core & Configuration**
*(All tasks completed successfully in previous cycles. See repository history).*

## **Phase 6: CLI, TUI & Architecture Bugfixes**
Completing the operational toolset and fixing architectural compliance gaps from the Phase 1-5 audit.

- [x] **[ARCH]** Define and document the CLI short-option policy (abbreviated flags).
	- Related: [ADR-13], [REQ-9.6]
- [x] Implement canonical short-option flags in CLI (`-a`, `-i`, `-m`, etc.).
	- Related: [ADR-13], [REQ-9.6]
- [x] Implement `jatai log`, `jatai log --all`, and `jatai docs` with terminal-first output.
	- Related: [ADR-8], [ADR-12], [REQ-8.2], [REQ-9.3]
- [x] Add `--inbox` option to export logs and docs directly to current node INBOX.
	- Related: [ADR-8], [REQ-8.3], [REQ-9.5]
- [x] Implement `jatai list`, `jatai send`, `jatai read`, `jatai unread`, `jatai remove`.
	- Related: [REQ-9.1]
- [x] Implement `jatai config` and `jatai config get`.
	- Related: [ADR-13], [REQ-9.7]
- [x] Build the interactive TUI with Textual and implement "Browse Nodes".
	- Related: [ADR-14], [REQ-9.8], [REQ-9.11]
- [x] **[BUGFIX] OS Auto-Start Enable:** Ensure the daemon installation not only creates the `.service`/`.plist` file, but actually runs the OS command to enable/load it (e.g., `systemctl --user enable`).
	- Related: [ADR-5], [REQ-4.2]
- [x] **[BUGFIX] Unify Helloworld Drop:** Modify the Daemon auto-onboarding to read `!helloworld.md` from the `docs/` folder instead of using a hardcoded string, matching the `jatai init` behavior.
	- Related: [ADR-8], [ADR-15]
- [x] **[BUGFIX] TUI Feature Parity:** Expose the `--inbox` option inside the TUI for `docs` and `log` commands.
	- Related: [ADR-14], [REQ-9.4]
- [x] **[BUGFIX] Code Cleanup:** Remove dead code (`deliver_copy_to_outbox()` in `delivery.py`).
	- Related: [REQ-7]
- [x] **[BUGFIX] Enforce Config Syntax:** Modify `jatai config [key]` to throw a syntax error if `[value]` is missing, enforcing the use of `config get` for reads.
	- Related: [ADR-13], [REQ-9.7]
- [x] **[BUGFIX] Rename internal methods:** Rename misleading methods like `is_being_written` to `has_ignore_prefix` or similar to reflect the state machine accurately.
	- Related: [ADR-3], [REQ-2]
- [x] **[BUGFIX] Update CLI/TUI Tests:** Update/fix CLI and TUI automated tests to match the new config get/set enforcement and TUI async/modal prompt behavior. Ensure tests reflect ADRs and REQUIREMENTS, and are compatible with Textual's event loop requirements.
	- Related: [REQ-7], [ADR-14]
- [x] **[BUGFIX] OS Auto-Start Enable & Warnings:** Ensure the daemon installation runs `systemctl --user enable`. Catch failures (or missing systemd) and output an explicit error message to the user.
	- Related: [ADR-5], [REQ-4.2]
- [x] **[BUGFIX] Retry Math Correction:** Ensure the code logic accurately reflects `1 original attempt + MAX_RETRIES` before hitting the fatal prefix state.
	- Related: [ADR-6], [REQ-5.1], [REQ-5.2]
- [x] **[BUGFIX] Local File Locks:** Implement `filelock` on `Node.save_config` and `Node.load_config` to match the global registry concurrency protection.
	- Related: [ADR-11], [REQ-3.4.2], [REQ-3.2]

## **Phase 7: Advanced Logging & Immediate Garbage Collection**
Refining the internal engines for long-term disk safety and observability.

- [x] **State Architecture Refactor:**
		- [x] Remove "prefix guessing" heuristic (anti-heuristic): ensure the daemon never infers prefixes from historical files, only from configs/backups.
			- Related: [ADR-3.3], [REQ-3.6]
		- [x] Implement writing/updating of `/tmp/jatai/removed.yaml` with ` --autoremoved` entries when manual `.jatai` removal is detected.
			- Related: [ADR-4.4], [REQ-3.7.2]
		- [x] Implement generation and maintenance of `/tmp/jatai/uuid_map.yaml` (map node paths to UUIDs, reuse UUIDs for removed/re-added paths).
			- Related: [ADR-4.3], [REQ-3.5.2]
		- [x] Implement/adjust backup cache in `/tmp/jatai/bkp/<UUID>.yaml` for prefix migrations.
			- Related: [ADR-4.3], [REQ-3.5.4]
- [x] Implement Log Rotation: Name log files with datetime suffix + `.log` and store them in `/tmp/jatai/logs/`.
	- Related: [ADR-12], [REQ-6.2]
- [x] Implement Configurable Latest Log: Maintain a `jatai_latest.log` symlink/copy whose target location is defined by a global configuration key.
	- Related: [ADR-12], [REQ-6.3]
- [x] Implement GC Deletion Engine: Move deleted files to the OS Trash by default, with an override setting for permanent deletion.
	- Related: [ADR-7], [REQ-3.7.3.2]
- [x] Implement GC 15-Minute Sweep: Background daemon loop to sweep old files every 15 minutes.
	- Related: [ADR-7], [REQ-3.7.3.3]
- [x] Implement GC Immediate Threshold: Logic to instantly delete the oldest file locally the moment the 11th file (or configured limit) hits the OUTBOX.
	- Related: [ADR-7], [REQ-3.7.3.3]
- [x] Implement default configuration constants: INBOX keeps all, OUTBOX keeps max 11 files.
	- Related: [ADR-7], [REQ-3.7.3.1]
- [x] Rename `_` semantic references in code/docs from "processed" to "ignore" for OUTBOX contexts.
	- Related: [ADR-3], [REQ-2]
- [x] [BUGFIX] Remove/disable TUI "Browse Nodes" until future rework (still active in code).
	- Related: [ADR-14]
- [x] [BUGFIX] Implement auto-start fallback for environments without systemd (e.g., crontab @reboot, Windows, macOS, etc.).
	- Related: [ADR-5], [REQ-4.2]
- [x] [BUGFIX] Apply local `.jatai` locking in `Node.save_config` and `Node.load_config` to match global registry lock style.
	- Related: [ADR-11], [REQ-3.4.2]
- [x] [BUGFIX] Adjust GC execution path to run immediate outbound processed-file sweep when OUTBOX crosses `GC_MAX_SENT_FILES`.
	- Related: [ADR-7]
- [x] [BUGFIX] Align `Registry.DEFAULT_CONFIG` to ADR/REQUIREMENTS with `GC_MAX_SENT_FILES: 11` and `GC_MAX_READ_FILES: 0`.
	- Related: [ADR-7], [REQ-3.7.3.1]
- [x] [BUGFIX] Enforce control-state artifacts under `/tmp/jatai` and disable daemon auto-creation of `._jatai` on manual `.jatai` deletion.
	- Related: [ADR-4], [ADR-5.2], [ADR-6.1], [REQ-3.5], [REQ-3.7.2], [REQ-4.1]
- [x] [BUGFIX] Bootstrap global `~/.jatai` on first TUI launch and add explicit uninstall cleanup helper (`jatai cleanup --full`).
	- Related: [ADR-4.6], [ADR-4.7], [REQ-9.12], [REQ-9.13]

---

## **Future / Expansion (Post-Core)**
Architectural discussions and network expansions.

- [x] Implement OS Auto-Start fallbacks (e.g., `crontab @reboot` for Alpine/minimal Linux) and native compatibility for Windows/macOS.
- [ ] **[ARCH]** Define detailed TUI Navigation rules (separating INBOX/OUTBOX views, webapp layout mirroring).
- [ ] **[ARCH]** Define the Prefix Customization Schema (how users will change `_`, `!`, etc., in the `.jatai` file).
- [ ] **[ARCH]** Define directory structure logic for Smart Routing & Topics.
- [ ] **[ARCH]** Design the Node Addressing protocol (ID generation based on the existing UUID map for direct resolution).
- [ ] **[ARCH]** Design payload structures and UI for the Built-in Chat Application.
- [ ] Implement Built-in Chat Application using INBOX/OUTBOX for transport.
- [ ] Implement Jataí Over Internet (IP/Port exposition).
- [ ] Implement Global P2P & SaaS (Addressing providers).