"""Build 01-ingest.ipynb for the oscars-award-wins project.

Regenerate with:  .venv/bin/python scripts/_build_nb_01_ingest.py
Then execute with: .venv/bin/python -m jupyter nbconvert --to notebook \
    --execute --inplace --ExecutePreprocessor.timeout=1200 notebooks/01-ingest.ipynb
"""
from pathlib import Path

import nbformat

nb = nbformat.v4.new_notebook()
nb.metadata = {
    "kernelspec": {
        "display_name": "Python 3",
        "language": "python",
        "name": "python3",
    },
    "language_info": {"name": "python", "version": "3.14"},
}

cells = []

# ── Cell 0 — title ──────────────────────────────────────────────────────────
cells.append(nbformat.v4.new_markdown_cell("""\
# 01 — Ingest: Academy Awards nominations + winners

Fetches the **DLu/oscar_data `oscars.csv`** dataset — every Academy Award
nomination and winner from the 1st ceremony (1927/28) through the 98th (2025) —
and lands it in `data/raw/` (untouched) and `data/project.duckdb`.

**No transformation happens here.** Rows load into DuckDB exactly as the file
serves them (one row per nomination, all 14 columns). All cleaning is in
`02-clean.ipynb`.
"""))

# ── Cell 1 — setup ──────────────────────────────────────────────────────────
cells.append(nbformat.v4.new_code_cell("""\
import sys, os
from pathlib import Path

# Navigate to project root regardless of how the kernel was launched
PROJECT = Path.cwd()
while not (PROJECT / "config.yaml").exists() and PROJECT != PROJECT.parent:
    PROJECT = PROJECT.parent
os.chdir(PROJECT)
sys.path.insert(0, str(PROJECT))

from src.ingest import load_config, ingest_oscars
from src.clean_quality import get_connection, load_to_duckdb, register_source
import pandas as pd

cfg = load_config("config.yaml")
con = get_connection(cfg)
print(f"Project: {cfg['project_name']}")
"""))

# ── Cell 2 — source section ─────────────────────────────────────────────────
cells.append(nbformat.v4.new_markdown_cell("""\
## Source: DLu/oscar_data `oscars.csv` (fun-tier, authoritative-backed)

Source: **[DLu/oscar_data](https://github.com/DLu/oscar_data)** (David V. Lu) —
a curated Academy Awards nominations + winners dataset. The underlying facts come
from the official **[AMPAS Awards Database](https://awardsdatabase.oscars.org/)**
plus **IMDb** identifiers, so this fun-tier pop-culture project is backed by an
authoritative primary source. License: **BSD 2-Clause** for the compilation.

**TAB-separated, despite the `.csv` extension.** `ingest_oscars()` reads the file
with `sep="\\t"`. Reading it as comma-separated would collapse every row into a
single column.

**Caching.** The raw file is downloaded once to `data/raw/oscars.csv` and reused on
every later run (no network request), so re-execution is free. A polite ≥ 1.0s
delay precedes any actual download.

**Columns (14):** `Ceremony` (ordinal 1..98), `Year` (string, e.g. `1927/28` …
`2025`), `Class` (8 broad groupings), `CanonicalCategory` (normalized category name
across the years), `Category` (exact Oscars.org wording), `Film`, `FilmId`, `Name`,
`Nominees`, `NomineeIds`, `Winner` (bool: `True` = win, blank = non-winning
nomination), `Detail`, `Note`, `Citation`.
"""))

# ── Cell 3 — run the ingest ─────────────────────────────────────────────────
cells.append(nbformat.v4.new_code_cell("""\
# Download (or reuse cached) the TSV and read it UNtransformed (raw stage).
df = ingest_oscars(cfg, rate_limit_seconds=1.0)
print()
print("df.shape:", df.shape)
print("columns:", list(df.columns))
df.head()
"""))

# ── Cell 4 — load into DuckDB ────────────────────────────────────────────────
cells.append(nbformat.v4.new_markdown_cell("""\
## Load into DuckDB as `oscars_raw`

One row per nomination, values untransformed. The blank `Winner` cells read as
NULL (non-winner); `True` marks a win.
"""))

cells.append(nbformat.v4.new_code_cell("""\
load_to_duckdb(df, "oscars_raw", con)
n = con.execute("SELECT COUNT(*) FROM oscars_raw").fetchone()[0]
print(f"oscars_raw: {n:,} rows loaded into DuckDB")

register_source(
    con,
    "oscars_raw",
    "DLu/oscar_data (oscars.csv)",
    url="https://raw.githubusercontent.com/DLu/oscar_data/main/oscars.csv",
    license="BSD 2-Clause (compilation); facts from AMPAS Awards Database + IMDb",
    notes=(
        "Academy Awards nominations + winners, 1st (1927/28) .. 98th (2025) "
        "ceremonies. One row per nomination; Winner=True marks a win. TAB-separated."
    ),
    retrieved="2026-10-08",
    methodology=(
        "AMPAS official nomination/winner results parsed from the Awards Database "
        "and enriched with IMDb IDs. A win = one row with Winner=True; a tie yields "
        "two winner rows; CanonicalCategory normalizes category-name changes over "
        "the years into one continuous series."
    ),
    series_breaks=(
        "Categories were added/retired/renamed across 98 years, so an empty "
        "(category, decade) cell means the category did not exist that decade, NOT "
        "zero wins. SciTech (all 919 rows are winners) and Special (honorary) are "
        "non-competitive and are excluded from the competitive heatmap."
    ),
)
print("Source registered in _sources.")
"""))

# ── Cell 5 — plausibility check ──────────────────────────────────────────────
cells.append(nbformat.v4.new_markdown_cell("""\
## Plausibility check

Confirm the known shape of the data: **12,137 rows**, **98 distinct ceremonies**,
and **3,515 wins** (`Winner == True`). Also show the `Class` distribution — note
SciTech (919) and Special, the two non-competitive classes excluded later.
"""))

cells.append(nbformat.v4.new_code_cell("""\
summary = con.execute(\"\"\"
    SELECT
        COUNT(*)                                   AS n_rows,
        COUNT(DISTINCT Ceremony)                   AS n_ceremonies,
        SUM(CASE WHEN Winner THEN 1 ELSE 0 END)    AS n_wins,
        MIN(Year)                                  AS first_year,
        MAX(Year)                                  AS last_year
    FROM oscars_raw
\"\"\").df()
print(summary.to_string(index=False))

n_rows = int(summary["n_rows"].iloc[0])
n_wins = int(summary["n_wins"].iloc[0])
assert n_rows == 12137, f"Expected 12137 rows, got {n_rows}"
assert n_wins == 3515, f"Expected 3515 wins, got {n_wins}"
print("\\nPlausibility OK — 12,137 rows, 3,515 wins.")

print("\\nClass distribution (SciTech + Special are non-competitive):")
print(con.execute(
    "SELECT Class, COUNT(*) AS n_nominations, "
    "SUM(CASE WHEN Winner THEN 1 ELSE 0 END) AS n_wins "
    "FROM oscars_raw GROUP BY Class ORDER BY n_nominations DESC"
).df().to_string(index=False))
"""))

# ── Cell 6 — summary / next ─────────────────────────────────────────────────
cells.append(nbformat.v4.new_markdown_cell("""\
---
**Next:** `02-clean.ipynb` — keep the winner rows, parse `Year` to a numeric
ceremony year + decade, flag competitive vs honorary classes, and save interim.
"""))

# ── Cell 7 — cleanup ────────────────────────────────────────────────────────
cells.append(nbformat.v4.new_markdown_cell("""\
---
## Cleanup
Close the DuckDB connection so the single-writer lock is released for other tools
(DBCode, other notebooks). Runs on "Run All".
"""))
cells.append(nbformat.v4.new_code_cell("con.close()\nprint('connection closed')"))

nb.cells = cells

out = Path("notebooks/01-ingest.ipynb")
nbformat.write(nb, out)
print(f"Written: {out}")
