"""
Background daemon, startup scan, and watchdog integration for Jataí.
"""

import logging
import os
import signal
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from filelock import FileLock, Timeout
from watchdog.events import FileCreatedEvent, FileMovedEvent, FileSystemEventHandler
from watchdog.observers import Observer

from jatai.core.delivery import Delivery
from jatai.core.node import Node
from jatai.core.prefix import Prefix
from jatai.core.registry import Registry
from jatai.core.retry import RetryState


class AlreadyRunningError(RuntimeError):
    """Raised when a second daemon instance tries to start."""


class JataiWatchdogHandler(FileSystemEventHandler):
    """Handle OUTBOX file events and route them through the daemon."""

    def __init__(self, daemon: "JataiDaemon", source_node_path: Path) -> None:
        self.daemon = daemon
        self.source_node_path = Path(source_node_path).resolve()

    def on_created(self, event: FileCreatedEvent) -> None:
        if event.is_directory:
            return
        self.daemon.process_outbox_candidate(Path(event.src_path), self.source_node_path)

    def on_moved(self, event: FileMovedEvent) -> None:
        if event.is_directory:
            return
        self.daemon.process_outbox_candidate(Path(event.dest_path), self.source_node_path)


class JataiNodeConfigHandler(FileSystemEventHandler):
    """Watch node roots for config enable/disable and live edits."""

    CONFIG_FILENAMES = {Node.LOCAL_CONFIG_FILENAME, Node.LOCAL_CONFIG_DISABLED}

    def __init__(self, daemon: "JataiDaemon", node_path: Path) -> None:
        self.daemon = daemon
        self.node_path = Path(node_path).resolve()

    def on_created(self, event: FileCreatedEvent) -> None:
        if event.is_directory:
            return
        self._handle_path(Path(event.src_path))

    def on_modified(self, event) -> None:
        if event.is_directory:
            return
        self._handle_path(Path(event.src_path))

    def on_moved(self, event: FileMovedEvent) -> None:
        if event.is_directory:
            return
        self._handle_path(Path(event.src_path))
        self._handle_path(Path(event.dest_path))

    def _handle_path(self, path: Path) -> None:
        if path.name in self.CONFIG_FILENAMES:
            self.daemon.handle_node_config_change(self.node_path)


class JataiDaemon:
    """Manage background routing lifecycle and event-driven delivery."""

    POLL_INTERVAL_SECONDS = 0.2
    LOCK_TIMEOUT_SECONDS = 2
    MAINTENANCE_INTERVAL_TICKS = 25
    HELLOWORLD_FILENAME = "!helloworld.md"
    HELLOWORLD_CONTENT = """# Welcome to Jatai

This node was auto-onboarded from the global registry.

How to use:

1. Drop files into OUTBOX to broadcast.
2. Read files from INBOX.
3. Use `jatai status` to inspect this node.
4. Use `jatai docs` to receive documentation files in INBOX.
"""

    def __init__(
        self,
        registry_path: Optional[Path] = None,
        pid_path: Optional[Path] = None,
        retry_path: Optional[Path] = None,
        log_path: Optional[Path] = None,
        observer_factory=Observer,
    ) -> None:
        self.registry_path = Path(registry_path) if registry_path is not None else Path.home() / ".jatai"
        self.pid_path = Path(pid_path) if pid_path is not None else Path.home() / ".jatai.pid"
        self.retry_path = Path(retry_path) if retry_path is not None else Path.home() / ".retry"
        self.log_path = Path(log_path) if log_path is not None else Path.home() / ".jatai.log"
        self.observer_factory = observer_factory
        self.stop_event = threading.Event()
        self.observer: Optional[Observer] = None
        self.node_config_cache: Dict[Path, Dict[str, object]] = {}
        self.retry_state = RetryState(self.retry_path)
        self.logger = self._build_logger(self.log_path)

    def _build_logger(self, log_path: Path) -> logging.Logger:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        logger_name = f"jatai.daemon.{log_path}"
        logger = logging.getLogger(logger_name)
        logger.setLevel(logging.INFO)
        logger.propagate = False
        if not logger.handlers:
            handler = logging.FileHandler(log_path, encoding="utf-8")
            handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
            logger.addHandler(handler)
        return logger

    def _load_registry(self) -> Registry:
        registry = Registry(self.registry_path)
        registry.load()
        return registry

    def _resolve_configured_path(self, node: Node, configured_value: object, fallback_name: str) -> Path:
        if not configured_value:
            return node.node_path / fallback_name
        candidate = Path(str(configured_value))
        if candidate.is_absolute():
            return candidate
        return node.node_path / candidate

    def _drop_helloworld(self, node: Node) -> None:
        inbox = node.inbox_path
        inbox.mkdir(parents=True, exist_ok=True)
        hello_path = inbox / self.HELLOWORLD_FILENAME
        if hello_path.exists():
            return
        hello_path.write_text(
            self.HELLOWORLD_CONTENT + f"\nGenerated at: {datetime.now(timezone.utc).isoformat()}\n",
            encoding="utf-8",
        )

    def _ensure_node_onboarded(
        self,
        node: Node,
        node_data: Dict[str, object],
        global_config: Dict[str, object],
    ) -> None:
        effective = dict(global_config)
        for key in (
            "PREFIX_PROCESSED",
            "PREFIX_ERROR",
            "RETRY_DELAY_BASE",
            "MAX_RETRIES",
            "INBOX_DIR",
            "OUTBOX_DIR",
        ):
            if key in node_data:
                effective[key] = node_data[key]

        inbox_path = self._resolve_configured_path(node, effective.get("INBOX_DIR"), Node.INBOX_DIRNAME)
        outbox_path = self._resolve_configured_path(node, effective.get("OUTBOX_DIR"), Node.OUTBOX_DIRNAME)
        Node.validate_inbox_outbox_overlap(inbox_path, outbox_path)

        if not node.node_path.exists():
            node.node_path.mkdir(parents=True, exist_ok=True)

        has_any_local_config = node.local_config_path.exists() or node.disabled_config_path.exists()
        if not has_any_local_config:
            node.create(global_config=effective, inbox_path=inbox_path, outbox_path=outbox_path)
            self._drop_helloworld(node)
            self.logger.info("Auto-onboarded node at %s", node.node_path)
            return

        inbox_path.mkdir(parents=True, exist_ok=True)
        outbox_path.mkdir(parents=True, exist_ok=True)
        node.inbox_path = inbox_path
        node.outbox_path = outbox_path

    @property
    def pid_lock_path(self) -> Path:
        return Path(f"{self.pid_path}.lock")

    def _pid_lock(self) -> FileLock:
        self.pid_path.parent.mkdir(parents=True, exist_ok=True)
        return FileLock(str(self.pid_lock_path), timeout=self.LOCK_TIMEOUT_SECONDS)

    def read_pid(self) -> Optional[int]:
        if not self.pid_path.exists():
            return None
        content = self.pid_path.read_text(encoding="utf-8").strip()
        if not content:
            return None
        return int(content)

    def is_process_running(self, pid: int) -> bool:
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        return True

    def is_running(self) -> bool:
        pid = self.read_pid()
        if pid is None:
            return False
        return self.is_process_running(pid)

    def acquire_singleton(self) -> None:
        try:
            with self._pid_lock():
                pid = self.read_pid()
                if pid is not None and self.is_process_running(pid):
                    raise AlreadyRunningError("Already running")
                self.pid_path.write_text(str(os.getpid()), encoding="utf-8")
        except Timeout as exc:
            raise AlreadyRunningError(f"Failed to acquire daemon lock: {exc}") from exc

    def release_singleton(self) -> None:
        try:
            with self._pid_lock():
                if self.pid_path.exists():
                    self.pid_path.unlink()
        except Timeout:
            if self.pid_path.exists():
                self.pid_path.unlink()

    def install_signal_handlers(self) -> None:
        signal.signal(signal.SIGTERM, self._handle_shutdown_signal)
        signal.signal(signal.SIGINT, self._handle_shutdown_signal)

    def _handle_shutdown_signal(self, signum: int, frame) -> None:
        self.stop_event.set()

    def load_registered_nodes(self) -> List[Node]:
        registry = self._load_registry()
        nodes: List[Node] = []
        for node_data in registry.nodes.values():
            node = Node(Path(node_data["path"]))
            try:
                self._ensure_node_onboarded(node, node_data, registry.global_config)
            except Exception as exc:
                self.logger.warning("Failed to onboard node=%s reason=%s", node.node_path, exc)
                continue
            try:
                node.load_any_config()
            except FileNotFoundError:
                continue
            node.apply_effective_config(registry.global_config)
            nodes.append(node)
        return nodes

    def load_active_nodes(self) -> List[Node]:
        nodes: List[Node] = []
        for node in self.load_registered_nodes():
            if node.is_disabled() or not node.is_enabled():
                continue
            nodes.append(node)
        return nodes

    def _update_node_cache(self, node: Node) -> None:
        self.node_config_cache[node.node_path] = dict(node.local_config)

    def _remove_node_cache(self, node_path: Path) -> None:
        self.node_config_cache.pop(Path(node_path).resolve(), None)

    def _refresh_observer_watches(self) -> None:
        if self.observer is None:
            return
        if hasattr(self.observer, "unschedule_all"):
            self.observer.unschedule_all()

        registered_nodes = self.load_registered_nodes()
        active_count = 0
        for node in registered_nodes:
            try:
                self.observer.schedule(
                    JataiNodeConfigHandler(self, node.node_path),
                    str(node.node_path),
                    recursive=False,
                )
            except Exception as exc:
                self.logger.warning("Cannot watch node_path=%s reason=%s", node.node_path, exc)

        for node in registered_nodes:
            if node.is_disabled() or not node.is_enabled():
                self._remove_node_cache(node.node_path)
                continue
            try:
                self.observer.schedule(
                    JataiWatchdogHandler(self, node.node_path),
                    str(node.outbox_path),
                    recursive=False,
                )
            except Exception as exc:
                self.logger.warning("Cannot watch outbox_path=%s reason=%s", node.outbox_path, exc)
                continue
            self._update_node_cache(node)
            active_count += 1
        self.logger.info("Watchdog watching active_nodes=%s registered_nodes=%s", active_count, len(registered_nodes))

    def handle_node_config_change(self, node_path: Path) -> None:
        self.logger.info("Config change detected node=%s", node_path)
        node = Node(node_path)
        previous_config = self.node_config_cache.get(node.node_path)

        try:
            registry = self._load_registry()
        except FileNotFoundError:
            return

        try:
            node.load_any_config()
        except FileNotFoundError:
            self._remove_node_cache(node.node_path)
            self._refresh_observer_watches()
            return

        node.apply_effective_config(registry.global_config)

        if previous_config and node.is_enabled():
            prefix_keys_changed = any(
                previous_config.get(key) != node.local_config.get(key)
                for key in Node.PREFIX_KEYS
            )
            if prefix_keys_changed:
                self.logger.info("Prefix migration started node=%s", node_path)
                node.backup_current_config(previous_config)
                try:
                    node.migrate_prefix_history(previous_config, node.local_config)
                    self.logger.info("Prefix migration completed node=%s", node_path)
                except Exception as exc:
                    node.write_config(previous_config)
                    node.local_config = dict(previous_config)
                    node.apply_effective_config(registry.global_config)
                    self.logger.warning(
                        "Prefix rollback triggered node=%s reason=%s", node_path, exc
                    )
                    node.drop_error_notice(
                        f"Prefix migration aborted and configuration restored.\n\nReason: {exc}\n",
                        error_prefix=str(previous_config.get("PREFIX_ERROR", "!_")),
                    )

        if node.is_enabled() and not node.is_disabled():
            self._update_node_cache(node)
            self.logger.info("Node active node=%s", node_path)
        else:
            self._remove_node_cache(node.node_path)
            self.logger.info("Node disabled node=%s", node_path)

        self._refresh_observer_watches()

    def process_outbox_candidate(self, file_path: Path, source_node_path: Optional[Path] = None) -> None:
        if not file_path.exists() or not file_path.is_file():
            return

        nodes = self.load_active_nodes()
        source_node = self._find_source_node(file_path, nodes, source_node_path)
        if source_node is None:
            return

        success_prefix = str(source_node.get_config("PREFIX_PROCESSED", "_"))
        prefix = Prefix(
            success_prefix=success_prefix,
            error_prefix=str(source_node.get_config("PREFIX_ERROR", "!_")),
        )
        if Delivery.is_being_written(file_path, success_prefix=success_prefix):
            return
        if not prefix.is_pending(file_path):
            return

        self.broadcast_file(source_node, file_path, nodes)

    def _find_source_node(
        self,
        file_path: Path,
        nodes: List[Node],
        source_node_path: Optional[Path] = None,
    ) -> Optional[Node]:
        if source_node_path is not None:
            resolved = Path(source_node_path).resolve()
            for node in nodes:
                if node.node_path == resolved:
                    return node
        for node in nodes:
            if file_path.parent.resolve() == node.outbox_path.resolve():
                return node
        return None

    def _deliver_to_active_nodes(
        self,
        source_node: Node,
        source_file: Path,
        nodes: List[Node],
    ) -> Tuple[int, List[str]]:
        delivered_count = 0
        failed_nodes: List[str] = []
        for destination_node in nodes:
            if destination_node.node_path == source_node.node_path:
                continue
            try:
                Delivery(source_file, destination_node.inbox_path).deliver()
                delivered_count += 1
            except Exception as exc:
                failed_nodes.append(str(destination_node.node_path))
                self.logger.warning(
                    "Delivery failed for file=%s destination=%s reason=%s",
                    source_file,
                    destination_node.node_path,
                    exc,
                )
        return delivered_count, failed_nodes

    def _handle_delivery_result(
        self,
        source_node: Node,
        source_file: Path,
        canonical_retry_path: Path,
        total_targets: int,
        delivered_count: int,
        failed_nodes: List[str],
    ) -> bool:
        prefix = Prefix(
            success_prefix=str(source_node.get_config("PREFIX_PROCESSED", "_")),
            error_prefix=str(source_node.get_config("PREFIX_ERROR", "!_")),
        )

        if not failed_nodes:
            if source_file.exists():
                prefix.set_state(source_file, "processed")
            self.retry_state.clear(canonical_retry_path)
            self.logger.info("Delivery succeeded for file=%s", source_file)
            return True

        retry_delay_base = int(source_node.get_config("RETRY_DELAY_BASE", 60))
        max_retries = int(source_node.get_config("MAX_RETRIES", 3))
        partial_failure = delivered_count > 0 and delivered_count < total_targets
        retry_info = self.retry_state.register_failure(
            canonical_retry_path,
            failed_nodes=failed_nodes,
            retry_delay_base=retry_delay_base,
            max_retries=max_retries,
            partial_failure=partial_failure,
        )

        if retry_info["is_fatal"]:
            target_state = "fatal_partial" if partial_failure else "fatal_total"
            prefix.set_state(source_file, target_state)
            self.logger.error(
                "File reached fatal retry limit file=%s state=%s retries=%s",
                source_file,
                target_state,
                retry_info["retry_index"],
            )
            return False

        target_state = "error_partial" if partial_failure else "error_total"
        prefix.set_state(source_file, target_state)
        self.logger.warning(
            "File scheduled for retry file=%s state=%s retry_index=%s delay_seconds=%s",
            source_file,
            target_state,
            retry_info["retry_index"],
            retry_info["delay_seconds"],
        )
        return False

    def broadcast_file(self, source_node: Node, source_file: Path, nodes: List[Node]) -> bool:
        prefix = Prefix(
            success_prefix=str(source_node.get_config("PREFIX_PROCESSED", "_")),
            error_prefix=str(source_node.get_config("PREFIX_ERROR", "!_")),
        )
        canonical_retry_path = prefix.canonical_retry_path(source_file)
        self.retry_state.load()
        total_targets = sum(1 for node in nodes if node.node_path != source_node.node_path)
        delivered_count, failed_nodes = self._deliver_to_active_nodes(source_node, source_file, nodes)
        result = self._handle_delivery_result(
            source_node=source_node,
            source_file=source_file,
            canonical_retry_path=canonical_retry_path,
            total_targets=total_targets,
            delivered_count=delivered_count,
            failed_nodes=failed_nodes,
        )
        self.retry_state.save()
        return result

    def startup_scan(self) -> None:
        nodes = self.load_active_nodes()
        self.logger.info("Startup scan begin nodes=%s", len(nodes))
        for node in nodes:
            self.process_pending_outbox(node, nodes)
            self._run_auto_gc_for_node(node)
        self.logger.info("Startup scan complete")

    def _trim_processed_history(self, files: List[Path], success_prefix: str, max_files: int) -> int:
        if max_files <= 0:
            return 0

        processed_files = sorted(
            [path for path in files if path.name.startswith(success_prefix)],
            key=lambda path: path.stat().st_mtime,
        )
        excess = len(processed_files) - max_files
        if excess <= 0:
            return 0

        removed = 0
        for file_path in processed_files[:excess]:
            file_path.unlink(missing_ok=True)
            removed += 1
        return removed

    def _run_auto_gc_for_node(self, node: Node) -> None:
        success_prefix = str(node.get_config("PREFIX_PROCESSED", "_"))
        max_read = int(node.get_config("GC_MAX_READ_FILES", 0) or 0)
        max_sent = int(node.get_config("GC_MAX_SENT_FILES", 0) or 0)

        removed_read = self._trim_processed_history(node.list_inbox(), success_prefix, max_read)
        removed_sent = self._trim_processed_history(node.list_outbox(), success_prefix, max_sent)

        if removed_read or removed_sent:
            self.logger.info(
                "Auto-GC removed node=%s inbox=%s outbox=%s",
                node.node_path,
                removed_read,
                removed_sent,
            )

    def process_pending_outbox(self, node: Node, nodes: List[Node]) -> None:
        prefix = Prefix(
            success_prefix=str(node.get_config("PREFIX_PROCESSED", "_")),
            error_prefix=str(node.get_config("PREFIX_ERROR", "!_")),
        )
        for file_path in sorted(node.list_outbox()):
            if Delivery.is_being_written(file_path, success_prefix=prefix.success_prefix):
                continue

            if prefix.is_pending(file_path):
                self.broadcast_file(node, file_path, nodes)
                continue

            if prefix.is_retryable_error(file_path):
                canonical_retry_path = prefix.canonical_retry_path(file_path)
                self.retry_state.load()
                due = self.retry_state.is_due(canonical_retry_path)
                self.retry_state.save()
                if not due:
                    continue
                self.logger.info("Retry due for file=%s", file_path)
                pending_path = prefix.to_pending(file_path)
                self.broadcast_file(node, pending_path, nodes)

    def setup_watchdog(self) -> None:
        observer = self.observer_factory()
        observer.start()
        self.observer = observer
        self._refresh_observer_watches()

    def shutdown_watchdog(self) -> None:
        if self.observer is None:
            return
        self.observer.stop()
        self.observer.join(timeout=5)
        self.observer = None

    def run(self) -> None:
        self.install_signal_handlers()
        self.acquire_singleton()
        self.logger.info("Daemon starting pid=%s registry=%s", os.getpid(), self.registry_path)
        tick_count = 0
        try:
            self.startup_scan()
            self.setup_watchdog()
            while not self.stop_event.wait(self.POLL_INTERVAL_SECONDS):
                tick_count += 1
                if tick_count >= self.MAINTENANCE_INTERVAL_TICKS:
                    tick_count = 0
                    for node in self.load_active_nodes():
                        self._run_auto_gc_for_node(node)
        finally:
            self.shutdown_watchdog()
            self.release_singleton()
            self.logger.info("Daemon stopped")

    def stop(self) -> None:
        self.stop_event.set()
