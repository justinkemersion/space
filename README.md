# space

A small **Python CLI** that answers two everyday questions in the terminal: **how full are my disks?** and **how big is this folder or file?** Output is formatted with [Rich](https://github.com/Textualize/rich) so tables, colors, and usage bars are easy to scan.

## Intent

`space` is meant to be **obvious and quick**: one command for an overview of mounted volumes, or pass a path to see how much space that path uses and how much room is left on the volume that holds it. It uses [psutil](https://github.com/giampaolo/psutil) for disk facts and keeps sizes in **human-readable binary units** (KiB, MiB, GiB, …).

## Features

- **No arguments** — Lists volumes (skipping common pseudo filesystems like `tmpfs` and `proc`), showing **mount point**, **total**, **used**, **free**, and a **usage bar** whose colors **gradient from green toward red** as the volume fills. Tables use the **terminal width** so layout stays tidy.
- **Path argument** — Measures a **file** or **directory** (recursive sizing with **`os.scandir`**, no symlink following), prints total size, a **Top 5** table of the largest **immediate** children with **bars relative to the biggest** in that list, then the **volume** summary (same columns as above). Heavy or irrelevant trees (edit **`ignored_folders`** in `src/space/config.py`, e.g. `.git`, `node_modules`) are skipped so totals stay closer to “your project” than “dependencies + VCS”.
- **`-x` / `--one-filesystem`** — Like **`du -x`**: only count files on the **same mount** as the path you pass. For **`/`** this skips **`/home`**, **`/efi`**, and other mounts so the run finishes in reasonable time. **Pseudo paths** under **`/proc`**, **`/sys`**, and **`/run`** are never walked (they are huge and not normal disk usage).
- **Smart cleanup (Arch)** — On Arch Linux, if **pacman**’s package cache (`/var/cache/pacman/pkg`) or **yay**’s cache (`~/.cache/yay` or `$XDG_CACHE_HOME/yay`) is **≥ 2 GiB**, a short table suggests safe cleanup commands.
- **`--help`** — Short usage via `argparse`.

## Layout

- `src/space/config.py` — `ignored_folders`, `ignored_folder_patterns`, and other constants.
- `src/space/scanner.py` — **`DiskScanner`**: sizes, partitions, Arch cache checks (data only).
- `src/space/ui.py` — **`SpaceUI`**: Rich tables and bars.
- `src/space/cli.py` — `argparse` and **`main`** (console script `space`).

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
