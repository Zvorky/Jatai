# **Jataí 🐝**
**The local micro-email and messaging bus for your file system. Connect scripts and AI agents instantly using a zero-config drop-folder pattern. Jataí uses OS file events to route data across directories via standardized INBOX/OUTBOX folders, without complex APIs or sockets. Drop a file, and it's delivered\!**

## **🎯 Philosophy & Goal**

The main objective of Jataí is to eliminate the need for complex network setups (REST APIs, WebSockets, Localhost Ports) when making local scripts or AI agents talk to each other.  
By utilizing standardized directories (INBOX/ and OUTBOX/) and operating system file events, Jataí creates a zero-configuration, asynchronous communication mesh across different directories or disk volumes on your machine.  
**Core Tenets:**

1. **Language Agnostic:** If it can write a file, it can use Jataí.  
2. **Controlled Deletion:** Jataí protects your data by *never* deleting pending or unprocessed files (it only copies or renames them to mark state). Deletions occur strictly on processed history files (\_) when explicitly triggered by you (via the clear command) or by your configurable auto-retention rules to save disk space.  
3. **File-System First:** You don't need a CLI to use Jataí daily. The entire system is responsive to native file explorer actions.

## **🐝 Usage (The File-System Way)**

**Only the daemon startup requires the CLI.** Everything else can be done simply by moving, editing, or renaming files\!

1. **Initialize a Node:** Run jatai ./my-folder OR open the global \~/.jatai file and add the absolute path. The daemon will auto-build the INBOX/, OUTBOX/, and drop a \!helloworld.md onboarding file.  
2. **Send a Message:** Move any file into the OUTBOX/ folder. Jataí broadcasts it and adds a \_ prefix to the local copy.  
3. **Read a Message:** Rename processed files in the INBOX/ to start with \_.  
4. **Writing Large Files:** Save directly to the OUTBOX/ starting with \_ (e.g., \_video.mp4). Remove the \_ when done to trigger delivery.  
5. **Disable a Node:** Rename the hidden .jatai file to .\_jatai.  
6. **Get Help:** Run jatai docs to get an index of available manuals, or jatai docs {query} to drop specific documentation directly into the INBOX.

## **🛠️ CLI & TUI Toolbox**

*While daily operations are done directly via the file system, a robust CLI and an interactive Text User Interface (TUI) are currently planned for node management.*

$PLANNED / TODO$  

| Command | Action |
| :---- | :---- |
| jatai | Opens the interactive Text User Interface (TUI). |
| jatai \[path\] | Initializes a node. |
| jatai start | Starts the background daemon. |
| jatai stop | Stops the background daemon. |
| jatai status | Returns file counters for the current node. |
| jatai config \[--global\] \<key\> \<val\> | Sets a configuration parameter locally or globally. |
| jatai list \[addrs\|inbox\|outbox\] | Lists files in current node (inbox/outbox) or all nodes (addrs). |
| jatai send \<file\> \[--move\] | Copies (or moves) an external file into the local OUTBOX. |
| jatai read \<file\> | Renames a file in the INBOX, adding the success prefix. |
| jatai unread \<file\> | Removes the success prefix from a file in the INBOX. |
| jatai remove \[path\] | Disables the node (current dir by default). Safeguarded against global origin. |
| jatai clear \[inbox\|outbox\] | Clears processed files (\_) in both folders or a specific one. |
| jatai docs \[query\] | Fetches deep documentation from docs/ into the INBOX. |

## **🏗️ Architecture & Requirements**

* [**Architecture Decision Records (ADR)**](ARCHITECTURE.md)  
* [**Technical Requirements**](REQUIREMENTS.md)  
* **Deep Documentation:** Planned to be stored in the `docs/` folder (can be fetched via jatai docs).

## **🗂️ File Structure**

```
.
├── .git/                          # Git repository
├── src/jatai/                     # Main package source code
│   ├── __init__.py               # Package metadata and version info
│   ├── core/                      # Core modules
│   │   ├── __init__.py
│   │   ├── registry.py           # Global registry (~/.jatai) management
│   │   ├── delivery.py           # Atomic file delivery (shutil.copy2 with .tmp)
│   │   ├── prefix.py             # State machine using file prefixes
│   │   └── node.py               # Node representation (INBOX/OUTBOX)
│   └── cli/                       # Command-line interface
│       ├── __init__.py
│       └── main.py               # Typer CLI app and commands
├── tests/                         # Test suite (pytest)
│   ├── conftest.py               # pytest fixtures and configuration
│   ├── test_dummy.py             # Basic pytest setup test
│   ├── test_registry.py          # Registry module tests (happy/error/adversarial)
│   ├── test_delivery.py          # Delivery module tests (atomic delivery validation)
│   ├── test_prefix.py            # Prefix state machine tests
│   ├── test_node.py              # Node module tests
│   └── test_cli.py               # CLI tests using Typer's CliRunner
├── docs/                          # Documentation (future Phase 5)
├── venv/                          # Python virtual environment (Fedora Silverblue)
├── requirements.txt               # Python dependencies
├── validate_phase1.py            # Phase 1 validation script (requires deps)
├── test_phase1_core_logic.py     # Phase 1 core logic tests (no external deps)
├── run_all_tests.py              # Test runner script
├── AGENTS.md                      # Agent rules and development guidelines
├── ARCHITECTURE.md                # Architecture Decision Records (ADR)
├── REQUIREMENTS.md                # Technical requirements specification
├── README.md                      # This file
├── ToDo.md                        # Implementation roadmap
└── LICENSE                        # Mozilla Public License 2.0 (MPL-2.0)
```

## **🚀 Future Ideas & Roadmap**

* **Phase 2:** Smart Routing & Topics (Pub/Sub channels using subdirectories).  
* **Phase 3:** Node Addressing & Built-in Chat (Assigning unique IDs to directories for direct 1-to-1 delivery, plus a chat application that uses the Jataí transport).  
* **Phase 4:** Jataí Over Internet (Direct IP/Port connection, allowing remote access beyond the local LAN).  
* **Phase 5:** Global P2P Mesh Network & SaaS Control Plane (Addressing providers and mediators for offline message buffering, with free/paid storage tiers).

## **📄 License**

Jataí is released under the [Mozilla Public License 2.0 (MPL-2.0)](LICENSE).  
**What this means:**

* **Free for all:** You can use, modify, and distribute Jataí freely, including in commercial or closed-source environments.  
* **File-level Copyleft:** If you modify the *existing* Jataí source code files, you must share those specific modifications under the same MPL-2.0 license.  
* **Your code is yours:** Larger projects or proprietary tools that merely use Jataí (or communicate with it via the file system) are not "infected" and can remain completely closed-source.
