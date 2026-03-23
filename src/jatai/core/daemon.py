"""
Background daemon, startup scan, and watchdog integration for Jataí.
"""

import logging
import os
import signal
import threading
from pathlib import Path
from typing import List, Optional, Tuple

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


class JataiDaemon:
    """Manage background routing lifecycle and event-driven delivery."""

    POLL_INTERVAL_SECONDS = 0.2
    LOCK_TIMEOUT_SECONDS = 2

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

    def _resolve_configured_path(self, node: Node, key: str, default_path: Path) -> Path:
        value = node.get_config(key)
        if not value:
            return default_path
        candidate = Path(value)
        if candidate.is_absolute():
            return candidate
        return node.node_path / candidate

    def load_active_nodes(self) -> List[Node]:
        registry = Registry(self.registry_path)
        registry.load()
        nodes: List[Node] = []
        for node_data in registry.nodes.values():
            node = Node(Path(node_data["path"]))
            if node.is_disabled() or not node.is_enabled():
                continue
            try:
                node.load_config()
            except FileNotFoundError:
                continue
            node.inbox_path = self._resolve_configured_path(node, "INBOX_DIR", node.inbox_path)
            node.outbox_path = self._resolve_configured_path(node, "OUTBOX_DIR", node.outbox_path)
            nodes.append(node)
        return nodes

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
        for node in nodes:
            self.process_pending_outbox(node, nodes)

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
                pending_path = prefix.to_pending(file_path)
                self.broadcast_file(node, pending_path, nodes)

    def setup_watchdog(self) -> None:
        nodes = self.load_active_nodes()
        observer = self.observer_factory()
        for node in nodes:
            observer.schedule(
                JataiWatchdogHandler(self, node.node_path),
                str(node.outbox_path),
                recursive=False,
            )
        observer.start()
        self.observer = observer

    def shutdown_watchdog(self) -> None:
        if self.observer is None:
            return
        self.observer.stop()
        self.observer.join(timeout=5)
        self.observer = None

    def run(self) -> None:
        self.install_signal_handlers()
        self.acquire_singleton()
        try:
            self.startup_scan()
            self.setup_watchdog()
            while not self.stop_event.wait(self.POLL_INTERVAL_SECONDS):
                pass
        finally:
            self.shutdown_watchdog()
            self.release_singleton()

    def stop(self) -> None:
        self.stop_event.set()
