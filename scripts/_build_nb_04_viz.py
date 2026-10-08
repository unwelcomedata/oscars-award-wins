"""Build notebooks/04-viz.ipynb for the oscars-award-wins project (GENRE re-flow).

04-viz is a CONSUMER: it opens the DB **read-only** and renders the genre
exploration from the chart-ready tables that `03-prepare` built. It must NOT
create any chart_* table or shape aggregates off the interim data — that is 03's
job. If a cut is missing, amend 03 and re-run it, not here.

The LEAD chart uses the kit's new `categorical_grid` template (built in the
shared kit for this re-flow): a per-YEAR grid where each major-award-winning
film is colored by its PRIMARY GENRE, with a genre LEGEND off to the side (the
owner's "cut 3 shape, but with a legend instead of labels"). Two supporting
charts use the existing sequential `heatmap`. Charts render INLINE via the shared
Pillow factory (`render_chart`) — matplotlib is unusable on the Python 3.14 venv.
No `filename` is passed, so charts display inline only (nothing written to the
reserved `outputs/social/` dir — that is for `06-viz-social`).

Regenerate with:  .venv/bin/python scripts/_build_nb_04_viz.py
Then execute with: .venv/bin/python -m jupyter nbconvert --to notebook \
    --execute --inplace --ExecutePreprocessor.kernel_name=oscars-venv \
    --ExecutePreprocessor.timeout=1800 notebooks/04-viz.ipynb
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
# 04 — Visualization: Oscar wins by film GENRE (exploration)

The win-count grids barely changed decade to decade — a flat story. This re-flow
explores the data through **film genre** (TMDB primary genre, joined onto the
major-award winners): *which genres win the major awards, and how that shifts over
the decades.* It **CONSUMES** the three chart-ready tables `03-prepare` built and
renders them **read-only**; it builds **no** chart table (that is 03's job). Run
`03-prepare.ipynb` first.

**Four cuts explored:**
1. **LEAD — per-year major winners, colored by genre** (`categorical_grid`): the
   8 major categories down the left, every ceremony year across the top, each cell
   **colored by the winning film's primary genre**, with a **genre legend in a
   single row above the chart**. This is the owner's *"cut 3 shape (category ×
   year), but a legend instead of in-cell labels"* — color carries the data, no
   numbers. Absent cells (no major win that category+year) render empty.
2. **Genre × decade — count of major wins** (`heatmap`, sequential teal): which
   genres win the majors, by decade. Magnitude view.
3. **Best Picture genre mix by decade** (`heatmap`): how the Best Picture genre
   mix shifts over the decades.
4. **Cut 4 — the original pre-genre count grid** (`heatmap`, `show_values=False`):
   the 6 competitive classes × every year, cell = competitive win count, rendered
   with a **color-scale legend instead of in-cell numbers** (the ~98-column grid is
   too wide for readable digits). Re-added at the owner's request.

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

# Guard: the chart-ready genre tables must already exist (built by 03-prepare).
_tables = [t[0] for t in con.execute("SHOW TABLES").fetchall()]
_required = [
    "chart_major_genre_by_year",
    "chart_genre_wins_by_decade",
    "chart_bestpic_genre_by_decade",
    "chart_wins_class_by_year",          # cut 4 (the original pre-genre count grid)
]
_missing = [t for t in _required if t not in _tables]
assert not _missing, (
    f"Prepared chart tables missing: {_missing}. "
    "Run notebooks/03-prepare.ipynb first (it OWNS the chart_* tables)."
)
print("Connected (read-only). Prepared genre tables present:", _required)

# Source + TMDB attribution line carried in every chart subtitle/source.
SOURCE = "AMPAS Awards Database via DLu/oscar_data; genre via TMDB (not endorsed/certified by TMDB), retrieved 2026-10-08"
decade_label = lambda d: f"{int(d)}s"
"""))

# ── Cell 2 — LEAD: categorical grid ──────────────────────────────────────────
cells.append(nbformat.v4.new_markdown_cell("""\
## Cut 1 (LEAD) — Each major winner colored by genre, year by year

The owner's ask: *"like cut 3 (category × year), but with a legend instead of
labels."* Rows = the 8 major categories, columns = every ceremony year, and each
cell is **colored by the primary genre** of that category's winning film that
year. The **legend** sits as a **single horizontal row above the chart**
(`legend_loc="top"`), carrying genre→color; there are **no in-cell numbers** — the
color is the data. Genres are binned to the top-8 + `"Other"` (in
`03-prepare`) so the legend stays legible. Empty cells = no major win for that
category that year (sparse = absent, not a color).
"""))

cells.append(nbformat.v4.new_code_cell("""\
major_genre_by_year = con.execute(
    "SELECT * FROM chart_major_genre_by_year ORDER BY canonical_category, year_int"
).df()

render_chart({
    "type": "categorical_grid",
    "table": major_genre_by_year,       # inline DataFrame (factory accepts a df under "table")
    "row_col": "canonical_category",
    "col_col": "year_int",
    "category_col": "primary_genre_binned",
    "legend_title": "Primary genre",
    "legend_loc": "top",                # single horizontal legend row above the grid
    "col_label_fmt": lambda y: f"'{int(y) % 100:02d}",   # compact year label
    "title": "Primary genre of each major Oscar winner, year by year",
    "subtitle": "Best Picture, Directing, the four acting awards & the two screenplay awards \\u00b7 color = TMDB primary genre",
    "source": SOURCE,
    "preset": "twitter_landscape",
    # no filename -> display inline only (outputs/social is reserved for 06)
})
"""))

# ── Cell 3 — genre x decade count heatmap ────────────────────────────────────
cells.append(nbformat.v4.new_markdown_cell("""\
## Cut 2 — Major wins by genre over the decades (count)

The magnitude view: binned primary genre down the left, decades across the top,
each cell = the number of **major** awards that genre won that decade (sequential
teal — hotter = more wins). This is the "which genres win the majors, and when"
story. Empty cells = that genre won no major that decade.
"""))

cells.append(nbformat.v4.new_code_cell("""\
genre_by_decade = con.execute(
    "SELECT * FROM chart_genre_wins_by_decade ORDER BY primary_genre_binned, decade"
).df()

render_chart({
    "type": "heatmap",
    "table": genre_by_decade,
    "row_col": "primary_genre_binned",
    "col_col": "decade",
    "value_col": "wins",
    "palette": "heatmap_teal",
    "col_label_fmt": decade_label,
    "title": "Major Oscar wins by film genre over the decades",
    "subtitle": "Count of major-award wins per primary genre \\u00b7 empty cell = no major win that decade",
    "source": SOURCE,
    "preset": "twitter_landscape",
})
"""))

# ── Cell 4 — Best Picture genre mix heatmap ──────────────────────────────────
cells.append(nbformat.v4.new_markdown_cell("""\
## Cut 3 — Best Picture winners by genre over the decades

The headline category on its own: how the **Best Picture** genre mix shifts over
the decades (count heatmap). Reading one row across tells you when a genre's run
of Best Pictures happened; reading one column tells you that decade's mix.
"""))

cells.append(nbformat.v4.new_code_cell("""\
bestpic_by_decade = con.execute(
    "SELECT * FROM chart_bestpic_genre_by_decade ORDER BY primary_genre_binned, decade"
).df()

render_chart({
    "type": "heatmap",
    "table": bestpic_by_decade,
    "row_col": "primary_genre_binned",
    "col_col": "decade",
    "value_col": "wins",
    "palette": "heatmap_warm",
    "col_label_fmt": decade_label,
    "title": "Best Picture winners by film genre over the decades",
    "subtitle": "Count of Best Picture wins per primary genre \\u00b7 empty cell = no Best Picture of that genre that decade",
    "source": SOURCE,
    "preset": "twitter_landscape",
})
"""))

# ── Cell 4b — CUT 4: the original pre-genre count grid ───────────────────────
cells.append(nbformat.v4.new_markdown_cell("""\
## Cut 4 — Oscar wins by category, year by year (the original pre-genre count)

This is the **original "cut 3" from the first exploration pass — before any genre
enrichment**: a grid of the **6 competitive classes down the left × every ceremony
year across the top**, each cell = the **count of competitive Oscar wins** for that
class that year. **No genre is involved** — it is the plain award-count grid.

It was deemed **"too wide to post"** the first time, because ~98 year columns of
in-cell numbers are unreadable. The fix the owner asked for: render it with **no
in-cell numbers and a color-scale legend** (`heatmap` `show_values=False`), so
**color carries the count** instead of digits. The data comes from the prepared
`chart_wins_class_by_year` table (`03-prepare` owns it); this cell only reads it.
"""))

cells.append(nbformat.v4.new_code_cell("""\
# CUT 4 — consume the prepared pre-genre count grid read-only (03 built it).
cut4_wins_class_by_year = con.execute(
    "SELECT * FROM chart_wins_class_by_year ORDER BY class, year_int"
).df()

render_chart({
    "type": "heatmap",
    "table": cut4_wins_class_by_year,
    "row_col": "class",
    "col_col": "year_int",
    "value_col": "wins",
    "palette": "heatmap_teal",
    "show_values": False,               # no in-cell numbers -> color-scale legend (dense ~98-col grid)
    "legend_label": "wins",
    "col_label_fmt": lambda y: f"'{int(y) % 100:02d}",
    "title": "Oscar wins by category, year by year",
    "subtitle": "Count of competitive wins per category each ceremony \\u00b7 color = number of wins",
    "source": SOURCE,
    "preset": "twitter_landscape",
    # no filename -> display inline only (outputs/social is reserved for 06)
})
"""))

# ── Cell 5 — framing notes ───────────────────────────────────────────────────
cells.append(nbformat.v4.new_markdown_cell("""\
## Story framing — candidate angles for social charts

The genre lens is the interesting story the win-counts lacked:

1. **Per-year grid colored by genre (LEAD)** — the owner's requested shape:
   category × year, color = genre, legend on the side. It shows at a glance which
   genres the Academy rewards and how that drifts year to year across all eight
   major categories. Strong lead candidate.
2. **Genre × decade (count)** — the magnitude companion: which genres accumulate
   the major wins, and in which decades. Best supporting chart.
3. **Best Picture genre mix by decade** — the headline category's genre story on
   its own.
4. **Cut 4 — the original pre-genre count grid** (competitive wins by class ×
   year) — re-added at the owner's request, rendered with a color-scale legend
   instead of in-cell numbers so the ~98-column grid reads. Owner to validate it
   here before the social lineup is settled.

**Framing decisions awaiting owner sign-off** (no `06-viz-social` until confirmed):

- **Genre bin cutoff** — currently top-8 primary genres + `"Other"` (≤ 9 colors).
  Keep, or tighten/loosen N?
- **Which cuts to ship** — likely the lead grid + one of the two heatmaps.
- **Palette** — categorical palette for the grid; sequential teal/warm for the
  heatmaps (no diverging — counts have no midpoint).
- **Descriptive titles** — kept descriptive ("...by genre over the decades"), not
  conclusion-led, per the title rule.

If a different cut is wanted, it is added in `03-prepare` and 03 is re-run — not
built here.

⏸ **No `06-viz-social` work until the owner reviews these and confirms the lineup.**
"""))

# ── Cell 6 — cleanup ─────────────────────────────────────────────────────────
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
