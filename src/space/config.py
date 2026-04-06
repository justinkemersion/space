"""
Project tuning: paths and names the scanner should skip when walking trees.

Edit ``ignored_folders`` / ``ignored_folder_patterns`` below. Names match the
*basename* of each directory (not the full path).
"""

# Directory basenames to omit from recursive size totals (and from Top 5 when
# they are direct children). Add or remove entries to taste.
ignored_folders: list[str] = [
    ".git",
    "node_modules",
    ".node_modules",
    "__pycache__",
    ".venv",
    "venv",
    ".mypy_cache",
    ".pytest_cache",
    ".tox",
    "dist",
    "build",
    ".eggs",
]
# Patterns with *, ?, or [ use fnmatch against the directory basename.
ignored_folder_patterns: list[str] = ["*.egg-info"]

# Filesystem types omitted from the “all volumes” overview (pseudo / RAM disks).
SKIP_FSTYPES: frozenset[str] = frozenset(
    {
        "squashfs",
        "tmpfs",
        "devtmpfs",
        "proc",
        "sysfs",
        "devpts",
        "cgroup2",
        "cgroup",
        "pstore",
        "bpf",
        "tracefs",
        "securityfs",
        "ramfs",
        "hugetlbfs",
        "fusectl",
    }
)

CACHE_WARN_BYTES: int = 2 * 1024**3  # 2 GiB
PACMAN_PKG_CACHE: str = "/var/cache/pacman/pkg"
