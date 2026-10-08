"""Build 02-clean.ipynb for the oscars-award-wins project.

All cleaning happens INSIDE DuckDB (SQL), not pandas chains. This stage:
  - keeps the WIN rows (Winner = TRUE) — this is a WINS project;
  - parses `Year` to a numeric `year_int` (slash span -> latter 4-digit year)
    and derives `decade`;
  - snake_cases the kept columns, TRIMs text, flags `competitive`
    (FALSE for SciTech/Special, TRUE otherwise), and dedupes;
  - runs quality_report before saving interim Parquet.

Regenerate with:  .venv/bin/python scripts/_build_nb_02_clean.py
Then execute with: .venv/bin/python -m jupyter nbconvert --to notebook \
    --execute --inplace --ExecutePreprocessor.timeout=600 notebooks/02-clean.ipynb
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
# 02 — Clean: `oscars_raw` → `oscars_clean` (the wins)

Standardizes the raw nominations into a clean **wins** table, entirely in
**DuckDB SQL**. This stage does cleaning + light derivation only — no chart-ready
aggregation (that belongs to `03-prepare`).

What this notebook does, and why:

- **Keep only the wins** (`Winner = TRUE`). This is a wins-by-category project, so
  the ~3,515 winning rows are the universe; the 8,622 losing nominations are
  dropped here.
- **Parse `Year` → `year_int`.** The raw `Year` is a string: a plain 4-digit year
  (`2025`) for modern ceremonies, or a **slash span** (`1927/28`) for the earliest
  ones. For a slash span we take the **latter** year as a full 4-digit value
  (`1927/28` → `1928`), built in SQL as `LEFT(Year,2) || RIGHT(Year,2)` (the spans
  are all in the 1900s). A plain year passes through.
- **Derive `decade` = `(year_int // 10) * 10`** (e.g. 1928 → 1920, 1999 → 1990).
- **Flag `competitive`** = FALSE for `Class IN ('SciTech','Special')` (the
  non-competitive honorary/technical classes — all SciTech rows are "winners"), TRUE
  otherwise. The headline heatmap uses competitive classes only.
- **Carry `FilmId`** through (as `film_id`, first id of a pipe-separated multi-film
  award) — the previous build dropped it; the TMDB genre join needs it.
- **snake_case** the kept columns, **TRIM** text, and **dedupe**.

Then, for the **genre re-flow**: join TMDB `primary_genre` (from
`tmdb_genres_raw`, built in `01-ingest`) onto the **major-award wins** by
`film_id`, build the interim table **`major_wins_genre`**, and **report the match
rate** (how many major films got a genre; investigate the unmatched).

Output: interim Parquet `data/interim/oscars_clean.parquet` and
`data/interim/major_wins_genre.parquet` via `save_interim()`.
"""))

# ── Cell 1 — setup ──────────────────────────────────────────────────────────
cells.append(nbformat.v4.new_code_cell("""\
import sys, os
from pathlib import Path

PROJECT = Path.cwd()
while not (PROJECT / "config.yaml").exists() and PROJECT != PROJECT.parent:
    PROJECT = PROJECT.parent
os.chdir(PROJECT)
sys.path.insert(0, str(PROJECT))

from src.ingest import load_config
from src.clean_quality import get_connection, run_sql, quality_report, save_interim
import pandas as pd

cfg = load_config("config.yaml")
con = get_connection(cfg)
print(f"Project: {cfg['project_name']}")
print("Raw rows:", con.execute("SELECT COUNT(*) FROM oscars_raw").fetchone()[0])
"""))

# ── Cell 2 — the cleaning SQL ────────────────────────────────────────────────
cells.append(nbformat.v4.new_markdown_cell("""\
## 1. Build `oscars_clean` in DuckDB (one SQL pass)

A single `CREATE OR REPLACE TABLE` does all the cleaning: filter to wins, parse
the year, derive the decade, snake_case + TRIM the kept columns, and flag
competitive vs honorary. Deduped via `SELECT DISTINCT`.
"""))

cells.append(nbformat.v4.new_code_cell("""\
# All cleaning in DuckDB SQL (not pandas chains), per workspace norms.
# year_int: slash span '1927/28' -> 1928 via LEFT(2)||RIGHT(2); else the 4-digit Year.
# NOTE: we do NOT SELECT DISTINCT on the pruned columns — a win = one Winner=True
# row, and several legitimate wins differ only in columns we drop here (FilmId,
# NomineeIds, etc.), so DISTINCT would wrongly collapse them. We dedupe only exact
# full-row duplicates of the RAW winner rows (dedup_src below), preserving the
# honest 3,515 win count.
con.execute(\"\"\"
    CREATE OR REPLACE TABLE oscars_clean AS
    WITH dedup_src AS (
        SELECT DISTINCT * FROM oscars_raw WHERE Winner = TRUE
    )
    SELECT
        Ceremony                                           AS ceremony,
        TRIM(Class)                                        AS class,
        TRIM(CanonicalCategory)                            AS canonical_category,
        TRIM(Category)                                     AS category,
        TRIM(Film)                                         AS film,
        TRIM(Name)                                         AS name,
        -- Carry the IMDb id so the TMDB genre join can happen (first id of a
        -- pipe-separated multi-film FilmId); keep the full raw string too.
        split_part(TRIM(FilmId), '|', 1)                   AS film_id,
        NULLIF(TRIM(FilmId), '')                           AS film_id_raw,
        CAST(
            CASE WHEN Year LIKE '%/%'
                 THEN LEFT(Year, 2) || RIGHT(Year, 2)   -- '1927/28' -> '1928'
                 ELSE Year
            END AS INTEGER
        )                                                  AS year_int,
        (CAST(
            CASE WHEN Year LIKE '%/%'
                 THEN LEFT(Year, 2) || RIGHT(Year, 2)
                 ELSE Year
            END AS INTEGER) // 10) * 10                    AS decade,
        (Class NOT IN ('SciTech', 'Special'))              AS competitive
    FROM dedup_src
    ORDER BY year_int, class, canonical_category
\"\"\")

oscars_clean = run_sql("SELECT * FROM oscars_clean", con)
print("oscars_clean.shape:", oscars_clean.shape)
oscars_clean.head()
"""))

# ── Cell 3 — QC asserts ──────────────────────────────────────────────────────
cells.append(nbformat.v4.new_markdown_cell("""\
## 2. QC asserts — fail loudly

- all kept rows are wins (count close to 3,515; a handful of exact-duplicate win
  rows may collapse under `DISTINCT`),
- `year_int` spans 1928 … 2025 with no NULLs,
- `decade` is populated,
- `competitive` is present and FALSE exactly for SciTech/Special.
"""))

cells.append(nbformat.v4.new_code_cell("""\
n = len(oscars_clean)
print("rows:", n)
assert 3400 <= n <= 3515, f"win rows out of expected range: {n}"

yr = con.execute("SELECT MIN(year_int), MAX(year_int), "
                 "SUM(CASE WHEN year_int IS NULL THEN 1 ELSE 0 END) FROM oscars_clean").fetchone()
print("year_int min/max/nulls:", yr)
assert yr[0] == 1928, f"min year_int should be 1928, got {yr[0]}"
assert yr[1] == 2025, f"max year_int should be 2025, got {yr[1]}"
assert yr[2] == 0, "year_int has NULLs"

# decade populated, and competitive matches the Class rule exactly.
assert con.execute("SELECT COUNT(*) FROM oscars_clean WHERE decade IS NULL").fetchone()[0] == 0
bad = con.execute(
    "SELECT COUNT(*) FROM oscars_clean "
    "WHERE competitive <> (class NOT IN ('SciTech','Special'))"
).fetchone()[0]
assert bad == 0, f"competitive flag mismatch rows: {bad}"
print("QC OK — wins only, year_int 1928..2025, decade + competitive correct.")
"""))

# ── Cell 4 — quality report ──────────────────────────────────────────────────
cells.append(nbformat.v4.new_markdown_cell("""\
## 3. Quality report

`quality_report()` prints row count, duplicate rows, and null % per column before
we save. `film` / `name` are legitimately null for some wins (e.g. certain
honorary or non-film categories), so a moderate null threshold is expected.
"""))

cells.append(nbformat.v4.new_code_cell("""\
qc = quality_report(oscars_clean, "oscars_clean", con, max_null_pct=0.50)
"""))

# ── Cell 5 — final inspection ────────────────────────────────────────────────
cells.append(nbformat.v4.new_markdown_cell("""\
## 4. Final inspection — competitive split + wins by class
"""))

cells.append(nbformat.v4.new_code_cell("""\
print("Competitive vs honorary (win rows):")
print(run_sql(
    "SELECT competitive, COUNT(*) AS n_wins FROM oscars_clean "
    "GROUP BY competitive ORDER BY competitive DESC", con).to_string(index=False))

print("\\nWins by Class (competitive classes drive the heatmap):")
print(run_sql(
    "SELECT class, competitive, COUNT(*) AS n_wins FROM oscars_clean "
    "GROUP BY class, competitive ORDER BY n_wins DESC", con).to_string(index=False))
"""))

# ── Cell 5b — major_wins_genre (genre join) + match rate ─────────────────────
cells.append(nbformat.v4.new_markdown_cell("""\
## 5. Genre re-flow — join TMDB `primary_genre` onto the major-award wins

Build the interim table **`major_wins_genre`** entirely in DuckDB: filter
`oscars_clean` to the **8 major `CanonicalCategory` values** and `LEFT JOIN`
`tmdb_genres_raw` (from `01-ingest`) on `film_id` to attach `primary_genre`. One
row per major-award win, carrying `year_int, decade, class, canonical_category,
film, name, film_id, primary_genre`.

Then **report the match rate** — distinct major films, how many got a
`primary_genre`, and the unmatched films (title + year + id) so a low rate can be
investigated.
"""))

cells.append(nbformat.v4.new_code_cell("""\
# The 8 major CanonicalCategory values (encoded once, reused). Must match the
# MAJOR_CATEGORIES list in 01-ingest and the definition in SOURCES.md.
MAJOR_CATEGORIES = [
    "BEST PICTURE", "DIRECTING",
    "ACTOR IN A LEADING ROLE", "ACTRESS IN A LEADING ROLE",
    "ACTOR IN A SUPPORTING ROLE", "ACTRESS IN A SUPPORTING ROLE",
    "WRITING (Adapted Screenplay)", "WRITING (Original Screenplay)",
]
_in = ", ".join("'" + c.replace("'", "''") + "'" for c in MAJOR_CATEGORIES)

con.execute(f\"\"\"
    CREATE OR REPLACE TABLE major_wins_genre AS
    WITH majors AS (
        SELECT year_int, decade, class, canonical_category, film, name, film_id
        FROM oscars_clean
        WHERE canonical_category IN ({_in})
    )
    SELECT
        m.year_int, m.decade, m.class, m.canonical_category,
        m.film, m.name, m.film_id,
        g.primary_genre
    FROM majors m
    LEFT JOIN tmdb_genres_raw g USING (film_id)
    ORDER BY m.year_int, m.canonical_category
\"\"\")
major_wins_genre = run_sql("SELECT * FROM major_wins_genre", con)
print("major_wins_genre.shape:", major_wins_genre.shape)
major_wins_genre.head()
"""))

cells.append(nbformat.v4.new_code_cell("""\
# ── Match rate (films, not award rows) ───────────────────────────────────────
mr = con.execute(\"\"\"
    SELECT
        COUNT(DISTINCT film_id)                                           AS n_films,
        COUNT(DISTINCT film_id) FILTER (WHERE primary_genre IS NOT NULL)  AS n_matched
    FROM major_wins_genre
\"\"\").df()
n_films  = int(mr["n_films"].iloc[0])
n_matched = int(mr["n_matched"].iloc[0])
rate = n_matched / n_films if n_films else 0.0
print(f"TMDB genre match rate (unique major films): {n_matched}/{n_films} = {rate:.1%}")

# Award-row coverage (one film can appear on several award rows the same year).
rows_mr = con.execute(
    "SELECT COUNT(*) AS total, "
    "COUNT(*) FILTER (WHERE primary_genre IS NOT NULL) AS matched "
    "FROM major_wins_genre").df()
print(f"Major-award ROWS with a genre: {int(rows_mr['matched'].iloc[0])}/"
      f"{int(rows_mr['total'].iloc[0])}")

# Investigate the unmatched films (should be few / none).
unmatched = con.execute(\"\"\"
    SELECT DISTINCT film_id, film, year_int
    FROM major_wins_genre
    WHERE primary_genre IS NULL
    ORDER BY year_int
\"\"\").df()
print(f"\\nUnmatched films: {len(unmatched)}")
if len(unmatched):
    print(unmatched.to_string(index=False))
"""))

cells.append(nbformat.v4.new_markdown_cell("""\
### Match-rate interpretation

The IMDb-id match (`/3/find`) is deterministic, so coverage should be high
(≈ 100% of major films). Any unmatched film is printed above for investigation —
typically a film TMDB lacks under that IMDb id, which then falls back to a
title+year search in `01-ingest`. A genuinely unmatched film carries
`primary_genre = NULL` and is binned into `"Other"` in `03-prepare` (never
silently dropped). If the rate were to fall below ~95%, that would warrant a
closer look before charting.
"""))

cells.append(nbformat.v4.new_markdown_cell("""\
### QC the genre join — fail loudly

- `major_wins_genre` has exactly **756** rows (the enumerated major-win count),
- every row's `canonical_category` is one of the 8 major values,
- the LEFT JOIN did not drop or duplicate any major row,
- the null-genre rate equals the reported unmatched rate (nothing lost silently).
"""))

cells.append(nbformat.v4.new_code_cell("""\
n_major = len(major_wins_genre)
print("major rows:", n_major)
assert n_major == 756, f"expected 756 major-win rows, got {n_major}"

cats = set(r[0] for r in con.execute(
    "SELECT DISTINCT canonical_category FROM major_wins_genre").fetchall())
assert cats <= set(MAJOR_CATEGORIES), f"non-major categories present: {cats - set(MAJOR_CATEGORIES)}"

# LEFT JOIN must preserve the major row count exactly (no fan-out, no loss).
majors_only = con.execute(
    f"SELECT COUNT(*) FROM oscars_clean WHERE canonical_category IN ({_in})"
).fetchone()[0]
assert majors_only == n_major, f"join changed row count: {majors_only} -> {n_major}"
print("QC OK — 756 major wins, categories valid, join preserved every row.")
"""))

# ── Cell 6 — save interim ────────────────────────────────────────────────────
cells.append(nbformat.v4.new_markdown_cell("""\
## 6. Save interim Parquet

Write `data/interim/oscars_clean.parquet` AND
`data/interim/major_wins_genre.parquet` via `save_interim()`. These are the input
to `03-prepare`, which OWNS the chart-ready tables (the genre grid + genre×decade
heatmaps) and the sellable export.
"""))

cells.append(nbformat.v4.new_code_cell("""\
save_interim(oscars_clean, cfg, "oscars_clean.parquet")
save_interim(major_wins_genre, cfg, "major_wins_genre.parquet")
"""))

# ── Cell 7 — summary / next ──────────────────────────────────────────────────
cells.append(nbformat.v4.new_markdown_cell("""\
---
**Next:** `03-prepare.ipynb` — bin the genres, OWN the chart-ready genre tables
(per-year major winners colored by genre for the lead categorical grid; genre ×
decade and Best-Picture-genre × decade count heatmaps) from `major_wins_genre`,
and re-export the sellable per-win dataset **including `primary_genre`**.
"""))

# ── Cell 8 — cleanup ─────────────────────────────────────────────────────────
cells.append(nbformat.v4.new_markdown_cell("""\
---
## Cleanup
Close the DuckDB connection so the single-writer lock is released. Runs on
"Run All".
"""))
cells.append(nbformat.v4.new_code_cell("con.close()\nprint('connection closed')"))

nb.cells = cells

out = Path("notebooks/02-clean.ipynb")
nbformat.write(nb, out)
print(f"Written: {out}")
