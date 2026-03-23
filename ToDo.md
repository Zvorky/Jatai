# **Jataí 🐝 \- Implementation Roadmap & To-Do List**

This document organizes the planned development phases for Jataí, ordered by priority.

## **Phase 1: Core Foundation & Basic CLI**

The absolute minimum required to route files safely between folders.

* \[ \] Set up Python project structure (core/, cli/, tests/).  
* \[ \] Set up pytest framework and write first dummy test.  
* \[ \] Implement typer base setup.  
* \[ \] Write unit tests for global registry parsing (\~/.jatai).  
* \[ \] Create jatai \[path\] command to initialize INBOX/, OUTBOX/, and .jatai.  
* \[ \] Implement physical file copying logic (shutil.copy2) using **Atomic Delivery** (temporary .tmp extension during copy).  
* \[ \] Implement the success prefix logic (adding \_ to processed OUTBOX files).

## **Phase 2: The Routing Engine (Daemon & Watchdog)**

Making the system reactive and background-driven.

* \[ \] Implement jatai start and jatai stop logic.  
* \[ \] Implement the **Startup Scan**: on boot, scan all registered OUTBOXes for pending files.  
* \[ \] Integrate watchdog to listen for on\_created and on\_moved events in active OUTBOXes.  
* \[ \] Write integration tests simulating watchdog file drop events.  
* \[ \] Implement logic to ignore files currently being written (files starting with the success prefix).

## **Phase 3: Resilience & Error Handling**

Ensuring no data is lost during I/O failures.

* \[ \] Implement the error prefix (\!\_) for failed copies.  
* \[ \] Create the \~/.retry global state file to track retry indices.  
* \[ \] Write unit tests for the exponential retry math (RETRY\_DELAY\_BASE \* (2 ^ index)).  
* \[ \] Implement the background retry loop in the Daemon.  
* \[ \] Setup global logging (logging to \~/.jatai.log).

## **Phase 4: Configuration & File-System Reactivity**

Giving power back to the user via YAML and File-System manipulation.

* \[ \] Parse and apply local .jatai configurations (overriding global defaults).  
* \[ \] Implement **Soft-Delete**: Daemon must ignore nodes where config is named .\_jatai.  
* \[ \] Implement **Hot-Reload**: Watchdog listening to node root for .\_jatai \-\> .jatai renames.  
* \[ \] Implement **Prefix Hot-Swap**: Auto-rename local history if prefix config changes.  
* \[ \] Implement **Rollback**: Abort hot-swap on collisions and drop an error file in the INBOX.

## **Phase 5: Onboarding & Documentation (In-Band Help)**

The "File-System First" user experience.

* \[ \] Implement Auto-Onboarding: Daemon detects paths added manually to \~/.jatai and generates missing folders.  
* \[ \] Add \!helloworld.md file drop to newly created INBOXes.  
* \[ \] Create the docs/ folder structure (markdown files in subfolders).  
* \[ \] Implement jatai docs to drop a category index file.  
* \[ \] Implement jatai docs \[query\] to copy matching markdown files directly to the local INBOX.

## **Phase 6: Extended CLI Toolbox, TUI & Garbage Collection**

Adding convenience commands and storage management.

* \[ \] Implement jatai status, jatai list, jatai send, jatai read, jatai unread.  
* \[ \] Implement jatai remove (CLI wrapper for renaming to .\_jatai).  
* \[ \] Implement **Garbage Collection (Auto-Remove):** Background daemon logic to delete \_ prefixed files based on config thresholds.  
* \[ \] Implement jatai clear \[--read\] \[--sent\] manual CLI command.  
* \[ \] Build the interactive TUI (invoked by jatai with no arguments).

## **Phase 7: Advanced / Future Expansion (Post-Core)**

* \[ \] **\[ARCH\]** Define directory structure logic for Smart Routing & Topics.  
* \[ \] **\[ARCH\]** Design the Node Addressing protocol (ID generation and resolution mapping).  
* \[ \] **\[ARCH\]** Design payload structures and UI for the Built-in Chat Application.  
* \[ \] Implement Built-in Chat Application using INBOX/OUTBOX for transport.  
* \[ \] Implement Jataí Over Internet (IP/Port exposition).  
* \[ \] Implement Global P2P & SaaS (Addressing providers).