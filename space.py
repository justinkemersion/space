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


def usage_bar(percent: float, width: int = 18) -> str:
    """A small ASCII bar + percentage, color-coded by how full the volume is."""
    pct = max(0.0, min(100.0, float(percent)))
    filled = int(round(width * pct / 100.0))
    color = "green" if pct < 80 else "yellow" if pct < 90 else "red"
    bar = "█" * filled + "░" * (width - filled)
    return f"[{color}]{bar}[/{color}] {pct:.1f}%"


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
    table = Table(
        title="Disk space (all volumes)",
        caption="Sizes use binary units (KiB, MiB, GiB, …).",
        header_style="bold magenta",
        show_lines=False,
    )
    table.add_column("Mount", style="cyan", no_wrap=True)
    table.add_column("Total", justify="right")
    table.add_column("Used", justify="right")
    table.add_column("Free", justify="right")
    table.add_column("Usage", justify="left", min_width=28)

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
            usage_bar(pct),
        )

    console.print(table)


def path_size_bytes(path: str) -> int:
    """Total bytes used by a file or everything under a directory (no symlink following)."""
    if os.path.isfile(path) or (os.path.islink(path) and not os.path.isdir(path)):
        return os.path.getsize(path)

    total = 0
    for root, dirs, filenames in os.walk(path, followlinks=False):
        # Avoid descending into symlinked directories.
        dirs[:] = [d for d in dirs if not os.path.islink(os.path.join(root, d))]
        for name in filenames:
            fp = os.path.join(root, name)
            try:
                if os.path.islink(fp):
                    continue
                total += os.path.getsize(fp)
            except (OSError, PermissionError):
                continue
    return total


def show_path_usage(path: str) -> None:
    resolved = os.path.realpath(path)
    if not os.path.exists(resolved):
        console.print(f"[red]Not found:[/red] {path}")
        sys.exit(1)

    label = "File" if os.path.isfile(resolved) else "Directory"
    console.print(
        f"[bold]{label}[/bold] [cyan]{resolved}[/cyan]\n"
        f"[dim]Measuring size…[/dim]"
    )

    try:
        nbytes = path_size_bytes(resolved)
    except OSError as e:
        console.print(f"[red]Could not read path:[/red] {e}")
        sys.exit(1)

    console.print(f"\n[bold]This path uses[/bold]  [green]{human_bytes(nbytes)}[/green]\n")

    # Same style of numbers as the main table: volume that holds this path.
    try:
        vol = psutil.disk_usage(resolved)
    except (OSError, PermissionError) as e:
        console.print(f"[dim]Could not read volume stats: {e}[/dim]")
        return

    vol_table = Table(
        title="Volume that contains this path",
        header_style="bold magenta",
        show_header=True,
    )
    vol_table.add_column("Total", justify="right")
    vol_table.add_column("Used", justify="right")
    vol_table.add_column("Free", justify="right")
    vol_table.add_column("Usage", justify="left", min_width=28)
    vol_table.add_row(
        human_bytes(vol.total),
        human_bytes(vol.used),
        human_bytes(vol.free),
        usage_bar(vol.percent),
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
    return p


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    if args.path is None:
        show_all_partitions()
    else:
        show_path_usage(args.path)


if __name__ == "__main__":
    main()
