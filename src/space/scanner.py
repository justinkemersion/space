"""
Filesystem inspection: sizes, partitions, Arch cache hints.
"""

from __future__ import annotations

import fnmatch
import os
from dataclasses import dataclass
from typing import Iterator

import psutil

from . import config


@dataclass(frozen=True)
class PartitionInfo:
    mountpoint: str
    fstype: str
    opts: str


@dataclass(frozen=True)
class PartitionUsage:
    mountpoint: str
    total: int
    used: int
    free: int
    percent: float


@dataclass(frozen=True)
class CleanupHint:
    """Arch cache over threshold."""

    label: str
    size_bytes: int
    suggestion: str


class DiskScanner:
    """Collect disk and directory metrics (no terminal output)."""

    def __init__(
        self,
        *,
        ignored_folders: list[str] | None = None,
        ignored_folder_patterns: list[str] | None = None,
    ) -> None:
        names = list(
            config.ignored_folders if ignored_folders is None else ignored_folders
        )
        pats = list(
            config.ignored_folder_patterns
            if ignored_folder_patterns is None
            else ignored_folder_patterns
        )
        self._ignored_names = frozenset(names)
        self._ignored_patterns = tuple(pats)

    def _ignored_dir_name(self, name: str) -> bool:
        if name in self._ignored_names:
            return True
        for pat in self._ignored_patterns:
            if fnmatch.fnmatch(name, pat):
                return True
        return False

    @staticmethod
    def kernel_vfs_path(path: str) -> bool:
        """True if path is under Linux kernel pseudo filesystems."""
        if os.name != "posix":
            return False
        try:
            p = os.path.realpath(path)
        except OSError:
            return True
        for root in ("/proc", "/sys"):
            if p == root or p.startswith(root + os.sep):
                return True
        if p == "/run" or p.startswith("/run" + os.sep):
            return True
        return False

    def dir_size_scandir(self, path: str, *, st_dev: int | None = None) -> int:
        """Recursive byte total under *path* (no symlinks); optional one-filesystem."""
        if self.kernel_vfs_path(path):
            return 0
        total = 0
        stack = [path]
        while stack:
            current = stack.pop()
            try:
                with os.scandir(current) as it:
                    for entry in it:
                        try:
                            if entry.is_symlink():
                                continue
                            if entry.is_file(follow_symlinks=False):
                                st = entry.stat(follow_symlinks=False)
                                if st_dev is not None and st.st_dev != st_dev:
                                    continue
                                total += st.st_size
                            elif entry.is_dir(follow_symlinks=False):
                                if self._ignored_dir_name(entry.name):
                                    continue
                                child = entry.path
                                if self.kernel_vfs_path(child):
                                    continue
                                if st_dev is not None:
                                    st = entry.stat(follow_symlinks=False)
                                    if st.st_dev != st_dev:
                                        continue
                                stack.append(child)
                        except OSError:
                            continue
            except OSError:
                continue
        return total

    def path_size_bytes(self, path: str, *, one_filesystem: bool = False) -> int:
        if os.path.isfile(path) or (
            os.path.islink(path) and not os.path.isdir(path)
        ):
            return os.path.getsize(path)
        st_d: int | None = None
        if one_filesystem:
            st_d = os.stat(path, follow_symlinks=False).st_dev
        return self.dir_size_scandir(path, st_dev=st_d)

    def top_five_direct_children(
        self, dirpath: str, *, st_dev: int | None = None
    ) -> list[tuple[str, int]]:
        items: list[tuple[str, int]] = []
        try:
            with os.scandir(dirpath) as it:
                for entry in it:
                    try:
                        if entry.is_symlink():
                            continue
                        if self._ignored_dir_name(entry.name):
                            continue
                        if entry.is_file(follow_symlinks=False):
                            st = entry.stat(follow_symlinks=False)
                            if st_dev is not None and st.st_dev != st_dev:
                                continue
                            items.append((entry.name, st.st_size))
                        elif entry.is_dir(follow_symlinks=False):
                            child = entry.path
                            if self.kernel_vfs_path(child):
                                continue
                            if st_dev is not None:
                                st = entry.stat(follow_symlinks=False)
                                if st.st_dev != st_dev:
                                    continue
                            sz = self.dir_size_scandir(child, st_dev=st_dev)
                            items.append((entry.name + "/", sz))
                    except OSError:
                        continue
        except OSError:
            return []
        items.sort(key=lambda x: x[1], reverse=True)
        return items[:5]

    def iter_partition_usage(self) -> Iterator[tuple[PartitionInfo, PartitionUsage | None]]:
        for part in psutil.disk_partitions(all=False):
            if os.name == "nt":
                if "fixed" not in part.opts:
                    continue
            elif part.fstype in config.SKIP_FSTYPES:
                continue
            info = PartitionInfo(
                mountpoint=part.mountpoint,
                fstype=part.fstype,
                opts=part.opts,
            )
            try:
                u = psutil.disk_usage(part.mountpoint)
                yield info, PartitionUsage(
                    mountpoint=part.mountpoint,
                    total=u.total,
                    used=u.used,
                    free=u.free,
                    percent=u.percent,
                )
            except (OSError, PermissionError):
                yield info, None

    @staticmethod
    def is_arch_linux() -> bool:
        return os.path.exists("/etc/arch-release")

    def safe_dir_size(self, path: str) -> int | None:
        if not os.path.isdir(path):
            return None
        try:
            with os.scandir(path):
                pass
        except OSError:
            return None
        return self.dir_size_scandir(path, st_dev=None)

    @staticmethod
    def yay_cache_path() -> str:
        base = os.environ.get("XDG_CACHE_HOME", "").strip()
        if base:
            return os.path.join(base, "yay")
        return os.path.expanduser("~/.cache/yay")

    def arch_cleanup_hints(self) -> list[CleanupHint]:
        if not self.is_arch_linux():
            return []
        out: list[CleanupHint] = []
        pac_sz = self.safe_dir_size(config.PACMAN_PKG_CACHE)
        if pac_sz is not None and pac_sz >= config.CACHE_WARN_BYTES:
            out.append(
                CleanupHint(
                    label="pacman pkg cache",
                    size_bytes=pac_sz,
                    suggestion=(
                        "sudo pacman -Sc  (uninstalled only) or "
                        "sudo pacman -Scc  (full cache)"
                    ),
                )
            )
        yay_path = self.yay_cache_path()
        if os.path.isdir(yay_path):
            yay_sz = self.safe_dir_size(yay_path)
            if yay_sz is not None and yay_sz >= config.CACHE_WARN_BYTES:
                out.append(
                    CleanupHint(
                        label="yay cache",
                        size_bytes=yay_sz,
                        suggestion=(
                            "yay -Yc  and/or remove ~/.cache/yay when "
                            "AUR sources are not needed"
                        ),
                    )
                )
        return out

    @staticmethod
    def resolve_path(path: str) -> str:
        return os.path.realpath(path)

    @staticmethod
    def volume_usage(path: str) -> tuple[int, int, int, float] | None:
        """Returns (total, used, free, percent) or None."""
        try:
            u = psutil.disk_usage(path)
            return u.total, u.used, u.free, u.percent
        except (OSError, PermissionError):
            return None
