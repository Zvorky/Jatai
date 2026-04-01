"""
OS auto-start registration helpers for the Jataí daemon.
"""

import platform
import shutil
import subprocess
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
        """Create the appropriate auto-start configuration file for the host OS and enable it.

        On Linux with systemd: creates and enables a user systemd service.
        On Linux without systemd: falls back to a crontab ``@reboot`` entry.
        On macOS: creates and loads a LaunchAgent plist.
        On Windows: creates a startup script in the Windows Startup folder.
        For other platforms: raises :exc:`NotImplementedError`.

        If any OS-specific registration fails, a clear warning is printed per
        ADR-5.3 and REQ-4.2 — the method never fails silently.
        """
        if self.platform_name == "linux":
            return self._register_linux()

        if self.platform_name == "darwin":
            plist_path = self._register_launch_agent()
            try:
                subprocess.run(["launchctl", "load", str(plist_path)], check=True)
            except subprocess.CalledProcessError as e:
                print(f"Warning: Failed to load launch agent: {e}")
            return plist_path

        if self.platform_name == "windows":
            return self._register_windows_startup_script()

        raise NotImplementedError(f"Unsupported platform for auto-start registration: {self.platform_name}")

    def _register_linux(self) -> Path:
        """Handle Linux auto-start: systemd first, crontab fallback."""
        has_systemd = shutil.which("systemctl") is not None
        if has_systemd:
            service_path = self._register_systemd_user_service()
            enabled = self._enable_systemd_service()
            if not enabled:
                print(
                    "Warning: Could not enable systemd user service. "
                    "Attempting crontab @reboot fallback. "
                    "Run 'systemctl --user enable {0}.service' manually if needed.".format(self.service_name)
                )
                if not self._register_crontab_autostart():
                    print(
                        "Warning: crontab @reboot fallback also failed. "
                        "The daemon may not auto-start on boot. "
                        "Please configure auto-start manually."
                    )
            return service_path
        else:
            # No systemd: try crontab @reboot as the primary fallback.
            crontab_marker = self._get_crontab_marker_path()
            registered = self._register_crontab_autostart()
            if registered:
                crontab_marker.parent.mkdir(parents=True, exist_ok=True)
                crontab_marker.write_text(
                    f"# Jatai auto-start registered via crontab @reboot\n"
                    f"# Entry: @reboot {self._daemon_exec_start()}\n",
                    encoding="utf-8",
                )
                return crontab_marker
            else:
                print(
                    "Warning: Neither systemd nor crontab are available. "
                    "The daemon may not auto-start on boot. "
                    "Please configure auto-start manually."
                )
                # Return a placeholder path so callers don't crash.
                return crontab_marker

    def _get_crontab_marker_path(self) -> Path:
        """Return a marker file path documenting the crontab registration."""
        return self.home_path / ".config" / "jatai" / f"{self.service_name}-crontab.txt"

    def _register_crontab_autostart(self) -> bool:
        """Register daemon auto-start via ``crontab @reboot`` as a fallback.

        Returns ``True`` if the entry was successfully added (or already present),
        ``False`` if crontab is unavailable or the operation failed.
        """
        if shutil.which("crontab") is None:
            return False

        daemon_cmd = self._daemon_exec_start()
        cron_entry = f"@reboot {daemon_cmd}"

        try:
            result = subprocess.run(
                ["crontab", "-l"],
                capture_output=True,
                text=True,
            )
            current = result.stdout if result.returncode == 0 else ""
        except Exception:
            return False

        # Idempotent: skip if the entry is already present.
        if cron_entry in current:
            return True

        new_crontab = current.rstrip("\n") + ("\n" if current else "") + cron_entry + "\n"
        try:
            proc = subprocess.run(
                ["crontab", "-"],
                input=new_crontab,
                text=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return proc.returncode == 0
        except Exception:
            return False

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

    def _enable_systemd_service(self) -> bool:
        if shutil.which("systemctl") is None:
            return False

        try:
            subprocess.run(
                ["systemctl", "--user", "enable", f"{self.service_name}.service"],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False
        except Exception:
            return False

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
        """Create a ``@reboot``-equivalent VBScript in the Windows Startup folder.

        The script silently starts the daemon in the background every time the
        user logs in, equivalent to a ``@reboot`` cron entry on Linux.
        """
        startup_dir = (
            self.home_path
            / "AppData"
            / "Roaming"
            / "Microsoft"
            / "Windows"
            / "Start Menu"
            / "Programs"
            / "Startup"
        )
        startup_dir.mkdir(parents=True, exist_ok=True)
        script_path = startup_dir / f"{self.service_name}.vbs"
        daemon_exec = self._daemon_exec_start()
        script_path.write_text(
            f'Set WshShell = CreateObject("WScript.Shell")\n'
            f'WshShell.Run "{daemon_exec}", 0, False\n',
            encoding="utf-8",
        )
        return script_path
