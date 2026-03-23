# **Jataí 🐝 \- Architecture Decision Records (ADR)**

This document details the Architecture Decision Records (ADR) for the Jataí project.

## **1\. File-System Based Message Bus (Drop-Folder)**

* **Decision:** Utilize the *drop-folder* pattern. Communication will occur strictly through reading and writing in standardized directories (INBOX/ and OUTBOX/).

## **2\. Synchronization and Immutability Strategy**

* **Decision:** We reject the use of *Hardlinks* due to their inability to operate across different volumes/partitions. The final choice is the **physical copying of the file** (preserving metadata).

## **3\. Configurable State Machine & Hot-Swap (Prefix Philosophy)**

* **Decision:** File renaming using *configurable* prefixes. Read/Sent files receive a configurable success prefix (default \_). Failed transfers get an error prefix (default \!\_). System notifications use the error prefix in the INBOX.  
* **Hot-Swap & Rollback:** Changing the prefix in the .jatai file triggers the daemon to rename historical files. Collisions trigger an immediate rollback and an error file drop in the INBOX.

## **4\. Dual Registry & File-System First Onboarding**

* **Decision:** Jataí uses a dual YAML configuration approach with soft-deletion and auto-creation.  
  * **Global (\~/.jatai):** Stores absolute paths. Adding a path here auto-generates the INBOX/, OUTBOX/, and .jatai folders, dropping a \!helloworld.md tutorial into the new INBOX.  
  * **Local (.jatai or .\_jatai):** Renaming this file to .\_jatai disables the node (soft-delete). Renaming it back reactivates it (hot-reload).

## **5\. Event-Driven Execution (Start/Stop Daemon)**

* **Decision:** The main synchronization engine operates as a background Daemon based on OS file events, utilizing the watchdog library. It also performs a "Startup Scan" to process files added during downtime.

## **6\. Dynamic Resiliency and Exponential Retry**

* **Decision:** An exponential retry mechanism managed by a global \~/.retry state file, calculated dynamically per node: \[Node's RETRY\_DELAY\_BASE\] \* (2 ^ retry\_index).

## **7\. Data Safety and Controlled Garbage Collection**

* **Context:** The endless accumulation of processed files will exhaust disk space.  
* **Decision:** Jataí will *only* delete files explicitly marked with the success prefix (\_). This cleanup can be triggered manually (jatai clear) or automatically via configurable retention policies.

## **8\. Documentation as Messages (In-Band Help)**

* **Decision:** Comprehensive documentation is stored in a docs/ folder. Users can request documentation via jatai docs {query}, which will copy the relevant .md file(s) directly into their current node's INBOX.

## **9\. Atomic Delivery (Preventing Read/Write Race Conditions)**

* **Context:** Copying a large file from an OUTBOX to an INBOX takes time. If a listening script in the destination node tries to read the file before the copy is complete, it will read corrupted/incomplete data.  
* **Decision:** Jataí will perform **Atomic Delivery**. Files are first copied to the destination INBOX using a temporary extension (e.g., .file.ext.tmp). Only after the shutil.copy2 operation is 100% complete, the file is atomically renamed to its final name (.file.ext).  
* **Consequence:** Eliminates race conditions. Destination nodes will only ever see complete, ready-to-process files.