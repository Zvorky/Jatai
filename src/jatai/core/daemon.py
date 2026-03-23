"""
Background daemon, startup scan, and watchdog integration for Jataí.
"""

import os
import signal
import threading
from pathlib import Path
from typing import Dict, List, Optional

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
        self.node_config_cache: Dict[Path, Dict[str, object]] = {}

    def _load_registry(self) -> Registry:
        registry = Registry(self.registry_path)
        registry.load()
        return registry

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
            if not node.node_path.exists():
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
        for node in registered_nodes:
            self.observer.schedule(
                JataiNodeConfigHandler(self, node.node_path),
                str(node.node_path),
                recursive=False,
            )

        for node in registered_nodes:
            if node.is_disabled() or not node.is_enabled():
                self._remove_node_cache(node.node_path)
                continue
            self.observer.schedule(
                JataiWatchdogHandler(self, node.node_path),
                str(node.outbox_path),
                recursive=False,
            )
            self._update_node_cache(node)

    def handle_node_config_change(self, node_path: Path) -> None:
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
                node.backup_current_config(previous_config)
                try:
                    node.migrate_prefix_history(previous_config, node.local_config)
                except Exception as exc:
                    node.write_config(previous_config)
                    node.local_config = dict(previous_config)
                    node.apply_effective_config(registry.global_config)
                    node.drop_error_notice(
                        f"Prefix migration aborted and configuration restored.\n\nReason: {exc}\n",
                        error_prefix=str(previous_config.get("PREFIX_ERROR", "!_")),
                    )

        if node.is_enabled() and not node.is_disabled():
            self._update_node_cache(node)
        else:
            self._remove_node_cache(node.node_path)

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
