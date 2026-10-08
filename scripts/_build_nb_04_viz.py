"""Build notebooks/04-viz.ipynb for the oscars-award-wins project.

04-viz is a CONSUMER: it opens the DB **read-only** and renders the Oscars-wins
heatmaps from the chart-ready tables that `03-prepare` built. It must NOT create
any chart_* table or shape aggregates off `oscars_clean` — that is 03's job. If a
cut is missing, the fix is to amend 03 and re-run it, not to build it here.

This project ships the kit's first GRID template (`heatmap`/`matrix`, added to
`shared/chart_templates.py` in FEAT-001). Charts render INLINE via the shared
Pillow factory (`render_chart`) — matplotlib is unusable on the Python 3.14 venv.
No `filename` is passed, so charts display inline only (nothing is written to the
reserved `outputs/social/` dir — that is for `06-viz-social`).

Regenerate with:  .venv/bin/python scripts/_build_nb_04_viz.py
Then execute with: .venv/bin/python -m jupyter nbconvert --to notebook \
    --execute --inplace --ExecutePreprocessor.timeout=1200 notebooks/04-viz.ipynb
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
# 04 — Visualization: Oscar wins as a heatmap (grid exploration)

This notebook explores Academy Award **wins** as **heatmaps** — the kit's first
grid/matrix template — to decide which framing is worth building as social charts
later. It **CONSUMES** the three chart-ready tables `03-prepare` built and renders
them **read-only**; it does **not** build any chart table (that is 03's job). Run
`03-prepare.ipynb` first.

Each heatmap is a labelled grid: a **row category** down the left, a **column
category** across the top, each cell **color-scaled** by its win count and labelled
with the number. The load-bearing feature: a `(row, column)` pair that is **absent**
from the data (a category that didn't exist that period) renders as an **empty
cell**, not a zero — so you can literally see categories appear and retire.

**Four cuts explored:**
1. **Class × decade** (sequential teal) — the clean headline grid: the 6
   competitive classes over the decades.
2. **CanonicalCategory × decade** — the top-15 specific awards; shows categories
   appearing and retiring (the sparse-cell "seasons" story).
3. **Class × year** — the same as (1) but un-binned, so the owner can judge the
   **decade-vs-year** framing trade-off (the year grid is far wider and sparser).
4. **Class × decade, warm palette** — the same headline on `heatmap_warm`, to
   choose the palette.

These are **exploratory**. No `06-viz-social` work happens here — the framing is
settled first, then social is built once the owner confirms the lineup.
"""))

# ── Cell 1 — setup (read-only) ───────────────────────────────────────────────
cells.append(nbformat.v4.new_code_cell("""\
import sys, os
from pathlib import Path
import warnings
warnings.filterwarnings("ignore")

PROJECT = Path.cwd()
while not (PROJECT / "config.yaml").exists() and PROJECT != PROJECT.parent:
    PROJECT = PROJECT.parent
os.chdir(PROJECT)
sys.path.insert(0, str(PROJECT / "src"))

SHARED = PROJECT.parent.parent / "shared"
if str(SHARED) not in sys.path:
    sys.path.insert(0, str(SHARED))

import duckdb
import pandas as pd
from chart_factory import render_chart

DB_PATH = "data/project.duckdb"

# 03-prepare is the writer; this notebook only reads. Open READ-ONLY.
con = duckdb.connect(DB_PATH, read_only=True)

# Guard: the chart-ready tables must already exist (built by 03-prepare).
_tables = [t[0] for t in con.execute("SHOW TABLES").fetchall()]
_required = [
    "chart_wins_class_by_decade",
    "chart_wins_canoncat_by_decade",
    "chart_wins_class_by_year",
]
_missing = [t for t in _required if t not in _tables]
assert not _missing, (
    f"Prepared chart tables missing: {_missing}. "
    "Run notebooks/03-prepare.ipynb first (it OWNS the chart_* tables)."
)
print("Connected (read-only). Prepared chart tables present:", _required)

SOURCE = "AMPAS Awards Database via DLu/oscar_data, retrieved 2026-10-08"
# Pretty decade labels for the column axis: 1920 -> "1920s".
decade_label = lambda d: f"{int(d)}s"
"""))

# ── Cell 2 — cut 1: class x decade (headline) ────────────────────────────────
cells.append(nbformat.v4.new_markdown_cell("""\
## Cut 1 — Class × decade (the headline grid, sequential teal)

The 6 competitive classes down the left, decades across the top, each cell the
number of wins that class took that decade. Hotter (darker) cells = more wins. This
is the clean, legible headline: small grid, no honorary distortion. Empty cells
mean a class had no wins that decade (rare for these broad classes — mostly the
earliest decade before a class existed).
"""))

cells.append(nbformat.v4.new_code_cell("""\
class_by_decade = con.execute(
    "SELECT * FROM chart_wins_class_by_decade ORDER BY class, decade"
).df()

render_chart({
    "type": "heatmap",
    "table": class_by_decade,          # inline DataFrame (factory accepts a df under "table")
    "row_col": "class",
    "col_col": "decade",
    "value_col": "wins",
    "palette": "heatmap_teal",
    "col_label_fmt": decade_label,
    "title": "Oscar wins by category over the decades",
    "subtitle": "Competitive categories only \\u00b7 empty cell = category absent that decade",
    "source": SOURCE,
    "preset": "twitter_landscape",
    # no filename -> display inline only (outputs/social is reserved for 06)
})
"""))

# ── Cell 3 — cut 2: canonical category x decade ──────────────────────────────
cells.append(nbformat.v4.new_markdown_cell("""\
## Cut 2 — CanonicalCategory × decade (categories appearing & retiring)

The top-15 specific awards by total wins, over the decades. This is the "seasons"
story: a category that was introduced partway through Oscars history has **empty
cells in the early decades**, and a retired category has **empty cells at the
end** — because those `(category, decade)` pairs are genuinely absent (not zero).
Watch for rows that only fill in the middle of the grid.
"""))

cells.append(nbformat.v4.new_code_cell("""\
canoncat_by_decade = con.execute(
    "SELECT * FROM chart_wins_canoncat_by_decade ORDER BY canonical_category, decade"
).df()

render_chart({
    "type": "heatmap",
    "table": canoncat_by_decade,
    "row_col": "canonical_category",
    "col_col": "decade",
    "value_col": "wins",
    "palette": "heatmap_teal",
    "col_label_fmt": decade_label,
    "title": "Oscar wins by specific award over the decades",
    "subtitle": "Top 15 competitive categories by total wins \\u00b7 empty cell = award not given that decade",
    "source": SOURCE,
    "preset": "twitter_landscape",
})
"""))

# ── Cell 4 — cut 3: class x year (decade-vs-year framing) ────────────────────
cells.append(nbformat.v4.new_markdown_cell("""\
## Cut 3 — Class × year (the decade-vs-year framing comparison)

The same six classes, but columns are **individual years** instead of decades.
This is here to make the framing trade-off explicit for the owner: the year grid
is ~98 columns wide and far sparser (most class-years have just 1 win), so the
labels crowd and the "seasons" are harder to read. It is the direct argument for
**binning into decades** (Cut 1). Shown for comparison, not as a shippable chart.
"""))

cells.append(nbformat.v4.new_code_cell("""\
class_by_year = con.execute(
    "SELECT * FROM chart_wins_class_by_year ORDER BY class, year_int"
).df()

render_chart({
    "type": "heatmap",
    "table": class_by_year,
    "row_col": "class",
    "col_col": "year_int",
    "value_col": "wins",
    "palette": "heatmap_teal",
    "title": "Oscar wins by category, year by year",
    "subtitle": "Competitive categories only \\u00b7 un-binned years \\u2014 wider and sparser than the decade view",
    "source": SOURCE,
    "preset": "twitter_landscape",
})
"""))

# ── Cell 5 — cut 4: warm palette variant ─────────────────────────────────────
cells.append(nbformat.v4.new_markdown_cell("""\
## Cut 4 — Class × decade on the warm palette

The headline grid again, rendered with `heatmap_warm` instead of the default
`heatmap_teal`, so the owner can pick the palette. Same data, same shape — only the
color ramp changes. (Diverging is **not** used anywhere: win counts have no
meaningful midpoint, so a sequential ramp is the honest choice.)
"""))

cells.append(nbformat.v4.new_code_cell("""\
render_chart({
    "type": "heatmap",
    "table": class_by_decade,
    "row_col": "class",
    "col_col": "decade",
    "value_col": "wins",
    "palette": "heatmap_warm",
    "col_label_fmt": decade_label,
    "title": "Oscar wins by category over the decades",
    "subtitle": "Competitive categories only \\u00b7 warm palette variant",
    "source": SOURCE,
    "preset": "twitter_landscape",
})
"""))

# ── Cell 6 — framing notes ───────────────────────────────────────────────────
cells.append(nbformat.v4.new_markdown_cell("""\
## Story framing — candidate angles for social charts

From this exploration:

1. **Class × decade (teal)** — the clearest, most legible headline. Six broad
   rows, ~11 decade columns, instantly readable "seasons" of which class ran hot
   each decade. Strong lead candidate.
2. **CanonicalCategory × decade** — the richer "categories appear and retire"
   story; the empty cells carry real meaning (an award that didn't exist yet).
   Best supporting chart. Top-15 keeps it legible.
3. **Class × year** — demonstrably too wide/sparse to post; it's the evidence FOR
   binning into decades, not a chart to ship.
4. **Warm vs teal** — purely a palette choice; the data reads the same.

**Framing decisions awaiting owner sign-off** (no `06-viz-social` until confirmed):

- **Decade or year columns?** Recommendation: **decade** (legible; year is too wide).
- **Class (6 broad rows) or CanonicalCategory (top-N specific awards) as the row
  axis?** Both work; likely **both charts** — Class as the headline, CanonicalCategory
  as the "seasons" supporting chart.
- **Include or keep excluding SciTech / Special (honorary)?** Recommendation:
  **keep excluding** — they are non-competitive (every entry a recipient) and would
  create artificially hot cells. (Could show an "including honorary" variant clearly
  labelled, if wanted.)
- **Sequential teal vs warm palette?** Owner's pick; **sequential either way** —
  there is no real midpoint, so diverging is NOT used.
- **Descriptive title wording** — e.g. "Oscar wins by category over the decades"
  (describe, don't conclude).

If a different cut is wanted, it is added in `03-prepare` and 03 is re-run — not
built here.

⏸ **No `06-viz-social` work until the owner reviews these and confirms the lineup.**
"""))

# ── Cell 7 — cleanup ─────────────────────────────────────────────────────────
cells.append(nbformat.v4.new_markdown_cell("""\
---
## Cleanup
Close the read-only DuckDB connection so the lock is released. Runs on "Run All".
"""))
cells.append(nbformat.v4.new_code_cell("""\
con.close()
print("Connection closed.")
"""))

nb.cells = cells

out = Path("notebooks/04-viz.ipynb")
nbformat.write(nb, out)
print(f"Written: {out}")
