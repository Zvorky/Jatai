# **Jataí 🐝 \- Technical Requirements**

This document defines the functional and technical requirements for building Jataí.

## **1\. Technology Stack**

* **Language:** Python 3.8+  
* **Standard Libraries (Native):** os, shutil, time, logging, pathlib, json.  
* **External Libraries (Approved):**  
  * typer: For building the Command Line Interface (CLI).  
  * pyyaml: For reading and resilient manipulation of YAML configurations.  
  * watchdog: For monitoring file system events with zero CPU cost.  
  * pytest: For automated unit and integration testing.

## **2\. State Machine (The Prefix Philosophy)**

Jataí does not use databases for queue control. The state of each message is defined exclusively by the prefix of the file name. **These prefixes are configurable** (Globally or Locally), but assume the following defaults:

* **Success/Ignored Prefix (Default: \_):** Processed or currently writing file.  
  * In INBOX: Means the local node has already read the message.  
  * In OUTBOX: Means Jataí has successfully broadcasted the file.  
  * **Concurrency Strategy:** Agents that need to write large files must initially save them with this prefix (e.g., \_video.mp4). Jataí will ignore them. Once writing is complete, simply remove the prefix to trigger the delivery.  
* **Error/Warning Prefix (Default: \! or \!\_):** Files requiring attention.  
  * In OUTBOX: Delivery failure (e.g., destination disk full). It will wait for the *retry* process.  
  * In INBOX (System Notification): Used by Jataí itself to communicate with the user (e.g., \!\_JATAI\_WARNING.txt or \!helloworld.md).  
* **{No Prefix}:** Pending file. Jataí acts immediately.

## **3\. Topology and Configuration**

* **Node Structure:** A directory containing configurable input and output subfolders.  
* **Global Registry (\~/.jatai):** YAML file containing absolute paths of all nodes and global default configurations (e.g., PREFIX\_PROCESSED: "\_", RETRY\_DELAY\_BASE: 60).  
* **Local Configuration (.jatai in the node's folder):** YAML file that stores node metadata and overrides global configurations.

### **3.1 Initialization and Auto-Onboarding**

* **File-System Initialization:** Adding a directory path to the global \~/.jatai auto-generates the INBOX, OUTBOX, and local .jatai file.  
* **Onboarding (\!helloworld.md):** Newly initialized nodes receive a base documentation file automatically dropped into their INBOX.

### **3.2 Migration, Removal & Data Retention**

* **Automatic Prefix Migration (Hot-Swap):** Changing the prefix in .jatai triggers an automatic history rename.  
* **Deactivation and Soft-Delete:** Renaming .jatai to .\_jatai disables the node.  
* **Data Retention (Garbage Collection):** To prevent disk exhaustion, Jataí allows deleting **processed** files (files starting with the success prefix). This is the *only* exception to the non-destructive rule.  
  * **Auto-Cleanup:** Can be configured in .jatai using keys like AUTO\_CLEANUP\_SENT\_DAYS, AUTO\_CLEANUP\_READ\_DAYS, MAX\_SENT\_COUNT, or MAX\_READ\_COUNT.  
  * **Manual Cleanup:** Via CLI using the jatai clear command.

## **4\. Routing Engine (Daemon & Watchdog)**

* **Startup Scan:** On boot, scans all paths for active .jatai files and processes pending files.  
* **Real-Time Trigger:** watchdog listens for on\_created or on\_moved in OUTBOX folders.  
* **Reactivation Trigger:** Monitors the root of known nodes for hot-reloading (.\_jatai \-\> .jatai).

## **5\. Retry Mechanism (Failure Management)**

* **Error Trigger:** Copy failures add the configured Error Prefix in the OUTBOX.  
* **Exponential Logic:** Delay is \[Node's RETRY\_DELAY\_BASE\] \* (2 ^ retry\_index). Default: 60s.

## **6\. Observability and Logging**

* Exclusive use of the native logging library (e.g., \~/.jatai.log).

## **7\. Automated Testing Strategy**

* **Framework:** pytest.  
* **Location:** All tests must reside in the ./tests/ directory at the root of the project.  
* **Coverage:** Must cover YAML parsing resilience, state machine prefix logic, watchdog trigger simulation, and core CLI commands.

## **8\. Deep Documentation (docs/)**

* In-depth guides and architecture notes are stored as markdown files in folders/subfolders inside docs/.  
* Running jatai docs without a query will drop an **index file** into the INBOX listing all available categories.  
* Running jatai docs {query} drops the specific markdown files into the INBOX.

## **9\. CLI and TUI (The Toolbox)**

$$TODO$$  
*(Refer to the README for the full CLI command table).*