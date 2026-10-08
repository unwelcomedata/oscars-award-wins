"""Build notebooks/03-prepare.ipynb for the oscars-award-wins project.

GENRE RE-FLOW. Two jobs, both from the interim `major_wins_genre` table (the 756
major-award wins with TMDB `primary_genre` attached in 02-clean), entirely in
DuckDB SQL:

  Job 1 — OWN the chart-ready GENRE tables (materialized in DuckDB AND saved to
          data/processed/). `04-viz` ONLY consumes these — it never shapes chart
          data off the interim table. The genre BINNING (top-N + "Other") lives
          HERE (it is data shaping). The three tables:
            genre_bin                     — primary_genre -> binned label map
            chart_major_genre_by_year     — (canonical_category, year_int,
                                             primary_genre_binned): the LEAD
                                             categorical grid (one cell per major
                                             category x year, colored by genre).
            chart_genre_wins_by_decade    — (primary_genre_binned, decade, wins):
                                             count heatmap, which genres win majors.
            chart_bestpic_genre_by_decade — (primary_genre_binned, decade, wins):
                                             Best Picture only, genre mix by decade.
  Job 2 — re-export the sellable per-win dataset (CSV + Excel + Parquet) INCLUDING
          the new `primary_genre` column, with a plain-English codebook.

If a new cut is needed, it is added HERE and 03 is re-run — never shaped in 04.

Regenerate with:  .venv/bin/python scripts/_build_nb_03_prepare.py
Then execute with: .venv/bin/python -m jupyter nbconvert --to notebook \
    --execute --inplace --ExecutePreprocessor.kernel_name=oscars-venv \
    --ExecutePreprocessor.timeout=1800 notebooks/03-prepare.ipynb
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
# 03 — Prepare: chart-ready GENRE tables + sellable export

The win-count grids barely moved decade to decade, so this re-flow pivots to
**film genre**: *which genres win the major awards, and how that shifts over the
decades.* Two **jobs**, both built from the interim **`major_wins_genre`** table
(the 756 major-award wins with TMDB `primary_genre` attached in `02-clean`),
entirely in **DuckDB SQL**:

**Job 1 — OWN the chart-ready genre tables** (materialized in DuckDB *and* saved to
`data/processed/`). `04-viz` **only consumes** these — it never shapes chart data
off the interim table. The genre **binning** (top-N genres + `"Other"`) is data
shaping, so it lives **here**.

| Table | Row axis | Column axis | Cell |
|---|---|---|---|
| `chart_major_genre_by_year` | 8 major `canonical_category` | `year_int` | binned primary genre (categorical) |
| `chart_genre_wins_by_decade` | binned primary genre | decade | win count |
| `chart_bestpic_genre_by_decade` | binned primary genre | decade | Best Picture win count |
| `chart_wins_class_by_year` (cut 4) | 6 competitive `class` | `year_int` | competitive win count (pre-genre) |

**Sparse-cell rule (load-bearing):** a `(row, column)` pair with no major win that
period is a **MISSING ROW**, not a `value = 0` / blank-category row, so the
templates render those cells **empty** (not a filled color / not a zero).

**Job 2 — re-export the sellable package**: the per-win dataset as CSV + Excel +
Parquet with a codebook, now **including `primary_genre`** (populated for
major-award films only).
"""))

# ── Cell 1 — shaping choices ────────────────────────────────────────────────
cells.append(nbformat.v4.new_markdown_cell("""\
## The shaping choices (why these cuts)

- **Genre binning lives here.** TMDB assigns many genres; a legend of 15 colors is
  unreadable. We keep the **top-N primary genres by frequency among major winners**
  and bin the rest — plus any unmatched (`NULL`) genre — into **`"Other"`**, so the
  legend stays ≤ ~9 colors + Other (the shared categorical palette holds 10). The
  binned label (`primary_genre_binned`) is what every chart table uses.
- **Lead = per-year grid, colored by genre.** The owner asked for *"cut 3's shape
  (category × year) but with a legend instead of labels."* So the lead table has
  **rows = the 8 major categories, columns = `year_int`, cell = the binned genre of
  that category's winning film that year** — the input to the new
  `categorical_grid` template (color = genre, legend off to the side, no numbers).
- **Decade count heatmaps for the magnitude story.** `chart_genre_wins_by_decade`
  (all majors) and `chart_bestpic_genre_by_decade` (Best Picture only) are
  long/tidy counts for the existing sequential `heatmap` template — "which genres
  win, by decade" and "how the Best Picture genre mix shifts."
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
print("major_wins_genre rows:", con.execute("SELECT COUNT(*) FROM major_wins_genre").fetchone()[0])

# How many distinct genres to keep as their own color before binning to "Other".
# The shared categorical palette holds 10 colors; keep the top 8 + Other = 9.
TOP_N_GENRES = 8
print("Top-N genres kept (rest -> 'Other'):", TOP_N_GENRES)
"""))

# ── Cell 3 — genre_bin map ───────────────────────────────────────────────────
cells.append(nbformat.v4.new_markdown_cell("""\
## Job 1 · the genre binning map — `genre_bin`

Rank primary genres by how often they win a major, keep the top-N as themselves,
and map everything else — **including unmatched (`NULL`) genres** — to `"Other"`.
Both chart tables join this map so they share one consistent binned label.
"""))

cells.append(nbformat.v4.new_code_cell("""\
# Top-N primary genres by major-win frequency; the rest (and NULL) -> "Other".
con.execute(\"\"\"
    CREATE OR REPLACE TABLE genre_bin AS
    WITH ranked AS (
        SELECT primary_genre, COUNT(*) AS n
        FROM major_wins_genre
        WHERE primary_genre IS NOT NULL
        GROUP BY primary_genre
        ORDER BY n DESC
    ),
    topn AS (SELECT primary_genre FROM ranked LIMIT ?)
    SELECT
        r.primary_genre,
        CASE WHEN t.primary_genre IS NOT NULL THEN r.primary_genre ELSE 'Other' END
            AS primary_genre_binned,
        r.n
    FROM ranked r
    LEFT JOIN topn t USING (primary_genre)
    ORDER BY r.n DESC
\"\"\", [TOP_N_GENRES])
genre_bin = run_sql("SELECT * FROM genre_bin ORDER BY n DESC", con)
save_processed(genre_bin, cfg, "genre_bin.parquet")
print("Distinct primary genres:", len(genre_bin),
      "| kept as themselves:", (genre_bin['primary_genre_binned'] != 'Other').sum(),
      "| binned to Other:", (genre_bin['primary_genre_binned'] == 'Other').sum())
print(genre_bin.to_string(index=False))
"""))

# ── Cell 4 — chart_major_genre_by_year (LEAD) ────────────────────────────────
cells.append(nbformat.v4.new_markdown_cell("""\
## Job 1 · Table A (LEAD) — `chart_major_genre_by_year`

The input to the lead `categorical_grid`: **one row per `(canonical_category,
year_int)`** major win, carrying the **binned primary genre** of the winning film.
Rows = the 8 major categories, columns = year, cell category = genre. A film with
no genre match maps to `"Other"` via `genre_bin` (NULLs are folded, never left as
a blank category). Absent `(category, year)` pairs stay **missing** → the grid
draws them empty.

Note: for a given category × year there is normally one winning film (ties are
rare); if two winner rows share a category+year the first by film title is kept so
each cell is unique (the grid shows one genre per cell).
"""))

cells.append(nbformat.v4.new_code_cell("""\
con.execute(\"\"\"
    CREATE OR REPLACE TABLE chart_major_genre_by_year AS
    WITH labelled AS (
        SELECT
            m.canonical_category,
            m.year_int,
            m.film,
            COALESCE(b.primary_genre_binned, 'Other') AS primary_genre_binned
        FROM major_wins_genre m
        LEFT JOIN genre_bin b USING (primary_genre)
    ),
    one_per_cell AS (
        SELECT *,
               ROW_NUMBER() OVER (
                   PARTITION BY canonical_category, year_int ORDER BY film
               ) AS rn
        FROM labelled
    )
    SELECT canonical_category, year_int, primary_genre_binned
    FROM one_per_cell
    WHERE rn = 1
    ORDER BY canonical_category, year_int
\"\"\")
tA = run_sql("SELECT * FROM chart_major_genre_by_year", con)
save_processed(tA, cfg, "chart_major_genre_by_year.parquet")
print("rows:", len(tA),
      "| categories:", tA['canonical_category'].nunique(),
      "| years:", tA['year_int'].nunique(),
      "| genres:", sorted(tA['primary_genre_binned'].unique()))
tA.head()
"""))

# ── Cell 5 — chart_genre_wins_by_decade ──────────────────────────────────────
cells.append(nbformat.v4.new_markdown_cell("""\
## Job 1 · Table B — `chart_genre_wins_by_decade` (which genres win, by decade)

Long/tidy `(primary_genre_binned, decade, wins)` = COUNT of **all** major-award
wins per binned genre per decade. The "which genres win the majors, over the
decades" magnitude view (existing sequential `heatmap`). Absent `(genre, decade)`
pairs stay missing (empty cell = that genre won nothing that decade).
"""))

cells.append(nbformat.v4.new_code_cell("""\
con.execute(\"\"\"
    CREATE OR REPLACE TABLE chart_genre_wins_by_decade AS
    SELECT
        COALESCE(b.primary_genre_binned, 'Other') AS primary_genre_binned,
        m.decade,
        COUNT(*) AS wins
    FROM major_wins_genre m
    LEFT JOIN genre_bin b USING (primary_genre)
    GROUP BY 1, 2
    ORDER BY 1, 2
\"\"\")
tB = run_sql("SELECT * FROM chart_genre_wins_by_decade", con)
save_processed(tB, cfg, "chart_genre_wins_by_decade.parquet")
print("rows:", len(tB), "| genres:", tB['primary_genre_binned'].nunique(),
      "| decades:", sorted(tB['decade'].unique()))
print("\\nWins per genre (totals):")
print(tB.groupby('primary_genre_binned')['wins'].sum().sort_values(ascending=False).to_string())
"""))

# ── Cell 6 — chart_bestpic_genre_by_decade ───────────────────────────────────
cells.append(nbformat.v4.new_markdown_cell("""\
## Job 1 · Table C — `chart_bestpic_genre_by_decade` (Best Picture genre mix)

Long/tidy `(primary_genre_binned, decade, wins)` restricted to **Best Picture**
winners only (the headline category) — so the owner can see how the Best Picture
genre mix shifts over the decades. Count heatmap on the existing template.
"""))

cells.append(nbformat.v4.new_code_cell("""\
con.execute(\"\"\"
    CREATE OR REPLACE TABLE chart_bestpic_genre_by_decade AS
    SELECT
        COALESCE(b.primary_genre_binned, 'Other') AS primary_genre_binned,
        m.decade,
        COUNT(*) AS wins
    FROM major_wins_genre m
    LEFT JOIN genre_bin b USING (primary_genre)
    WHERE m.canonical_category = 'BEST PICTURE'
    GROUP BY 1, 2
    ORDER BY 1, 2
\"\"\")
tC = run_sql("SELECT * FROM chart_bestpic_genre_by_decade", con)
save_processed(tC, cfg, "chart_bestpic_genre_by_decade.parquet")
print("rows:", len(tC), "| genres:", tC['primary_genre_binned'].nunique(),
      "| Best Picture wins total:", int(tC['wins'].sum()))
print(tC.groupby('primary_genre_binned')['wins'].sum().sort_values(ascending=False).to_string())
"""))

# ── Cell 6b — chart_wins_class_by_year (CUT 4) ───────────────────────────────
cells.append(nbformat.v4.new_markdown_cell("""\
## Job 1 · Table D (cut 4) — `chart_wins_class_by_year` (the ORIGINAL pre-genre count cut)

This is the **original "cut 3" from the first exploration pass, before any genre
enrichment**, re-added so `04-viz` can show it as **cut 4**. Long/tidy
`(class, year_int, wins)` = the COUNT of **competitive** Oscar wins for each class
in each ceremony year — the plain award-count grid, **no genre involved**.

It is wide: **6 competitive classes × ~98 year columns**. In-cell numbers across
~98 columns are unreadable, which is why it was deemed "too wide to post" the first
time. The owner's fix: `04-viz` renders it with **no in-cell numbers and a
color-scale legend** (the `heatmap` `show_values=False` mode) so color carries the
count. `03` just produces the table; `04` consumes it read-only.

Counting note (bug-trap): this is a direct `COUNT(*)` over `oscars_clean` (already
filtered to winners in `02-clean`), grouped by `class, year_int` with
`WHERE competitive`. It counts raw winning rows directly — **no `DISTINCT`** (a
`DISTINCT` on a pruned column set previously collapsed tied wins). It uses
`year_int` directly and adds **no new year/decade math** (so no `/` vs `//` trap).
"""))

cells.append(nbformat.v4.new_code_cell("""\
# CUT 4: the original pre-genre count cut — competitive wins by class x year.
con.execute(\"\"\"
    CREATE OR REPLACE TABLE chart_wins_class_by_year AS
    SELECT class, year_int, COUNT(*) AS wins
    FROM oscars_clean
    WHERE competitive
    GROUP BY class, year_int
    ORDER BY class, year_int
\"\"\")
tD = run_sql("SELECT * FROM chart_wins_class_by_year ORDER BY class, year_int", con)
save_processed(tD, cfg, "chart_wins_class_by_year.parquet")
print("rows:", len(tD),
      "| classes:", sorted(tD['class'].unique()),
      "| years:", tD['year_int'].nunique(),
      "| total competitive wins:", int(tD['wins'].sum()),
      "| wins range:", int(tD['wins'].min()), "-", int(tD['wins'].max()))
tD.head()
"""))

# ── Cell 7 — chart-table QC ──────────────────────────────────────────────────
cells.append(nbformat.v4.new_markdown_cell("""\
### QC the chart tables — fail loudly

- the lead grid has exactly the `(canonical_category, year_int,
  primary_genre_binned)` columns, one row per cell, only the 8 major categories,
- the count tables carry `(primary_genre_binned, decade, wins)` with **no
  `wins = 0`** rows (absent cells are missing, not zero) and no NULL genre labels
  (NULLs were folded to `"Other"`),
- the all-genre decade counts total **756** (every major win accounted for),
- Best Picture counts total **98**,
- the cut-4 count grid (`chart_wins_class_by_year`) has only the **6 competitive
  classes**, **98 years**, **no `wins = 0`/NULL** rows, and totals **2218**
  (every competitive win accounted for).
"""))

cells.append(nbformat.v4.new_code_cell("""\
MAJORS = {"BEST PICTURE", "DIRECTING",
          "ACTOR IN A LEADING ROLE", "ACTRESS IN A LEADING ROLE",
          "ACTOR IN A SUPPORTING ROLE", "ACTRESS IN A SUPPORTING ROLE",
          "WRITING (Adapted Screenplay)", "WRITING (Original Screenplay)"}

# Lead grid: one row per (category, year); only major categories; no NULL genre.
lead_cats = set(r[0] for r in con.execute(
    "SELECT DISTINCT canonical_category FROM chart_major_genre_by_year").fetchall())
assert lead_cats <= MAJORS, f"lead grid has non-major categories: {lead_cats - MAJORS}"
dup = con.execute(
    "SELECT COUNT(*) FROM (SELECT canonical_category, year_int, COUNT(*) c "
    "FROM chart_major_genre_by_year GROUP BY 1,2 HAVING COUNT(*) > 1)").fetchone()[0]
assert dup == 0, f"lead grid has {dup} duplicate (category, year) cells"
assert con.execute(
    "SELECT COUNT(*) FROM chart_major_genre_by_year WHERE primary_genre_binned IS NULL"
).fetchone()[0] == 0

# Count tables: no zero rows, no null genre labels.
for tbl in ("chart_genre_wins_by_decade", "chart_bestpic_genre_by_decade"):
    assert con.execute(f"SELECT COUNT(*) FROM {tbl} WHERE wins = 0").fetchone()[0] == 0, \
        f"{tbl} has wins=0 rows (should be absent, not zero)"
    assert con.execute(f"SELECT COUNT(*) FROM {tbl} WHERE wins IS NULL").fetchone()[0] == 0
    assert con.execute(f"SELECT COUNT(*) FROM {tbl} WHERE primary_genre_binned IS NULL").fetchone()[0] == 0

# Totals reconcile.
all_decade = con.execute("SELECT SUM(wins) FROM chart_genre_wins_by_decade").fetchone()[0]
assert all_decade == 756, f"all-genre decade total should be 756, got {all_decade}"
bp = con.execute("SELECT SUM(wins) FROM chart_bestpic_genre_by_decade").fetchone()[0]
assert bp == 98, f"Best Picture total should be 98, got {bp}"

# cut 4 — the original pre-genre count grid.
COMPETITIVE_CLASSES = {"Acting", "Directing", "Music", "Production", "Title", "Writing"}
cut4_classes = set(r[0] for r in con.execute(
    "SELECT DISTINCT class FROM chart_wins_class_by_year").fetchall())
assert cut4_classes == COMPETITIVE_CLASSES, \
    f"cut 4 classes should be the 6 competitive classes, got {cut4_classes}"
assert con.execute("SELECT COUNT(*) FROM chart_wins_class_by_year WHERE wins = 0").fetchone()[0] == 0, \
    "cut 4 has wins=0 rows (should be absent, not zero)"
assert con.execute("SELECT COUNT(*) FROM chart_wins_class_by_year WHERE wins IS NULL").fetchone()[0] == 0
cut4_years = con.execute("SELECT COUNT(DISTINCT year_int) FROM chart_wins_class_by_year").fetchone()[0]
assert cut4_years == 98, f"cut 4 should span 98 years, got {cut4_years}"
cut4_total = con.execute("SELECT SUM(wins) FROM chart_wins_class_by_year").fetchone()[0]
assert cut4_total == 2218, f"cut 4 competitive-win total should be 2218, got {cut4_total}"

print(f"QC OK — lead grid unique cells, no zero/null rows, "
      f"{all_decade} majors + {bp} Best Picture reconcile; "
      f"cut 4 = {cut4_total} competitive wins over {cut4_years} years.")
"""))

# ── Cell 8 — sanity figures ──────────────────────────────────────────────────
cells.append(nbformat.v4.new_markdown_cell("""\
### Sanity figures the exploration will cite
"""))

cells.append(nbformat.v4.new_code_cell("""\
print("Top genres among ALL major winners:")
print(run_sql("SELECT primary_genre_binned, SUM(wins) AS wins "
              "FROM chart_genre_wins_by_decade GROUP BY 1 ORDER BY 2 DESC", con).to_string(index=False))

print("\\nBest Picture genre mix by decade (wins):")
print(run_sql("SELECT decade, primary_genre_binned, wins "
              "FROM chart_bestpic_genre_by_decade ORDER BY decade, wins DESC", con).to_string(index=False))
"""))

# ── Cell 9 — export ─────────────────────────────────────────────────────────
cells.append(nbformat.v4.new_markdown_cell("""\
## Job 2 — sellable export + codebook (now WITH `primary_genre`)

Re-export the per-win dataset from `oscars_clean`, LEFT JOINing TMDB
`primary_genre` on `film_id`. Genre was looked up for **major-award films only**,
so `primary_genre` is populated for those and **NULL for non-major films** (stated
plainly in the codebook). CSV + Excel + Parquet (per `config.yaml`), codebook for
every column. Export name: **`oscars_award_wins_v1`**.
"""))

cells.append(nbformat.v4.new_code_cell("""\
export_df = con.execute(\"\"\"
    SELECT
        o.ceremony, o.year_int, o.decade,
        o.class, o.competitive,
        o.canonical_category, o.category,
        o.film, o.name,
        o.film_id,
        g.primary_genre
    FROM oscars_clean o
    LEFT JOIN tmdb_genres_raw g USING (film_id)
    ORDER BY o.year_int, o.class, o.canonical_category
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
    "film_id": "IMDb title identifier (e.g. tt0019071) for the winning film; the first id when an award covers multiple films (pipe-separated in the source).",
    "primary_genre": ("Primary film genre (TMDB genres[0]), looked up by IMDb id; "
                      "populated for MAJOR-award films only (Best Picture, Directing, "
                      "the four acting awards, and the two screenplay awards) and NULL "
                      "for all other wins. Source: TMDB (this product uses the TMDB API "
                      "but is not endorsed or certified by TMDB)."),
}

notes = \"\"\"Source: DLu/oscar_data (David V. Lu), oscars.csv — Academy Awards nominations +
winners, compiled from the AMPAS Awards Database (https://awardsdatabase.oscars.org/)
and IMDb. License: BSD 2-Clause for the compilation; underlying facts from AMPAS/IMDb.
Film genre is from The Movie Database (TMDB): this product uses the TMDB API but is not
endorsed or certified by TMDB; primary_genre = TMDB genres[0], populated for major-award
films only. Scope: WINS ONLY (one row per winning award), 1st ceremony (1927/28) through
the 98th (2025). A win = one row with Winner=True; a tie yields two winner rows. SciTech
and Special are non-competitive (every entry a recipient) and are flagged competitive=False.
This is a fun-tier pop-culture dataset; see SOURCES.md.\"\"\"

written = package_dataset(export_df, cfg, name="oscars_award_wins_v1",
                          codebook=codebook, notes=notes)
written
"""))

# ── Cell 10 — provenance ─────────────────────────────────────────────────────
cells.append(nbformat.v4.new_markdown_cell("""\
### Register provenance for the processed chart tables

Record the genre `chart_*` tables (and the `genre_bin` map) in `_sources` so the
project keeps full provenance for everything `04-viz` reads (all derived from
`major_wins_genre` = DLu/oscar_data + AMPAS/IMDb + TMDB genre).
"""))

cells.append(nbformat.v4.new_code_cell("""\
for t in ["genre_bin", "chart_major_genre_by_year",
          "chart_genre_wins_by_decade", "chart_bestpic_genre_by_decade"]:
    register_source(
        con, t,
        name="DLu/oscar_data + TMDB (derived)",
        url="https://github.com/DLu/oscar_data",
        license="BSD 2-Clause (compilation) + TMDB API terms (genre); facts from AMPAS + IMDb",
        notes=("Chart-ready genre table built in 03-prepare from major_wins_genre "
               "(the 756 major-award wins with TMDB primary_genre). Primary genre "
               "binned to the top-8 + 'Other'. Absent (row, column) pairs are "
               "MISSING rows (not value=0 / not a blank category) so empty cells "
               "render empty. This product uses the TMDB API but is not endorsed "
               "or certified by TMDB."),
        methodology=("Built in DuckDB SQL from major_wins_genre: the lead grid is "
                     "one row per (canonical_category, year_int) carrying the binned "
                     "genre; the decade tables COUNT wins by binned genre x decade "
                     "(all majors, and Best Picture only). Decade = (year_int//10)*10."),
        series_breaks=("TMDB genres are present-day labels, not release-era marketing "
                       "genres. Categories were added/retired over 98 years, so empty "
                       "cells = no major win of that genre/category that period."),
    )

# cut 4 — the original pre-genre count grid is NOT genre-derived: it is a plain
# competitive-win count off oscars_clean (AMPAS/IMDb via DLu/oscar_data), no TMDB.
register_source(
    con, "chart_wins_class_by_year",
    name="DLu/oscar_data (derived)",
    url="https://github.com/DLu/oscar_data",
    license="BSD 2-Clause (compilation); facts from AMPAS + IMDb",
    notes=("Cut 4: the original pre-genre count grid built in 03-prepare — "
           "COUNT of competitive Oscar wins by class x year_int, straight from "
           "oscars_clean (no genre, no TMDB). 6 competitive classes x 98 years, "
           "582 cells, 2218 wins total. Absent (class, year) pairs are MISSING "
           "rows (not value=0) so empty cells render empty; rendered in 04-viz "
           "with a color-scale legend instead of in-cell numbers."),
    methodology=("Direct COUNT(*) over oscars_clean WHERE competitive, grouped by "
                 "class, year_int. No DISTINCT (counts raw winning rows; a tie is "
                 "two rows). year_int used directly, no new year/decade math."),
    series_breaks=("Categories/classes were added and retired across 98 ceremonies, "
                   "so a class absent in a given year is a MISSING cell, not a 0."),
)
print(run_sql("SELECT duckdb_table, source_name FROM _sources ORDER BY duckdb_table",
              con).to_string(index=False))
"""))

# ── Cell 11 — next ───────────────────────────────────────────────────────────
cells.append(nbformat.v4.new_markdown_cell("""\
---
**Next:** `04-viz.ipynb` — explore the GENRE story by **consuming** these `chart_*`
tables (opening the DB read-only, never re-shaping off interim data): the LEAD
per-year categorical grid (major winners colored by genre, with a legend), the
genre × decade count heatmap, the Best Picture genre-mix heatmap, and **cut 4**
(the original pre-genre `chart_wins_class_by_year` count grid, rendered with a
color-scale legend instead of in-cell numbers).
**Pause for owner review of the framing before `06-viz-social`.**
"""))

# ── Cell 12 — cleanup ────────────────────────────────────────────────────────
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
