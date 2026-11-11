# Stack

## Used

| Tool | Why |
|---|---|
| Python >= 3.10 | Code uses `from __future__ import annotations`, PEP 604 unions such as `int | None`, and frozen dataclasses. |
| Python standard library | Runtime uses `argparse`, `csv`, `json`, `logging`, `re`, `decimal`, `dataclasses`, `typing` and `collections.abc`. |
| pytest | The provided compiled test artifact is pytest-based. |

## Discarded

| Tool | Why not |
|---|---|
| Runtime third-party dependencies | None are declared or imported. |
