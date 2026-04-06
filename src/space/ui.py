"""
Rich terminal rendering for disk and path reports.
"""

from __future__ import annotations

import errno
import os
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .scanner import DiskScanner, TopItem


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

    def print_access_error(self, path: str, exc: BaseException) -> None:
        """Human-readable message for permission and I/O failures."""
        if isinstance(exc, PermissionError) or (
            isinstance(exc, OSError) and exc.errno == errno.EACCES
        ):
            self.console.print(
                f"[red]Permission denied[/red] — cannot read "
                f"[cyan]{path}[/cyan]. Try a different path or elevated permissions."
            )
            return
        if isinstance(exc, OSError) and exc.errno == errno.ENOENT:
            self.console.print(f"[red]Not found[/red] — [cyan]{path}[/cyan]")
            return
        name = type(exc).__name__
        self.console.print(f"[red]{name}[/red] — {exc}")

    def print_partition_table(self) -> None:
        """Mode A — global disk overview (no Arch tips)."""
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

    def print_arch_maintenance_tips(self, message: str | None) -> None:
        """Mode A — ArchCleaner text after the partition table."""
        if not message:
            return
        self.console.print()
        self.console.print(
            Panel(
                message,
                title="[bold]Maintenance tips[/bold] (Arch)",
                border_style="dim",
            )
        )

    def print_bloat_hunter_top_items(self, items: list[TopItem]) -> None:
        """Render Top N immediate children (name, type, size, relative bar)."""
        tw = self.terminal_table_width()
        if not items:
            self.console.print(
                "[dim]No files or folders to rank here (empty or all skipped).[/dim]"
            )
            return

        largest = items[0].size
        top_table = Table(
            title="Bloat Hunter — largest items here",
            header_style="bold magenta",
            width=tw,
            expand=True,
            caption="Bars show share of the largest entry in this list.",
        )
        top_table.add_column(
            "Name",
            style="cyan",
            overflow="ellipsis",
            no_wrap=True,
            max_width=max(16, tw // 5),
        )
        top_table.add_column("Type", max_width=10)
        top_table.add_column("Size", justify="right", max_width=12)
        top_table.add_column(
            "Share of largest",
            justify="left",
            overflow="ellipsis",
            max_width=max(26, tw // 2),
        )
        for item in items:
            top_table.add_row(
                item.name,
                item.type,
                self.human_bytes(item.size),
                self.relative_gradient_bar(item.size, largest),
            )
        self.console.print(top_table)

    def print_bloat_hunter(self, path: str, *, one_filesystem: bool = False) -> int:
        """
        Mode B — scan *path* and show total size plus Top 5 via Bloat Hunter.

        Returns exit code 0 on success, 1 on failure.
        """
        try:
            resolved = self._scanner.resolve_path(path)
        except OSError as exc:
            self.print_access_error(path, exc)
            return 1

        if not os.path.lexists(resolved):
            self.console.print(f"[yellow]Not found[/yellow] — [cyan]{path}[/cyan]")
            return 1

        mode_note = (
            "\n[dim]One filesystem only (-x): not crossing other mount points.[/dim]"
            if one_filesystem and os.path.isdir(resolved)
            else ""
        )
        self.console.print(
            f"[bold]Bloat Hunter[/bold] — [cyan]{resolved}[/cyan]{mode_note}\n"
            f"[dim]Measuring…[/dim]"
        )

        st_d: int | None = None
        if one_filesystem and os.path.isdir(resolved):
            try:
                st_d = os.stat(resolved, follow_symlinks=False).st_dev
            except OSError as exc:
                self.print_access_error(resolved, exc)
                return 1

        if os.path.isdir(resolved):
            try:
                with os.scandir(resolved):
                    pass
            except OSError as exc:
                self.print_access_error(resolved, exc)
                return 1

            try:
                nbytes = self._scanner.path_size_bytes(
                    resolved, one_filesystem=one_filesystem
                )
            except (OSError, PermissionError) as exc:
                self.print_access_error(resolved, exc)
                return 1

            try:
                items = self._scanner.get_top_items(
                    resolved, limit=5, st_dev=st_d
                )
            except (OSError, PermissionError) as exc:
                self.print_access_error(resolved, exc)
                return 1
        else:
            if os.path.islink(resolved) and not os.path.exists(resolved):
                self.console.print(
                    "[yellow]Broken symlink[/yellow] — cannot measure."
                )
                return 1
            try:
                nbytes = os.path.getsize(resolved)
            except (OSError, PermissionError) as exc:
                self.print_access_error(resolved, exc)
                return 1
            base = os.path.basename(resolved)
            items = [TopItem(name=base, size=nbytes, type="file")]

        self.console.print(
            f"\n[bold]Total under path[/bold]  [green]{self.human_bytes(nbytes)}[/green]\n"
        )
        self.print_bloat_hunter_top_items(items)
        return 0
