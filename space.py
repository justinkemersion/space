#!/usr/bin/env python3
"""
space — show disk partitions or how much space a path uses (human-readable).
"""

from __future__ import annotations

import argparse
import os
import sys

import psutil
from rich.console import Console
from rich.table import Table
from rich.text import Text

console = Console()

# Skip pseudo / memory filesystems so the default view stays “real disks”.
SKIP_FSTYPES = frozenset(
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

CACHE_WARN_BYTES = 2 * 1024**3  # 2 GiB
PACMAN_PKG_CACHE = "/var/cache/pacman/pkg"


def _kernel_vfs_path(path: str) -> bool:
    """True if path is under Linux kernel pseudo filesystems (huge / non-disk)."""
    if os.name != "posix":
        return False
    try:
        p = os.path.realpath(path)
    except OSError:
        return True
    for root in ("/proc", "/sys"):
        if p == root or p.startswith(root + os.sep):
            return True
    # tmpfs; sizing under /run is slow and not “on disk” for the root volume.
    if p == "/run" or p.startswith("/run" + os.sep):
        return True
    return False


def terminal_table_width() -> int:
    """Use full terminal width with a sane default for non-TTY / narrow cases."""
    w = console.width
    if w is None or w < 50:
        return 80
    return w


def bar_cell_count() -> int:
    """Scale bar length slightly with terminal size."""
    tw = terminal_table_width()
    return max(10, min(22, tw // 5))


def human_bytes(n: float) -> str:
    """Turn a byte count into a short, readable string (1024-based)."""
    if n < 0:
        n = 0.0
    for unit in ("B", "KiB", "MiB", "GiB", "TiB", "PiB"):
        if abs(n) < 1024.0:
            if unit == "B":
                return f"{int(n):,} B"
            return f"{n:.2f} {unit}"
        n /= 1024.0
    return f"{n:.2f} EiB"


def heat_rgb(percent: float) -> tuple[int, int, int]:
    """Smooth green → yellow → red for 0–100 (% full or relative weight)."""
    p = max(0.0, min(100.0, float(percent))) / 100.0
    if p < 0.5:
        t = p * 2.0
        r = int(255 * t)
        g = 255
        b = int(40 * (1.0 - t))
    else:
        t = (p - 0.5) * 2.0
        r = 255
        g = int(255 * (1.0 - t))
        b = 0
    return r, g, b


def gradient_usage_bar(percent: float, width: int | None = None) -> Text:
    """Block bar with per-cell color gradient (green→red) by fill level."""
    if width is None:
        width = bar_cell_count()
    pct = max(0.0, min(100.0, float(percent)))
    filled = max(0, min(width, int(round(width * pct / 100.0))))
    out = Text()
    for i in range(width):
        ch = "█" if i < filled else "░"
        if i < filled:
            # Along the filled span, ramp heat so the bar reads as “filling up”.
            cell_pct = ((i + 1) / width) * 100.0
            blend = min(100.0, (cell_pct + pct) / 2.0)
            r, g, b = heat_rgb(blend)
            out.append(ch, style=f"#{r:02x}{g:02x}{b:02x}")
        else:
            out.append(ch, style="dim")
    out.append(f" {pct:.1f}%", style="default")
    return out


def relative_gradient_bar(size: int, largest: int, width: int | None = None) -> Text:
    """Bar for comparing sizes (largest in the set = full bar)."""
    if width is None:
        width = bar_cell_count()
    if largest <= 0:
        pct = 0.0
    else:
        pct = min(100.0, 100.0 * float(size) / float(largest))
    filled = max(0, min(width, int(round(width * pct / 100.0))))
    out = Text()
    for i in range(width):
        ch = "█" if i < filled else "░"
        if i < filled:
            cell_pct = ((i + 1) / width) * pct
            r, g, b = heat_rgb(cell_pct)
            out.append(ch, style=f"#{r:02x}{g:02x}{b:02x}")
        else:
            out.append(ch, style="dim")
    out.append(f" {pct:.1f}%", style="default")
    return out


def dir_size_scandir(path: str, *, st_dev: int | None = None) -> int:
    """Total bytes under a directory (no symlink following), using scandir.

    If *st_dev* is set (device id of the starting volume), do not cross into
    other mount points — same idea as ``du -x``. Kernel pseudo paths under
    /proc, /sys, and /run are never descended into.
    """
    if _kernel_vfs_path(path):
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
                            child = entry.path
                            if _kernel_vfs_path(child):
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


def path_size_bytes(path: str, *, one_filesystem: bool = False) -> int:
    """Total bytes used by a file or everything under a directory."""
    if os.path.isfile(path) or (os.path.islink(path) and not os.path.isdir(path)):
        return os.path.getsize(path)
    st_d: int | None = None
    if one_filesystem:
        st_d = os.stat(path, follow_symlinks=False).st_dev
    return dir_size_scandir(path, st_dev=st_d)


def top_five_direct_children(
    dirpath: str, *, st_dev: int | None = None
) -> list[tuple[str, int]]:
    """Largest immediate files/subdirectories by total size (dirs summed recursively)."""
    items: list[tuple[str, int]] = []
    try:
        with os.scandir(dirpath) as it:
            for entry in it:
                try:
                    if entry.is_symlink():
                        continue
                    if entry.is_file(follow_symlinks=False):
                        st = entry.stat(follow_symlinks=False)
                        if st_dev is not None and st.st_dev != st_dev:
                            continue
                        items.append((entry.name, st.st_size))
                    elif entry.is_dir(follow_symlinks=False):
                        child = entry.path
                        if _kernel_vfs_path(child):
                            continue
                        if st_dev is not None:
                            st = entry.stat(follow_symlinks=False)
                            if st.st_dev != st_dev:
                                continue
                        sz = dir_size_scandir(child, st_dev=st_dev)
                        items.append((entry.name + "/", sz))
                except OSError:
                    continue
    except OSError:
        return []
    items.sort(key=lambda x: x[1], reverse=True)
    return items[:5]


def is_arch_linux() -> bool:
    return os.path.exists("/etc/arch-release")


def safe_dir_size(path: str) -> int | None:
    """Return byte size of directory tree, or None if unreadable."""
    if not os.path.isdir(path):
        return None
    try:
        with os.scandir(path):
            pass
    except OSError:
        return None
    return dir_size_scandir(path, st_dev=None)


def yay_cache_path() -> str:
    base = os.environ.get("XDG_CACHE_HOME", "").strip()
    if base:
        return os.path.join(base, "yay")
    return os.path.expanduser("~/.cache/yay")


def smart_cleanup_arch() -> None:
    """On Arch, warn when pacman / yay caches exceed CACHE_WARN_BYTES."""
    if not is_arch_linux():
        return

    rows: list[tuple[str, str, str]] = []
    pac_sz = safe_dir_size(PACMAN_PKG_CACHE)
    if pac_sz is not None and pac_sz >= CACHE_WARN_BYTES:
        rows.append(
            (
                "pacman pkg cache",
                human_bytes(pac_sz),
                "sudo pacman -Sc  (uninstalled only) or sudo pacman -Scc  (full cache)",
            )
        )

    yay_path = yay_cache_path()
    if os.path.isdir(yay_path):
        yay_sz = safe_dir_size(yay_path)
        if yay_sz is not None and yay_sz >= CACHE_WARN_BYTES:
            rows.append(
                (
                    "yay cache",
                    human_bytes(yay_sz),
                    "yay -Yc  and/or remove ~/.cache/yay when AUR sources are not needed",
                )
            )

    if not rows:
        return

    tw = terminal_table_width()
    t = Table(
        title="Smart cleanup (Arch)",
        caption=f"Caches at or above {human_bytes(CACHE_WARN_BYTES)} trigger a hint.",
        header_style="bold magenta",
        width=tw,
        expand=True,
    )
    t.add_column(
        "Location",
        style="cyan",
        overflow="ellipsis",
        max_width=max(16, tw // 5),
    )
    t.add_column("Size", justify="right", max_width=12)
    t.add_column("Suggestion", overflow="ellipsis", max_width=max(24, tw // 2))
    for row in rows:
        t.add_row(*row)
    console.print(t)


def iter_disk_partitions():
    """Yield mount points we care about for a “physical-ish” overview."""
    for part in psutil.disk_partitions(all=False):
        if os.name == "nt":
            if "fixed" not in part.opts:
                continue
        elif part.fstype in SKIP_FSTYPES:
            continue
        yield part


def show_all_partitions() -> None:
    tw = terminal_table_width()
    table = Table(
        title="Disk space (all volumes)",
        caption="Sizes use binary units (KiB, MiB, GiB, …). Bars run green→red as usage grows.",
        header_style="bold magenta",
        show_lines=False,
        width=tw,
        expand=True,
    )
    table.add_column(
        "Mount",
        style="cyan",
        overflow="ellipsis",
        no_wrap=True,
        max_width=max(14, tw // 5),
    )
    table.add_column("Total", justify="right", max_width=11)
    table.add_column("Used", justify="right", max_width=11)
    table.add_column("Free", justify="right", max_width=11)
    table.add_column(
        "Usage",
        justify="left",
        overflow="ellipsis",
        max_width=max(28, tw // 3),
    )

    for part in iter_disk_partitions():
        try:
            usage = psutil.disk_usage(part.mountpoint)
        except (OSError, PermissionError):
            table.add_row(
                part.mountpoint,
                "—",
                "—",
                "—",
                "[dim]not accessible[/dim]",
            )
            continue

        pct = usage.percent
        table.add_row(
            part.mountpoint,
            human_bytes(usage.total),
            human_bytes(usage.used),
            human_bytes(usage.free),
            gradient_usage_bar(pct),
        )

    console.print(table)
    smart_cleanup_arch()


def show_path_usage(path: str, *, one_filesystem: bool = False) -> None:
    resolved = os.path.realpath(path)
    if not os.path.exists(resolved):
        console.print(f"[red]Not found:[/red] {path}")
        sys.exit(1)

    label = "File" if os.path.isfile(resolved) else "Directory"
    mode_note = (
        "\n[dim]One filesystem only (-x): not crossing other mount points.[/dim]"
        if one_filesystem and os.path.isdir(resolved)
        else ""
    )
    console.print(
        f"[bold]{label}[/bold] [cyan]{resolved}[/cyan]{mode_note}\n"
        f"[dim]Measuring size…[/dim]"
    )

    try:
        nbytes = path_size_bytes(resolved, one_filesystem=one_filesystem)
    except OSError as e:
        console.print(f"[red]Could not read path:[/red] {e}")
        sys.exit(1)

    console.print(f"\n[bold]This path uses[/bold]  [green]{human_bytes(nbytes)}[/green]\n")

    tw = terminal_table_width()
    st_d: int | None = None
    if one_filesystem and os.path.isdir(resolved):
        st_d = os.stat(resolved, follow_symlinks=False).st_dev
    if os.path.isdir(resolved):
        top = top_five_direct_children(resolved, st_dev=st_d)
        if top:
            largest = top[0][1]
            top_table = Table(
                title="Top 5 largest items here",
                header_style="bold magenta",
                width=tw,
                expand=True,
                caption="Bar length is relative to the largest entry in this list.",
            )
            top_table.add_column(
                "Name",
                style="cyan",
                overflow="ellipsis",
                no_wrap=True,
                max_width=max(18, tw // 4),
            )
            top_table.add_column("Size", justify="right", max_width=12)
            top_table.add_column(
                "Share of largest",
                justify="left",
                overflow="ellipsis",
                max_width=max(30, tw // 2),
            )
            for name, sz in top:
                top_table.add_row(
                    name,
                    human_bytes(sz),
                    relative_gradient_bar(sz, largest),
                )
            console.print(top_table)
            console.print()

    try:
        vol = psutil.disk_usage(resolved)
    except (OSError, PermissionError) as e:
        console.print(f"[dim]Could not read volume stats: {e}[/dim]")
        return

    vol_table = Table(
        title="Volume that contains this path",
        header_style="bold magenta",
        show_header=True,
        width=tw,
        expand=True,
    )
    vol_table.add_column("Total", justify="right", max_width=11)
    vol_table.add_column("Used", justify="right", max_width=11)
    vol_table.add_column("Free", justify="right", max_width=11)
    vol_table.add_column(
        "Usage",
        justify="left",
        overflow="ellipsis",
        max_width=max(28, tw // 3),
    )
    vol_table.add_row(
        human_bytes(vol.total),
        human_bytes(vol.used),
        human_bytes(vol.free),
        gradient_usage_bar(vol.percent),
    )
    console.print(vol_table)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="space",
        description="Show disk space for all volumes, or the size of a file/directory plus its volume.",
    )
    p.add_argument(
        "path",
        nargs="?",
        default=None,
        help="File or directory to measure (optional).",
    )
    p.add_argument(
        "-x",
        "--one-filesystem",
        action="store_true",
        help="When sizing a directory, stay on the same device (like du -x). Use for '/' to skip other mounts and finish much faster.",
    )
    return p


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    if args.path is None:
        show_all_partitions()
    else:
        show_path_usage(args.path, one_filesystem=args.one_filesystem)


if __name__ == "__main__":
    main()
