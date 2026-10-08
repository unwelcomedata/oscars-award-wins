"""Build notebooks/03-prepare.ipynb for the oscars-award-wins project.

Two jobs, both from the interim `oscars_clean` table, entirely in DuckDB SQL:

  Job 1 — OWN the chart-ready heatmap tables (materialized in DuckDB AND saved to
          data/processed/). Each is long/tidy (row, column, value), one row per
          cell. GENUINELY-ABSENT (row, col) pairs are left as MISSING ROWS (not
          value=0) so the shared heatmap template renders those cells EMPTY. The
          three tables:
            chart_wins_class_by_decade    — 6 competitive Class rows x decade
            chart_wins_canoncat_by_decade — top-N CanonicalCategory rows x decade
            chart_wins_class_by_year      — 6 competitive Class rows x year_int
  Job 2 — export the sellable per-win dataset (CSV + Excel + Parquet) with a
          plain-English codebook for every column.

`04-viz` ONLY consumes these tables. If a new cut is needed, it is added HERE and
03 is re-run — never shaped inside 04.

Regenerate with:  .venv/bin/python scripts/_build_nb_03_prepare.py
Then execute with: .venv/bin/python -m jupyter nbconvert --to notebook \
    --execute --inplace --ExecutePreprocessor.timeout=1800 notebooks/03-prepare.ipynb
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
# 03 — Prepare: chart-ready heatmap tables + sellable export

Two **jobs**, both built from the interim `oscars_clean` table (the ~3.5k wins)
entirely in **DuckDB SQL**:

**Job 1 — OWN the chart-ready tables** (materialized in DuckDB *and* saved to
`data/processed/`). `04-viz` will **only consume** these — it never shapes chart
data off the interim table — so the heatmap inputs are settled here. Each table is
**long/tidy: one row per `(row, column, value)` cell**, which is exactly what the
shared `heatmap` template wants.

| Table | Row axis | Column axis | Value |
|---|---|---|---|
| `chart_wins_class_by_decade` | 6 competitive `Class` groupings | decade | win count |
| `chart_wins_canoncat_by_decade` | top-N `CanonicalCategory` | decade | win count |
| `chart_wins_class_by_year` | 6 competitive `Class` groupings | `year_int` | win count |

**The sparse-cell rule (load-bearing):** a `(row, column)` pair that had **no
wins because the category did not exist that period** is left as a **MISSING ROW**,
not a `value = 0` row. A `GROUP BY` naturally omits empty combinations, so the
template renders those cells **empty** (category absent), which is the honest read
— categories were added and retired across 98 years.

**Job 2 — export the sellable package**: the per-win dataset (not the aggregates)
as CSV + Excel + Parquet with a plain-English codebook for every column.
"""))

# ── Cell 1 — shaping choices ────────────────────────────────────────────────
cells.append(nbformat.v4.new_markdown_cell("""\
## The shaping choices (why these cuts)

- **Decade bins, not raw years, for the headline.** 98 individual years make an
  unreadable grid; binning into decades (1920s … 2020s, ~11 columns) keeps the
  "seasons" legible. A raw-year version (`chart_wins_class_by_year`) is also built
  so `04-viz` can show the owner the decade-vs-year framing trade-off side by side.
- **Competitive classes only.** SciTech and Special are non-competitive (every
  SciTech entry is a "winner"), so including them would create artificially hot
  cells. The headline grid uses the **6 competitive `Class` groupings** — Title,
  Acting, Directing, Writing, Production, Music.
- **`CanonicalCategory`, not `Category`, for the specific-award cut.**
  `CanonicalCategory` collapses the many wording changes of the same award over the
  decades, so each category reads as one continuous series. Capped to the **top-N by
  total wins** so the grid stays ≤ ~15 rows.
- **A win = one row with `Winner = TRUE`** (already filtered in `02-clean`); a tie
  is two winner rows. Counts are honest win counts.
"""))

# ── Cell 2 — setup ──────────────────────────────────────────────────────────
cells.append(nbformat.v4.new_code_cell("""\
import sys, os
from pathlib import Path

PROJECT = Path.cwd()
while not (PROJECT / "config.yaml").exists() and PROJECT != PROJECT.parent:
    PROJECT = PROJECT.parent
os.chdir(PROJECT)
sys.path.insert(0, str(PROJECT))

from src.ingest import load_config
from src.clean_quality import get_connection, run_sql, register_source, save_processed
from src.prepare import package_dataset

cfg = load_config("config.yaml")
con = get_connection(cfg)
print("Project:", cfg["project_name"])
print("oscars_clean rows:", con.execute("SELECT COUNT(*) FROM oscars_clean").fetchone()[0])

# The 6 competitive Class groupings, in a sensible display order.
COMPETITIVE_CLASSES = ["Title", "Acting", "Directing", "Writing", "Production", "Music"]
print("Competitive classes:", COMPETITIVE_CLASSES)
"""))

# ── Cell 3 — chart_wins_class_by_decade ──────────────────────────────────────
cells.append(nbformat.v4.new_markdown_cell("""\
## Job 1 · Table 1 — `chart_wins_class_by_decade` (the headline grid)

Long/tidy `(class, decade, wins)` — one row per competitive-class × decade
combination that actually had wins. Rows = the 6 competitive `Class` groupings;
columns = decade; value = win count. Any class × decade with no wins is simply
absent (the `GROUP BY` omits it) → the template draws an empty cell.
"""))

cells.append(nbformat.v4.new_code_cell("""\
con.execute(\"\"\"
    CREATE OR REPLACE TABLE chart_wins_class_by_decade AS
    SELECT
        class,
        decade,
        COUNT(*) AS wins
    FROM oscars_clean
    WHERE competitive
    GROUP BY class, decade
    ORDER BY class, decade
\"\"\")
t1 = run_sql("SELECT * FROM chart_wins_class_by_decade", con)
save_processed(t1, cfg, "chart_wins_class_by_decade.parquet")
print("rows:", len(t1), "| classes:", sorted(t1['class'].unique()),
      "| decades:", sorted(t1['decade'].unique()))
t1.head()
"""))

# ── Cell 4 — chart_wins_canoncat_by_decade ───────────────────────────────────
cells.append(nbformat.v4.new_markdown_cell("""\
## Job 1 · Table 2 — `chart_wins_canoncat_by_decade` (categories appearing/retiring)

Long/tidy `(canonical_category, decade, wins)` for the **top-N competitive
canonical categories by total wins** (capped at 15 rows). This is the "seasons"
story: categories that appear partway through history and categories that retire
show up as **empty cells** at the start or end of their row — because those
`(category, decade)` pairs are genuinely absent, not zero.
"""))

cells.append(nbformat.v4.new_code_cell("""\
# Top-15 competitive canonical categories by total wins, then their per-decade
# counts. Absent (category, decade) pairs are NOT emitted (no value=0 rows), so
# the heatmap renders them empty.
con.execute(\"\"\"
    CREATE OR REPLACE TABLE chart_wins_canoncat_by_decade AS
    WITH top_cats AS (
        SELECT canonical_category
        FROM oscars_clean
        WHERE competitive
        GROUP BY canonical_category
        ORDER BY COUNT(*) DESC
        LIMIT 15
    )
    SELECT
        o.canonical_category,
        o.decade,
        COUNT(*) AS wins
    FROM oscars_clean o
    JOIN top_cats t USING (canonical_category)
    WHERE o.competitive
    GROUP BY o.canonical_category, o.decade
    ORDER BY o.canonical_category, o.decade
\"\"\")
t2 = run_sql("SELECT * FROM chart_wins_canoncat_by_decade", con)
save_processed(t2, cfg, "chart_wins_canoncat_by_decade.parquet")
print("rows:", len(t2), "| distinct categories:", t2['canonical_category'].nunique())
print("\\nWins per category (totals):")
print(t2.groupby('canonical_category')['wins'].sum().sort_values(ascending=False).to_string())
"""))

# ── Cell 5 — chart_wins_class_by_year ────────────────────────────────────────
cells.append(nbformat.v4.new_markdown_cell("""\
## Job 1 · Table 3 — `chart_wins_class_by_year` (the decade-vs-year comparison)

Same as table 1 but columns = `year_int` instead of decade. This exists so
`04-viz` can show the owner the **decade-bin vs raw-year** framing trade-off: the
year grid is far wider (98 columns) and sparser, which is exactly the legibility
argument for binning into decades.
"""))

cells.append(nbformat.v4.new_code_cell("""\
con.execute(\"\"\"
    CREATE OR REPLACE TABLE chart_wins_class_by_year AS
    SELECT
        class,
        year_int,
        COUNT(*) AS wins
    FROM oscars_clean
    WHERE competitive
    GROUP BY class, year_int
    ORDER BY class, year_int
\"\"\")
t3 = run_sql("SELECT * FROM chart_wins_class_by_year", con)
save_processed(t3, cfg, "chart_wins_class_by_year.parquet")
print("rows:", len(t3), "| distinct years:", t3['year_int'].nunique())
t3.head()
"""))

# ── Cell 6 — chart-table QC ──────────────────────────────────────────────────
cells.append(nbformat.v4.new_markdown_cell("""\
### QC the chart tables — fail loudly

- all three tables carry exactly the `(row, column, value)` columns,
- the class tables cover only the 6 competitive classes,
- **no `value = 0` rows exist** (absent cells are missing rows, not zeros),
- the total wins in `chart_wins_class_by_decade` equals the competitive win count
  in `oscars_clean` (nothing dropped or double-counted).
"""))

cells.append(nbformat.v4.new_code_cell("""\
# No zero-value rows in any chart table (sparse cells must be ABSENT, not 0).
for tbl, val in [("chart_wins_class_by_decade", "wins"),
                 ("chart_wins_canoncat_by_decade", "wins"),
                 ("chart_wins_class_by_year", "wins")]:
    zeros = con.execute(f"SELECT COUNT(*) FROM {tbl} WHERE {val} = 0").fetchone()[0]
    assert zeros == 0, f"{tbl} has {zeros} value=0 rows (should be absent, not zero)"
    assert con.execute(f"SELECT COUNT(*) FROM {tbl} WHERE {val} IS NULL").fetchone()[0] == 0

# class tables cover only the 6 competitive classes
for tbl in ("chart_wins_class_by_decade", "chart_wins_class_by_year"):
    classes = set(r[0] for r in con.execute(f"SELECT DISTINCT class FROM {tbl}").fetchall())
    assert classes <= set(COMPETITIVE_CLASSES), f"{tbl} has non-competitive classes: {classes}"

# totals reconcile: class-by-decade wins == competitive wins in oscars_clean
comp_wins = con.execute("SELECT COUNT(*) FROM oscars_clean WHERE competitive").fetchone()[0]
grid_wins = con.execute("SELECT SUM(wins) FROM chart_wins_class_by_decade").fetchone()[0]
assert comp_wins == grid_wins, f"win totals disagree: clean={comp_wins} grid={grid_wins}"
print(f"QC OK — no zero/null cells, competitive classes only, "
      f"{grid_wins} competitive wins reconcile.")
"""))

# ── Cell 7 — sanity figures ──────────────────────────────────────────────────
cells.append(nbformat.v4.new_markdown_cell("""\
### Sanity figures the exploration will cite

The hottest class × decade cells, and the categories that start/stop partway
through history (the sparse-cell story).
"""))

cells.append(nbformat.v4.new_code_cell("""\
print("Top class x decade cells by wins:")
print(run_sql("SELECT class, decade, wins FROM chart_wins_class_by_decade "
              "ORDER BY wins DESC LIMIT 8", con).to_string(index=False))

print("\\nFirst and last decade each top category appears (empty before/after = absent):")
print(run_sql(
    "SELECT canonical_category, MIN(decade) AS first_decade, "
    "MAX(decade) AS last_decade, SUM(wins) AS total_wins "
    "FROM chart_wins_canoncat_by_decade GROUP BY canonical_category "
    "ORDER BY total_wins DESC", con).to_string(index=False))
"""))

# ── Cell 8 — export ─────────────────────────────────────────────────────────
cells.append(nbformat.v4.new_markdown_cell("""\
## Job 2 — sellable export + codebook

Export the clean **per-win** dataset (not the aggregates) from `oscars_clean` as
CSV + Excel + Parquet (per `config.yaml` `export.formats`), with a codebook
describing every column in plain English. `package_dataset()` calls `strip_pii()`
internally — `strip_pii_columns` is empty in config, so it's a no-op (public
pop-culture data). Export name: **`oscars_award_wins_v1`**.
"""))

cells.append(nbformat.v4.new_code_cell("""\
export_df = con.execute(\"\"\"
    SELECT
        ceremony, year_int, decade,
        class, competitive,
        canonical_category, category,
        film, name
    FROM oscars_clean
    ORDER BY year_int, class, canonical_category
\"\"\").df()

codebook = {
    "ceremony": "Academy Awards ceremony ordinal (1 = 1927/28 ... 98 = 2025).",
    "year_int": "Ceremony year as a 4-digit integer. For the earliest slash-span years (e.g. '1927/28') this is the latter year (1928).",
    "decade": "Decade the ceremony falls in, as the starting year (e.g. 1928 -> 1920, 1999 -> 1990).",
    "class": "Broad award grouping (Title, Acting, Directing, Writing, Production, Music, SciTech, Special).",
    "competitive": "True for competitive classes; False for SciTech and Special (non-competitive honorary/technical awards where every entry is a recipient).",
    "canonical_category": "Normalized category name that collapses the many wording changes of the same award over the years, so a category reads as one continuous series.",
    "category": "Exact category wording as published by the Academy for that ceremony.",
    "film": "Film associated with the win (may be empty for some honorary/non-film categories).",
    "name": "Person(s) or entity credited with the win (may be empty for some categories).",
}

notes = \"\"\"Source: DLu/oscar_data (David V. Lu), oscars.csv — Academy Awards nominations +
winners, compiled from the AMPAS Awards Database (https://awardsdatabase.oscars.org/)
and IMDb. License: BSD 2-Clause for the compilation; underlying facts from AMPAS/IMDb.
Scope: WINS ONLY (one row per winning award), 1st ceremony (1927/28) through the 98th
(2025). A win = one row with Winner=True; a tie yields two winner rows. SciTech and
Special are non-competitive (every entry a recipient) and are flagged competitive=False.
This is a fun-tier pop-culture dataset; see SOURCES.md.\"\"\"

written = package_dataset(export_df, cfg, name="oscars_award_wins_v1",
                          codebook=codebook, notes=notes)
written
"""))

# ── Cell 9 — provenance ──────────────────────────────────────────────────────
cells.append(nbformat.v4.new_markdown_cell("""\
### Register provenance for the processed chart tables

Record the three `chart_*` tables in `_sources` so the project keeps full
provenance for everything `04-viz` reads (all derived from `oscars_clean`,
ultimately DLu/oscar_data + AMPAS/IMDb).
"""))

cells.append(nbformat.v4.new_code_cell("""\
for t in ["chart_wins_class_by_decade", "chart_wins_canoncat_by_decade",
          "chart_wins_class_by_year"]:
    register_source(
        con, t,
        name="DLu/oscar_data (derived)",
        url="https://github.com/DLu/oscar_data",
        license="BSD 2-Clause (compilation); facts from AMPAS Awards Database + IMDb",
        notes=("Chart-ready long/tidy (row, column, value) heatmap table built in "
               "03-prepare from oscars_clean. Competitive wins only. Absent "
               "(row, column) pairs are MISSING rows (not value=0) so empty cells "
               "render empty = category absent that period."),
        methodology=("Aggregated in DuckDB SQL as COUNT(*) of winning rows grouped "
                     "by the row axis (class or canonical_category) and the column "
                     "axis (decade or year_int). Decade = (year_int // 10) * 10."),
        series_breaks=("Categories added/retired/renamed over 98 years, so empty "
                       "cells = category did not exist that period, NOT zero wins."),
    )
print(run_sql("SELECT duckdb_table, source_name FROM _sources ORDER BY duckdb_table",
              con).to_string(index=False))
"""))

# ── Cell 10 — next ───────────────────────────────────────────────────────────
cells.append(nbformat.v4.new_markdown_cell("""\
---
**Next:** `04-viz.ipynb` — explore the heatmaps by **consuming** these `chart_*`
tables (opening the DB read-only, never re-shaping off interim data): class ×
decade (headline), canonical-category × decade (appearing/retiring categories),
class × year (the decade-vs-year framing comparison), and a warm-palette variant.
**Pause for owner review of the framing before `06-viz-social`.**
"""))

# ── Cell 11 — cleanup ────────────────────────────────────────────────────────
cells.append(nbformat.v4.new_markdown_cell("""\
---
## Cleanup
Close the DuckDB connection so the single-writer lock is released. Runs on
"Run All".
"""))
cells.append(nbformat.v4.new_code_cell("con.close()\nprint('connection closed')"))

nb.cells = cells

out = Path("notebooks/03-prepare.ipynb")
nbformat.write(nb, out)
print(f"Written: {out}")
