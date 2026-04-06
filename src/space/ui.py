"""
Rich terminal rendering for disk and path reports.
"""

from __future__ import annotations

import os
import sys
from rich.console import Console
from rich.table import Table
from rich.text import Text

from . import config
from .scanner import CleanupHint, DiskScanner


class SpaceUI:
    """Format and print scanner results with Rich."""

    def __init__(
        self,
        scanner: DiskScanner,
        *,
        console: Console | None = None,
    ) -> None:
        self._scanner = scanner
        self.console = console or Console()

    def terminal_table_width(self) -> int:
        w = self.console.width
        if w is None or w < 50:
            return 80
        return w

    def bar_cell_count(self) -> int:
        tw = self.terminal_table_width()
        return max(10, min(22, tw // 5))

    @staticmethod
    def human_bytes(n: float) -> str:
        if n < 0:
            n = 0.0
        for unit in ("B", "KiB", "MiB", "GiB", "TiB", "PiB"):
            if abs(n) < 1024.0:
                if unit == "B":
                    return f"{int(n):,} B"
                return f"{n:.2f} {unit}"
            n /= 1024.0
        return f"{n:.2f} EiB"

    @staticmethod
    def heat_rgb(percent: float) -> tuple[int, int, int]:
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

    def gradient_usage_bar(self, percent: float, width: int | None = None) -> Text:
        if width is None:
            width = self.bar_cell_count()
        pct = max(0.0, min(100.0, float(percent)))
        filled = max(0, min(width, int(round(width * pct / 100.0))))
        out = Text()
        for i in range(width):
            ch = "█" if i < filled else "░"
            if i < filled:
                cell_pct = ((i + 1) / width) * 100.0
                blend = min(100.0, (cell_pct + pct) / 2.0)
                r, g, b = self.heat_rgb(blend)
                out.append(ch, style=f"#{r:02x}{g:02x}{b:02x}")
            else:
                out.append(ch, style="dim")
        out.append(f" {pct:.1f}%", style="default")
        return out

    def relative_gradient_bar(
        self, size: int, largest: int, width: int | None = None
    ) -> Text:
        if width is None:
            width = self.bar_cell_count()
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
                r, g, b = self.heat_rgb(cell_pct)
                out.append(ch, style=f"#{r:02x}{g:02x}{b:02x}")
            else:
                out.append(ch, style="dim")
        out.append(f" {pct:.1f}%", style="default")
        return out

    def print_partitions_overview(self) -> None:
        tw = self.terminal_table_width()
        table = Table(
            title="Disk space (all volumes)",
            caption=(
                "Sizes use binary units (KiB, MiB, GiB, …). "
                "Bars run green→red as usage grows."
            ),
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

        for pinfo, usage in self._scanner.iter_partition_usage():
            if usage is None:
                table.add_row(
                    pinfo.mountpoint,
                    "—",
                    "—",
                    "—",
                    "[dim]not accessible[/dim]",
                )
                continue
            table.add_row(
                usage.mountpoint,
                self.human_bytes(usage.total),
                self.human_bytes(usage.used),
                self.human_bytes(usage.free),
                self.gradient_usage_bar(usage.percent),
            )

        self.console.print(table)
        hints = self._scanner.arch_cleanup_hints()
        if hints:
            self.print_arch_cleanup(hints, config.CACHE_WARN_BYTES)

    def print_arch_cleanup(
        self, hints: list[CleanupHint], warn_bytes: int
    ) -> None:
        tw = self.terminal_table_width()
        t = Table(
            title="Smart cleanup (Arch)",
            caption=(
                f"Caches at or above {self.human_bytes(warn_bytes)} trigger a hint."
            ),
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
        t.add_column(
            "Suggestion",
            overflow="ellipsis",
            max_width=max(24, tw // 2),
        )
        for h in hints:
            t.add_row(h.label, self.human_bytes(h.size_bytes), h.suggestion)
        self.console.print(t)

    def print_path_report(self, path: str, *, one_filesystem: bool = False) -> None:
        resolved = self._scanner.resolve_path(path)
        if not os.path.exists(resolved):
            self.console.print(f"[red]Not found:[/red] {path}")
            sys.exit(1)

        label = "File" if os.path.isfile(resolved) else "Directory"
        mode_note = (
            "\n[dim]One filesystem only (-x): not crossing other mount points.[/dim]"
            if one_filesystem and os.path.isdir(resolved)
            else ""
        )
        self.console.print(
            f"[bold]{label}[/bold] [cyan]{resolved}[/cyan]{mode_note}\n"
            f"[dim]Measuring size…[/dim]"
        )

        try:
            nbytes = self._scanner.path_size_bytes(
                resolved, one_filesystem=one_filesystem
            )
        except OSError as e:
            self.console.print(f"[red]Could not read path:[/red] {e}")
            sys.exit(1)

        self.console.print(
            f"\n[bold]This path uses[/bold]  [green]{self.human_bytes(nbytes)}[/green]\n"
        )

        tw = self.terminal_table_width()
        st_d: int | None = None
        if one_filesystem and os.path.isdir(resolved):
            st_d = os.stat(resolved, follow_symlinks=False).st_dev

        if os.path.isdir(resolved):
            top = self._scanner.top_five_direct_children(resolved, st_dev=st_d)
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
                        self.human_bytes(sz),
                        self.relative_gradient_bar(sz, largest),
                    )
                self.console.print(top_table)
                self.console.print()

        vol = self._scanner.volume_usage(resolved)
        if vol is None:
            self.console.print("[dim]Could not read volume stats[/dim]")
            return

        total, used, free, pct = vol
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
            self.human_bytes(total),
            self.human_bytes(used),
            self.human_bytes(free),
            self.gradient_usage_bar(pct),
        )
        self.console.print(vol_table)
