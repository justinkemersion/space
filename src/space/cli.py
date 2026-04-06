"""
Command-line entry for the space tool.
"""

from __future__ import annotations

import argparse

from .scanner import DiskScanner
from .ui import SpaceUI


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="space",
        description=(
            "Show disk space for all volumes, or the size of a file/directory "
            "plus its volume."
        ),
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
        help=(
            "When sizing a directory, stay on the same device (like du -x). "
            "Use for '/' to skip other mounts and finish much faster."
        ),
    )
    return p


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    scanner = DiskScanner()
    ui = SpaceUI(scanner)
    if args.path is None:
        ui.print_partitions_overview()
    else:
        ui.print_path_report(args.path, one_filesystem=args.one_filesystem)
