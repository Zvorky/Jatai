"""
Background daemon, startup scan, and watchdog integration for Jataí.
"""

import os
import signal
import threading
import time
from pathlib import Path
from typing import List, Optional

from filelock import FileLock, Timeout
from watchdog.events import FileCreatedEvent, FileMovedEvent, FileSystemEventHandler
from watchdog.observers import Observer

from jatai.core.delivery import Delivery
from jatai.core.node import Node
from jatai.core.prefix import Prefix
from jatai.core.registry import Registry


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
        observer_factory=Observer,
    ) -> None:
        self.registry_path = Path(registry_path) if registry_path is not None else Path.home() / ".jatai"
        self.pid_path = Path(pid_path) if pid_path is not None else Path.home() / ".jatai.pid"
        self.observer_factory = observer_factory
        self.stop_event = threading.Event()
        self.observer: Optional[Observer] = None

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

    def broadcast_file(self, source_node: Node, source_file: Path, nodes: List[Node]) -> bool:
        all_delivered = True
        for destination_node in nodes:
            if destination_node.node_path == source_node.node_path:
                continue
            try:
                Delivery(source_file, destination_node.inbox_path).deliver()
            except Exception:
                all_delivered = False

        if all_delivered and source_file.exists():
            Prefix(
                success_prefix=str(source_node.get_config("PREFIX_PROCESSED", "_")),
                error_prefix=str(source_node.get_config("PREFIX_ERROR", "!_")),
            ).add_success_prefix(source_file)
        return all_delivered

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
