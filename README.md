# space

A small **Python CLI** that answers two everyday questions in the terminal: **how full are my disks?** and **how big is this folder or file?** Output is formatted with [Rich](https://github.com/Textualize/rich) so tables, colors, and usage bars are easy to scan.

## Intent

`space` is meant to be **obvious and quick**: one command for an overview of mounted volumes, or pass a path to see how much space that path uses and how much room is left on the volume that holds it. It uses [psutil](https://github.com/giampaolo/psutil) for disk facts and keeps sizes in **human-readable binary units** (KiB, MiB, GiB, …).

## Features

- **No arguments** — Lists volumes (skipping common pseudo filesystems like `tmpfs` and `proc`), showing **mount point**, **total**, **used**, **free**, and a **color-coded usage bar** with percentage.
- **Path argument** — Measures a **file** or **directory** (directories are walked without following symlinks), prints total size used, then shows the same **total / used / free / bar** summary for the **filesystem that contains** that path.
- **`--help`** — Short usage via `argparse`.

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
