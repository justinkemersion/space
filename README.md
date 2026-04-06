# space

A small **Python CLI** that answers two everyday questions in the terminal: **how full are my disks?** and **how big is this folder or file?** Output is formatted with [Rich](https://github.com/Textualize/rich) so tables, colors, and usage bars are easy to scan.

## Intent

`space` is meant to be **obvious and quick**: **Mode A** shows all volumes; **Mode B** (“Bloat Hunter”) digs into one path. It uses [psutil](https://github.com/giampaolo/psutil) for disk facts and keeps sizes in **human-readable binary units** (KiB, MiB, GiB, …).

## Features

- **Mode A (no arguments)** — Partition overview: **mount**, **total**, **used**, **free**, and a **green→red usage bar** per volume. Then **`ArchCleaner`** may print **maintenance tips** in a panel if pacman/yay caches exceed **2 GiB**.
- **Mode B (`space <path>`)** — **Bloat Hunter**: total size under the path, then **`print_bloat_hunter_top_items`** — a **Top 5** table of the largest **immediate** children (**name**, **type** `file`/`directory`, **size**, **share bar**). Does **not** print the global partition table. Ignored trees come from **`ignored_folders`** in `src/space/config.py` (e.g. `.git`, `node_modules`).
- **`-x` / `--one-filesystem`** — Bloat Hunter only, like **`du -x`**: stay on the **same device** as the path. Pseudo paths **`/proc`**, **`/sys`**, **`/run`** are never walked.
- **Errors** — **Permission denied** and common I/O issues produce a short, styled message (exit code **1**); no traceback.
- **`--help`** — Short usage via `argparse`.

## Layout

- `src/space/config.py` — `ignored_folders`, `ignored_folder_patterns`, and other constants.
- `src/space/scanner.py` — **`DiskScanner`**: sizes, partitions, **`get_top_items`**, etc.
- `src/space/cleaners.py` — **`ArchCleaner`**: Arch cache checks and recommendation text.
- `src/space/ui.py` — **`SpaceUI`**: Rich tables, **`print_partition_table`**, **`print_bloat_hunter`**, **`print_bloat_hunter_top_items`**.
- `src/space/cli.py` — **`main`**: Mode A vs Mode B (console script `space`).

## Requirements

- Python **3.10+**
- Dependencies: **psutil**, **rich** (see `pyproject.toml`).

## Install

From the project directory:

```bash
python -m venv .venv
source .venv/bin/activate   # or: .venv\Scripts\activate on Windows
pip install -e .
space
space /path/to/something
```

You can also install with [pipx](https://pipx.pypa.io/) if you prefer an isolated app environment.

## Remote

Upstream repository: `git@github.com:justinkemersion/space.git`
