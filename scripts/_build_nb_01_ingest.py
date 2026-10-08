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
from src.clean_quality import get_connection, load_to_duckdb, register_source, run_sql
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

# ── Cell 6 — TMDB enrichment: source section ────────────────────────────────
cells.append(nbformat.v4.new_markdown_cell("""\
## Source: TMDB (film genre enrichment)

The win-count heatmaps barely move decade to decade, so this re-flow enriches the
data with **film genre** — *which genres win the major awards, and how that shifts
over the decades.* Genre comes from **[The Movie Database (TMDB)](https://www.themoviedb.org/)**.

> *This product uses the TMDB API but is not endorsed or certified by TMDB.*

**External enrichment via an API is INGESTION, not cleaning**, so it enters here
in `01-ingest`. How it works:

- **API key** — read from the project's **gitignored `.env`** as `TMDB_API_KEY`
  (via `load_env`). The key is **never printed, logged, or committed**; the cells
  below reference it only as `TMDB_API_KEY loaded from the gitignored .env`.
- **Matching (deterministic first)** — the Oscars dataset carries an IMDb id per
  film (`FilmId`, already `tt`-prefixed), so the **primary match is
  `/3/find/{FilmId}?external_source=imdb_id`** (an exact IMDb-id lookup, no title
  ambiguity). A **title + ceremony-year search** is the **fallback** only when
  `/find` returns nothing. For the 2 major rows with a pipe-separated `FilmId`
  (multi-film award) the **first** id is used.
- **Primary genre only** — we keep `genres[0]` (TMDB's first genre) per film; the
  owner asked for primary genre only.
- **Scope** — only the **unique films that won a MAJOR award** are looked up
  (464 distinct films), not all 3,515 wins. A film that won several majors is
  fetched once.
- **Caching** — every TMDB response lands untouched under `data/raw/tmdb/`
  (gitignored) so re-runs are fully **offline**; a polite ≥ 0.3s delay precedes
  each live call.

**Major-award definition** (the 8 headline categories, 756 winning rows):
`BEST PICTURE`, `DIRECTING`, `ACTOR`/`ACTRESS IN A LEADING ROLE`,
`ACTOR`/`ACTRESS IN A SUPPORTING ROLE`, `WRITING (Adapted Screenplay)`,
`WRITING (Original Screenplay)`. (Full list + exclusions in `SOURCES.md`.)
"""))

# ── Cell 7 — load key + genre map, show ONE representative /find call ─────────
cells.append(nbformat.v4.new_markdown_cell("""\
### Load the API key and show one representative `/find` call

Load `TMDB_API_KEY` from the gitignored `.env`, fetch TMDB's genre id→name map
once, then run a **single representative** `/3/find/{imdb_id}` call inline so the
mechanics are visible — printing the resolved **primary genre**, never the key.
"""))

cells.append(nbformat.v4.new_code_cell("""\
from src.ingest import (
    load_env, tmdb_genre_map, tmdb_find_by_imdb_id, enrich_major_award_genres,
)

env = load_env(".env")  # populates os.environ; returns {KEY: value} (never printed)
TMDB_API_KEY = env.get("TMDB_API_KEY") or os.environ.get("TMDB_API_KEY")
assert TMDB_API_KEY, (
    "TMDB_API_KEY not found. Add it to the gitignored .env as "
    "TMDB_API_KEY=<your key> (copied from highest-grossing-films/.env)."
)
print("TMDB_API_KEY loaded from the gitignored .env:", bool(TMDB_API_KEY))

# Genre id -> name map (one memoized call).
gmap = tmdb_genre_map(TMDB_API_KEY)
print("TMDB genre taxonomy:", sorted(gmap.values()))

# One representative /find call — a well-known Best Picture winner by IMDb id.
# (tt0109830 = Forrest Gump.) Prints the resolved primary genre, NOT the key.
demo = tmdb_find_by_imdb_id("tt0109830", TMDB_API_KEY, cfg)
print("\\nRepresentative /3/find/{imdb_id} result:")
print("  imdb_id:", demo["imdb_id"], "| tmdb_title:", demo["tmdb_title"])
print("  genres:", demo["genres"], "| primary_genre:", demo["primary_genre"],
      "| matched:", demo["matched"])
"""))

# ── Cell 8 — enrich the unique major-award films ─────────────────────────────
cells.append(nbformat.v4.new_markdown_cell("""\
### Enrich the unique major-award films

Build the list of **unique** major-award-winning films (first id of a
pipe-separated `FilmId`), run the IMDb-id → genre lookup (with the title+year
fallback), and land the untransformed result in DuckDB as **`tmdb_genres_raw`**
(one row per unique film). The join onto the per-award winning rows happens in
`02-clean`.
"""))

cells.append(nbformat.v4.new_code_cell("""\
# Major-award CanonicalCategory values (the 8 headline categories).
MAJOR_CATEGORIES = [
    "BEST PICTURE", "DIRECTING",
    "ACTOR IN A LEADING ROLE", "ACTRESS IN A LEADING ROLE",
    "ACTOR IN A SUPPORTING ROLE", "ACTRESS IN A SUPPORTING ROLE",
    "WRITING (Adapted Screenplay)", "WRITING (Original Screenplay)",
]
_in = ", ".join("'" + c.replace("'", "''") + "'" for c in MAJOR_CATEGORIES)

# Unique winning films among the majors: first id of a pipe-separated FilmId,
# one representative title + ceremony year for the fallback search.
unique_films = con.execute(f\"\"\"
    SELECT
        split_part(TRIM(FilmId), '|', 1)                       AS film_id,
        ANY_VALUE(TRIM(Film))                                  AS film,
        CAST(ANY_VALUE(
            CASE WHEN Year LIKE '%/%'
                 THEN LEFT(Year, 2) || RIGHT(Year, 2)
                 ELSE Year END) AS INTEGER)                    AS year_int
    FROM oscars_raw
    WHERE Winner = TRUE
      AND CanonicalCategory IN ({_in})
      AND FilmId IS NOT NULL AND TRIM(FilmId) <> ''
    GROUP BY split_part(TRIM(FilmId), '|', 1)
    ORDER BY film_id
\"\"\").df()
print(f"Unique major-award films to look up: {len(unique_films)}")

# IMDb-id match (primary) with title+year fallback; cached under data/raw/tmdb/.
tmdb_genres_raw = enrich_major_award_genres(unique_films, TMDB_API_KEY, cfg,
                                            rate_limit_seconds=0.3)
load_to_duckdb(tmdb_genres_raw, "tmdb_genres_raw", con)
print(f"tmdb_genres_raw: {len(tmdb_genres_raw):,} unique films loaded into DuckDB")

matched = int(tmdb_genres_raw["matched"].sum())
print(f"Matched (any method): {matched}/{len(tmdb_genres_raw)} "
      f"({matched/len(tmdb_genres_raw):.1%})")
print("Match method breakdown:")
print(tmdb_genres_raw["match_method"].value_counts().to_string())
print("\\nPrimary-genre distribution (unique films):")
print(tmdb_genres_raw["primary_genre"].value_counts(dropna=False).to_string())
"""))

# ── Cell 9 — register TMDB source ────────────────────────────────────────────
cells.append(nbformat.v4.new_code_cell("""\
register_source(
    con,
    "tmdb_genres_raw",
    "The Movie Database (TMDB)",
    url="https://www.themoviedb.org/",
    license="TMDB API Terms — free non-commercial use; attribution required",
    notes=(
        "This product uses the TMDB API but is not endorsed or certified by TMDB. "
        "Film genre enrichment for the UNIQUE major-award-winning films (464). "
        "Primary genre = genres[0] (TMDB's first genre). Matched by IMDb id "
        "(/3/find/{imdb_id}?external_source=imdb_id) with a title+year search "
        "(/3/search/movie) fallback. API key in the gitignored .env; raw responses "
        "cached under data/raw/tmdb/."
    ),
    retrieved="2026-10-08",
    methodology=(
        "For each unique major-award film (first id of a pipe-separated FilmId), "
        "resolve the TMDB movie by exact IMDb id first; fall back to a title + "
        "ceremony-year search only if /find returns no movie result. Keep genres[0]."
    ),
    series_breaks=(
        "TMDB genres are PRESENT-DAY labels from the current TMDB taxonomy, not the "
        "contemporaneous (release-era) marketing genre. Treat genre as a consistent "
        "modern lens across all decades."
    ),
)
print("TMDB source registered in _sources.")
print(run_sql("SELECT duckdb_table, source_name FROM _sources ORDER BY duckdb_table", con).to_string(index=False))
"""))

# ── Cell 10 — summary / next ─────────────────────────────────────────────────
cells.append(nbformat.v4.new_markdown_cell("""\
---
**Next:** `02-clean.ipynb` — keep the winner rows, parse `Year` to a numeric
ceremony year + decade, flag competitive vs honorary classes, **carry `FilmId`
through so the genre join can happen**, join TMDB `primary_genre` onto the
major-award wins, **report the match rate**, and save interim.
"""))

# ── Cell 11 — cleanup ────────────────────────────────────────────────────────
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
