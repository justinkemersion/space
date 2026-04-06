"""
Command-line entry for the space tool.
"""

from __future__ import annotations

import argparse
import sys

from .cleaners import ArchCleaner
from .scanner import DiskScanner
from .ui import SpaceUI


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="space",
        description=(
            "Mode A (no path): disk overview for all volumes, then Arch maintenance tips. "
            "Mode B (path): Bloat Hunter — total size and Top 5 largest immediate children."
        ),
    )
    p.add_argument(
        "path",
        nargs="?",
        default=None,
        help="Directory or file to analyze with Bloat Hunter (optional).",
    )
    p.add_argument(
        "-x",
        "--one-filesystem",
        action="store_true",
        help=(
            "Bloat Hunter only: stay on the same device as the path (like du -x)."
        ),
    )
    return p


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    scanner = DiskScanner()
    ui = SpaceUI(scanner)
    cleaner = ArchCleaner(scanner)

    if args.path is None:
        # Mode A — global partitions, then ArchCleaner tips at the bottom.
        ui.print_partition_table()
        ui.print_arch_maintenance_tips(cleaner.recommendation())
        return

    # Mode B — Bloat Hunter on the given path (no partition table).
    code = ui.print_bloat_hunter(
        args.path,
        one_filesystem=args.one_filesystem,
    )
    if code != 0:
        sys.exit(code)


if __name__ == "__main__":
    main()
