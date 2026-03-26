"""
OS auto-start registration helpers for the Jataí daemon.
"""

import platform
import sys
from pathlib import Path
from typing import Optional


class AutoStartRegistrar:
    """Create host-specific auto-start configuration for the daemon."""

    def __init__(
        self,
        service_name: str = "jatai",
        home_path: Optional[Path] = None,
        platform_name: Optional[str] = None,
        python_executable: Optional[str] = None,
    ) -> None:
        self.service_name = service_name
        self.home_path = Path(home_path) if home_path is not None else Path.home()
        self.platform_name = platform_name or platform.system().lower()
        self.python_executable = python_executable or sys.executable

    def register(self) -> Path:
        """Create the appropriate auto-start configuration file for the host OS and enable it."""
        if self.platform_name == "linux":
            service_path = self._register_systemd_user_service()
            # Enable the service for user
            import subprocess
            try:
                subprocess.run([
                    "systemctl", "--user", "enable", f"{self.service_name}.service"
                ], check=True)
            except Exception as e:
                print(f"Warning: Failed to enable systemd user service: {e}")
            return service_path
        if self.platform_name == "darwin":
            plist_path = self._register_launch_agent()
            import subprocess
            try:
                subprocess.run([
                    "launchctl", "load", str(plist_path)
                ], check=True)
            except Exception as e:
                print(f"Warning: Failed to load launch agent: {e}")
            return plist_path
        if self.platform_name == "windows":
            return self._register_windows_startup_script()
        raise NotImplementedError(f"Unsupported platform for auto-start registration: {self.platform_name}")

    def _daemon_exec_start(self) -> str:
        return f'"{self.python_executable}" -m jatai.cli.main _daemon-run'

    def _register_systemd_user_service(self) -> Path:
        service_dir = self.home_path / ".config" / "systemd" / "user"
        service_dir.mkdir(parents=True, exist_ok=True)
        service_path = service_dir / f"{self.service_name}.service"
        service_path.write_text(
            "[Unit]\n"
            "Description=Jataí background daemon\n"
            "After=default.target\n\n"
            "[Service]\n"
            "Type=simple\n"
            f"ExecStart={self._daemon_exec_start()}\n"
            "Restart=on-failure\n\n"
            "[Install]\n"
            "WantedBy=default.target\n",
            encoding="utf-8",
        )
        return service_path

    def _register_launch_agent(self) -> Path:
        plist_dir = self.home_path / "Library" / "LaunchAgents"
        plist_dir.mkdir(parents=True, exist_ok=True)
        plist_path = plist_dir / f"{self.service_name}.plist"
        plist_path.write_text(
            "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
            "<!DOCTYPE plist PUBLIC \"-//Apple//DTD PLIST 1.0//EN\" \"http://www.apple.com/DTDs/PropertyList-1.0.dtd\">\n"
            "<plist version=\"1.0\">\n"
            "<dict>\n"
            f"  <key>Label</key><string>{self.service_name}</string>\n"
            "  <key>ProgramArguments</key>\n"
            "  <array>\n"
            f"    <string>{self.python_executable}</string>\n"
            "    <string>-m</string>\n"
            "    <string>jatai.cli.main</string>\n"
            "    <string>_daemon-run</string>\n"
            "  </array>\n"
            "  <key>RunAtLoad</key><true/>\n"
            "</dict>\n"
            "</plist>\n",
            encoding="utf-8",
        )
        return plist_path

    def _register_windows_startup_script(self) -> Path:
        startup_dir = self.home_path / "AppData" / "Roaming" / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
        startup_dir.mkdir(parents=True, exist_ok=True)
        script_path = startup_dir / f"{self.service_name}.cmd"
        script_path.write_text(
            f'@echo off\nstart "" "{self.python_executable}" -m jatai.cli.main _daemon-run\n',
            encoding="utf-8",
        )
        return script_path
