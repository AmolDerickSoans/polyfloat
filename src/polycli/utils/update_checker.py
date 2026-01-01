"""Update checking and auto-update functionality."""
import asyncio
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from polycli import __version__

console = Console()

PYPI_URL = "https://pypi.org/pypi/polyfloat/json"
CONFIG_DIR = Path.home() / ".polycli"
BACKUP_DIR = CONFIG_DIR / "backups"
CACHE_FILE = CONFIG_DIR / "update_cache.json"

MIN_DISK_SPACE_MB = 100
MAX_RETRIES = 2
RETRY_DELAY_SECONDS = 5


@dataclass
class UpdateConfig:
    """Configuration for auto-update behavior."""

    enabled: bool = True
    mode: str = "auto"
    channel: str = "stable"
    frequency: str = "startup"
    last_check: Optional[str] = None
    skip_version: Optional[str] = None
    max_retries: int = MAX_RETRIES

    @classmethod
    def load(cls) -> "UpdateConfig":
        """Load config from file or return defaults."""
        config_file = CONFIG_DIR / "config.yaml"
        if not config_file.exists():
            return cls()

        try:
            import yaml

            with open(config_file) as f:
                data = yaml.safe_load(f) or {}
            updates = data.get("updates", {})
            return cls(
                enabled=updates.get("enabled", True),
                mode=updates.get("mode", "auto"),
                channel=updates.get("channel", "stable"),
                frequency=updates.get("frequency", "startup"),
                last_check=updates.get("last_check"),
                skip_version=updates.get("skip_version"),
                max_retries=updates.get("max_retries", MAX_RETRIES),
            )
        except Exception:
            return cls()

    def save(self) -> None:
        """Save config to file."""
        import yaml

        config_file = CONFIG_DIR / "config.yaml"

        existing = {}
        if config_file.exists():
            try:
                with open(config_file) as f:
                    existing = yaml.safe_load(f) or {}
            except Exception:
                pass

        if "updates" not in existing:
            existing["updates"] = {}

        existing["updates"].update(
            {
                "enabled": self.enabled,
                "mode": self.mode,
                "channel": self.channel,
                "frequency": self.frequency,
                "last_check": self.last_check,
                "skip_version": self.skip_version,
                "max_retries": self.max_retries,
            }
        )

        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(config_file, "w") as f:
            yaml.dump(existing, f)


@dataclass
class UpdateInfo:
    """Information about an available update."""

    current_version: str
    latest_version: str
    channel: str
    release_date: Optional[str] = None
    download_url: Optional[str] = None
    release_notes: Optional[str] = None
    is_major: bool = False


@dataclass
class UpdateResult:
    """Result of an update operation."""

    success: bool
    from_version: str
    to_version: str
    message: str
    rolled_back: bool = False
    error: Optional[str] = None


@dataclass
class CacheEntry:
    """Cached update check result."""

    latest_version: str
    channel: str
    checked_at: str
    expires_at: str


class UpdateChecker:
    """Handles update checking and auto-update functionality."""

    def __init__(self):
        self.config = UpdateConfig.load()
        self._cache: dict[str, CacheEntry] = self._load_cache()

    def _load_cache(self) -> dict:
        """Load update cache from file."""
        if not CACHE_FILE.exists():
            return {}
        try:
            with open(CACHE_FILE) as f:
                return json.load(f)
        except Exception:
            return {}

    def _save_cache(self) -> None:
        """Save update cache to file."""
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(CACHE_FILE, "w") as f:
            json.dump(self._cache, f)

    def _is_cache_valid(self, channel: str) -> bool:
        """Check if cached entry is still valid."""
        entry = self._cache.get(channel)
        if not entry:
            return False

        try:
            expires = datetime.fromisoformat(entry.expires_at)
            checked = datetime.fromisoformat(entry.checked_at)
            now = datetime.now(timezone.utc)

            if now > expires:
                return False

            if self.config.frequency == "startup":
                return False
            elif self.config.frequency == "daily":
                return (now - checked).days < 1
            elif self.config.frequency == "weekly":
                return (now - checked).days < 7

            return False
        except Exception:
            return False

    def _should_check(self, force: bool = False) -> bool:
        """Determine if we should check for updates."""
        if not self.config.enabled:
            return False
        if force:
            return True
        if self._is_cache_valid(self.config.channel):
            return False
        return True

    async def _get_pypi_version(self, channel: str = "stable") -> Optional[str]:
        """Get latest version from PyPI."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(PYPI_URL, follow_redirects=True)
                response.raise_for_status()
                data = response.json()
                version = data["info"]["version"]

                if channel == "stable":
                    if any(c in version for c in ["a", "b", "rc", "alpha", "beta"]):
                        return None
                elif channel == "beta":
                    if "rc" in version or "alpha" in version:
                        return None
                elif channel == "latest":
                    pass

                return version
        except Exception:
            return None

    def _version_tuple(self, version: str) -> tuple:
        """Convert version string to tuple for comparison."""
        clean = version.replace("v", "").split("+")[0]
        parts = []
        for part in clean.split("."):
            try:
                parts.append(int(part))
            except ValueError:
                parts.append(0)
        while len(parts) < 3:
            parts.append(0)
        return tuple(parts)

    def _version_greater(self, v1: str, v2: str) -> bool:
        """Check if v1 is greater than v2."""
        return self._version_tuple(v1) > self._version_tuple(v2)

    def _is_major_update(self, current: str, latest: str) -> bool:
        """Check if update is a major version bump."""
        current_major = self._version_tuple(current)[0]
        latest_major = self._version_tuple(latest)[0]
        return latest_major > current_major

    async def check_update(self, force: bool = False) -> Optional[UpdateInfo]:
        """Check if an update is available."""
        if not self._should_check(force):
            entry = self._cache.get(self.config.channel)
            if entry:
                return UpdateInfo(
                    current_version=__version__,
                    latest_version=entry.latest_version,
                    channel=self.config.channel,
                )
            return None

        latest_version = await self._get_pypi_version(self.config.channel)

        if not latest_version:
            return None

        if latest_version == self.config.skip_version:
            return None

        if not self._version_greater(latest_version, __version__):
            self._cache[self.config.channel] = CacheEntry(
                latest_version=latest_version,
                channel=self.config.channel,
                checked_at=datetime.now(timezone.utc).isoformat(),
                expires_at=datetime.now(timezone.utc).isoformat(),
            )
            self._save_cache()
            self.config.last_check = datetime.now(timezone.utc).isoformat()
            self.config.save()
            return None

        is_major = self._is_major_update(__version__, latest_version)

        cache_entry = CacheEntry(
            latest_version=latest_version,
            channel=self.config.channel,
            checked_at=datetime.now(timezone.utc).isoformat(),
            expires_at=datetime.now(timezone.utc).isoformat(),
        )
        self._cache[self.config.channel] = cache_entry
        self._save_cache()

        self.config.last_check = datetime.now(timezone.utc).isoformat()
        self.config.save()

        return UpdateInfo(
            current_version=__version__,
            latest_version=latest_version,
            channel=self.config.channel,
            is_major=is_major,
        )

    def _check_disk_space(self) -> bool:
        """Check if enough disk space is available."""
        try:
            stat = shutil.disk_usage(".")
            free_mb = stat.free / (1024 * 1024)
            return free_mb >= MIN_DISK_SPACE_MB
        except Exception:
            return True

    def _check_pip_available(self) -> bool:
        """Check if pip is available."""
        try:
            subprocess.run(
                [sys.executable, "-m", "pip", "--version"],
                capture_output=True,
                timeout=5,
            )
            return True
        except Exception:
            return False

    def _check_network(self) -> bool:
        """Check if network is available."""
        try:
            import socket

            socket.create_connection(("pypi.org", 443), timeout=5)
            return True
        except Exception:
            return False

    def _create_backup(self) -> Optional[Path]:
        """Create a backup of the current installation."""
        try:
            backup_dir = BACKUP_DIR / __version__
            if backup_dir.exists():
                shutil.rmtree(backup_dir)
            backup_dir.mkdir(parents=True, exist_ok=True)

            result = subprocess.run(
                [sys.executable, "-m", "pip", "show", "polyfloat"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                with open(backup_dir / "pip_show.txt", "w") as f:
                    f.write(result.stdout)

            subprocess.run(
                [sys.executable, "-m", "pip", "download", f"polyfloat=={__version__}"],
                cwd=backup_dir,
                capture_output=True,
                timeout=120,
            )

            config_file = CONFIG_DIR / "config.yaml"
            if config_file.exists():
                shutil.copy(config_file, backup_dir / "config.yaml")

            return backup_dir
        except Exception:
            return None

    def _restore_backup(self, backup_path: Path) -> bool:
        """Restore from a backup."""
        try:
            whl_file = None
            for f in backup_path.glob("polyfloat-*.whl"):
                whl_file = f
                break

            if whl_file:
                subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "pip",
                        "install",
                        "--force-reinstall",
                        str(whl_file),
                    ],
                    capture_output=True,
                    timeout=120,
                )
            return True
        except Exception:
            return False

    async def _perform_pip_upgrade(self, channel: str) -> tuple[bool, Optional[str]]:
        """Perform the pip upgrade."""
        try:
            if channel == "stable":
                cmd = [sys.executable, "-m", "pip", "install", "--upgrade", "polyfloat"]
            elif channel == "beta":
                cmd = [
                    sys.executable,
                    "-m",
                    "pip",
                    "install",
                    "--upgrade",
                    "--pre",
                    "polyfloat",
                ]
            else:
                cmd = [sys.executable, "-m", "pip", "install", "--upgrade", "polyfloat"]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,
            )

            if result.returncode == 0:
                return True, None
            else:
                return False, result.stderr
        except subprocess.TimeoutExpired:
            return False, "Upgrade timed out"
        except Exception as e:
            return False, str(e)

    async def _verify_installation(self) -> bool:
        """Verify the installation works after upgrade."""
        try:
            result = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    "import polyfloat; print(polyfloat.__version__)",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            return result.returncode == 0 and __version__ in result.stdout
        except Exception:
            return False

    async def perform_update(
        self, channel: Optional[str] = None, mode: str = "auto"
    ) -> UpdateResult:
        """Perform the update."""
        target_channel = channel or self.config.channel

        if mode == "disabled":
            return UpdateResult(
                success=False,
                from_version=__version__,
                to_version="",
                message="Updates are disabled",
            )

        if not self._check_disk_space():
            return UpdateResult(
                success=False,
                from_version=__version__,
                to_version="",
                message=f"Insufficient disk space (need {MIN_DISK_SPACE_MB}MB)",
            )

        if not self._check_pip_available():
            return UpdateResult(
                success=False,
                from_version=__version__,
                to_version="",
                message="pip is not available",
            )

        if not self._check_network():
            return UpdateResult(
                success=False,
                from_version=__version__,
                to_version="",
                message="Network is not available",
            )

        backup_path = self._create_backup()
        current_version = __version__

        update_info = await self.check_update(force=True)
        if not update_info:
            return UpdateResult(
                success=False,
                from_version=__version__,
                to_version="",
                message="No update available",
            )

        target_version = update_info.latest_version
        error: Optional[str] = None

        for attempt in range(self.config.max_retries + 1):
            success, error = await self._perform_pip_upgrade(target_channel)

            if success and await self._verify_installation():
                self.config.last_check = datetime.now(timezone.utc).isoformat()
                self.config.save()
                return UpdateResult(
                    success=True,
                    from_version=current_version,
                    to_version=target_version,
                    message=f"Updated from {current_version} to {target_version}",
                )

            if attempt < self.config.max_retries:
                await asyncio.sleep(RETRY_DELAY_SECONDS)

        rollback_success = False
        if backup_path and self._restore_backup(backup_path):
            rollback_success = True
            self.config.enabled = False
            self.config.save()

        return UpdateResult(
            success=False,
            from_version=current_version,
            to_version=target_version,
            message="Update failed",
            rolled_back=rollback_success,
            error=error,
        )


def format_update_notification(info: UpdateInfo) -> Panel:
    """Format the update notification banner."""
    if info.is_major:
        title = "Major Update Available"
        style = "red"
    else:
        title = "Update Available"
        style = "yellow"

    text = Text()
    text.append(f"Current version: {info.current_version}\n", style="dim")
    text.append(
        f"Latest version:  {info.latest_version} ({info.channel})\n\n",
        style="bold green",
    )
    text.append("Run: ", style="dim")
    text.append("poly update", style="bold cyan")
    text.append("  OR  ", style="dim")
    text.append("pip install --upgrade polyfloat", style="bold cyan")

    return Panel(
        text,
        title=f" {title} ",
        border_style=style,
        expand=False,
    )


def format_update_success(result: UpdateResult) -> Panel:
    """Format the update success message."""
    text = Text()
    text.append("Update Successful!\n\n", style="bold green")
    text.append(f"From: {result.from_version}\n", style="dim")
    text.append(f"To:   {result.to_version}\n", style="bold green")

    return Panel(
        text,
        title=" Update Complete ",
        border_style="green",
        expand=False,
    )


def format_update_failure(result: UpdateResult) -> Panel:
    """Format the update failure message."""
    text = Text()
    text.append("Update Failed\n\n", style="bold red")
    text.append(
        f"Attempted: {result.from_version} -> {result.to_version}\n\n", style="dim"
    )

    if result.error:
        err_text = result.error[:200] if len(result.error) > 200 else result.error
        text.append(f"Error: {err_text}\n\n", style="red")

    if result.rolled_back:
        text.append("Rolled back to previous version\n", style="yellow")
        text.append("Auto-update has been disabled\n\n", style="yellow")
        text.append("Run: poly config set updates.enabled=false\n", style="dim")
        text.append("Then: poly update --mode=notify", style="dim")
    else:
        text.append("Could not restore backup\n", style="red")
        text.append(
            f"Please manually reinstall: pip install polyfloat=={result.from_version}\n",
            style="dim",
        )

    return Panel(
        text,
        title=" Update Failed ",
        border_style="red",
        expand=False,
    )
