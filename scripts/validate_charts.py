#!/usr/bin/env python3
"""Pre-publish data-validation GATE — re-check the chart data before anything goes public.

Re-derives the headline facts the three published oscars-award-wins charts show,
straight from the SOURCE tables (`oscars_clean`, `major_wins_genre`, `genre_bin`)
and the prepared `chart_*` tables, confirms the published
`export/oscars_award_wins_v1.csv` still matches its DuckDB source value-for-value,
checks the structural invariants (row counts, the 8 major-award categories, the
9-genre binned set, the heatmap sparse-cell rule), and confirms the social/web
PNG sets stay in parity.

The three published charts and the tables they read:
  1. 01_major_genre_by_year  -> chart_major_genre_by_year (categorical grid,
     one row per (canonical_category, year_int), ~754 rows)
  2. 02_genre_wins_by_decade -> chart_genre_wins_by_decade (heatmap, all 8 major
     awards, 73 rows, sums to 756)
  3. 03_bestpic_genre_by_decade -> chart_bestpic_genre_by_decade (heatmap, Best
     Picture only, 40 rows, sums to 98)

Counting conventions respected (see artifacts/validate-script-plan.md):
  - A win = one winner row; a tie = two winner rows. Honest COUNT(*), **no
    DISTINCT** (a DISTINCT on pruned columns would collapse tied wins).
  - decade = (year_int // 10) * 10 — integer floor, never bare `/`.
  - Sparse heatmap cells are ABSENT rows, never wins = 0.
  - Genre binning = top-8 source genres kept + the rest folded to "Other" (9
    binned labels). The DB currently keeps Thriller (not Western) as the 8th —
    this script follows the DB, not the status docs.

The DB is opened **READ-ONLY** (`duckdb.connect(path, read_only=True)`) so this
gate never fights the single-writer lock a notebook or DBCode may hold. It does
not write to the DB, the exports, or the charts.

Exit code 0 = safe to publish. Non-zero = do NOT publish (prints the failing
check).

Usage:
    .venv/bin/python scripts/validate_charts.py

Run interpreter: the project `.venv` (Py3.14 has duckdb + pandas + PIL).
"""
from __future__ import annotations

import sys
from pathlib import Path

import duckdb
import pandas as pd

# --- project bootstrap -------------------------------------------------------
PROJECT = Path(__file__).resolve().parent
while not (PROJECT / "config.yaml").exists() and PROJECT != PROJECT.parent:
    PROJECT = PROJECT.parent
sys.path.insert(0, str(PROJECT))
from src.ingest import load_config  # noqa: E402

failures: list[str] = []
checks: list[str] = []

# The 8 major (competitive) canonical award categories — the only categories any
# published chart counts. Set equality is asserted against this everywhere.
MAJOR_CATEGORIES = {
    "BEST PICTURE",
    "DIRECTING",
    "ACTOR IN A LEADING ROLE",
    "ACTRESS IN A LEADING ROLE",
    "ACTOR IN A SUPPORTING ROLE",
    "ACTRESS IN A SUPPORTING ROLE",
    "WRITING (Adapted Screenplay)",
    "WRITING (Original Screenplay)",
}

# The 9 binned-genre labels = top-8 kept source genres + the "Other" catch-all.
# Asserted as the DB holds it (Thriller is the 8th, Western is folded to Other).
BINNED_GENRES = {
    "Action", "Adventure", "Comedy", "Crime", "Drama",
    "History", "Romance", "Thriller", "Other",
}


def check(name: str, condition: bool, detail: str = "") -> None:
    """Record a PASS/FAIL. `condition` must be truthy to pass."""
    if condition:
        checks.append(f"  PASS  {name}")
    else:
        failures.append(f"  FAIL  {name}" + (f" — {detail}" if detail else ""))


# ---------------------------------------------------------------------------
# Export-vs-DB parity helper
# ---------------------------------------------------------------------------

def _normalize(df: pd.DataFrame, float_round: int = 4) -> pd.DataFrame:
    """Make a frame comparable regardless of int32/int64 and NaN handling.

    - round floats (so DB's higher precision never spuriously differs),
    - render every value as a string with NaN → a stable sentinel,
    so a published CSV (int64 on read) compares equal to a DB frame (int32).
    """
    out = df.copy()
    out = out.reset_index(drop=True)
    for col in out.columns:
        if pd.api.types.is_float_dtype(out[col]):
            out[col] = out[col].round(float_round)
    # Stringify with a NaN sentinel so NaN == NaN compares equal.
    return out.astype(object).where(out.notna(), "<NA>").astype(str)


def assert_csv_matches(name: str, df_db: pd.DataFrame, csv_path: Path) -> None:
    """Assert a published CSV equals the DB-derived frame, value-for-value."""
    if not csv_path.exists():
        check(f"export parity: {name} (file present)", False, f"missing {csv_path}")
        return
    df_csv = pd.read_csv(csv_path)
    check(f"export parity: {name} row count", len(df_csv) == len(df_db),
          f"csv={len(df_csv)} db={len(df_db)}")
    check(f"export parity: {name} columns",
          list(df_csv.columns) == list(df_db.columns),
          f"csv={list(df_csv.columns)} db={list(df_db.columns)}")
    if list(df_csv.columns) != list(df_db.columns) or len(df_csv) != len(df_db):
        return
    norm_csv = _normalize(df_csv)
    norm_db = _normalize(df_db[df_csv.columns])
    # Order-insensitive content comparison: sort both by all columns before
    # comparing so a tie-order flip can't false-fail; every value and the full
    # row set must still match.
    cols = list(norm_csv.columns)
    norm_csv_s = norm_csv.sort_values(cols).reset_index(drop=True)
    norm_db_s = norm_db.sort_values(cols).reset_index(drop=True)
    equal = norm_csv_s.equals(norm_db_s)
    detail = ""
    if not equal:
        diff_mask = norm_csv_s.ne(norm_db_s)
        where = diff_mask.stack()
        first = where[where].index[:1].tolist()
        detail = f"first diff at {first}" if first else "value mismatch"
    check(f"export parity: {name} values match DB", equal, detail)


# ---------------------------------------------------------------------------
# Check groups
# ---------------------------------------------------------------------------

def check_structural(con: duckdb.DuckDBPyConnection) -> None:
    """(c) STRUCTURAL — table row counts, the 8 majors, the 9-genre bin, sparse cells."""
    expected_rows = {
        "oscars_clean": 3515,
        "major_wins_genre": 756,
        "genre_bin": 15,
        "chart_major_genre_by_year": 754,
        "chart_genre_wins_by_decade": 73,
        "chart_bestpic_genre_by_decade": 40,
    }
    for tbl, n in expected_rows.items():
        got = con.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
        check(f"structural: {tbl} = {n} rows (non-zero)", got == n and got > 0,
              f"got {got}")

    # The major-award filter yields exactly the 8 categories — in major_wins_genre
    # AND in the lead grid.
    for tbl in ("major_wins_genre", "chart_major_genre_by_year"):
        cats = {r[0] for r in con.execute(
            f"SELECT DISTINCT canonical_category FROM {tbl}").fetchall()}
        check(f"structural: {tbl} has exactly the 8 major categories",
              cats == MAJOR_CATEGORIES,
              f"missing={sorted(MAJOR_CATEGORIES - cats)}; extra={sorted(cats - MAJOR_CATEGORIES)}")

    # major_wins_genre (756) reconciles to the all-majors heatmap sum (756).
    mwg = con.execute("SELECT COUNT(*) FROM major_wins_genre").fetchone()[0]
    heatmap_sum = con.execute("SELECT SUM(wins) FROM chart_genre_wins_by_decade").fetchone()[0]
    check("structural: major_wins_genre (756) == all-majors heatmap sum",
          mwg == heatmap_sum == 756, f"major_wins_genre={mwg} heatmap_sum={heatmap_sum}")

    # genre_bin: 15 distinct source genres; exactly 8 kept as themselves + the rest
    # folded to Other; binned-label set size == 9.
    n_src = con.execute("SELECT COUNT(DISTINCT primary_genre) FROM genre_bin").fetchone()[0]
    n_kept = con.execute(
        "SELECT COUNT(*) FROM genre_bin WHERE primary_genre = primary_genre_binned"
    ).fetchone()[0]
    n_folded = con.execute(
        "SELECT COUNT(*) FROM genre_bin WHERE primary_genre_binned = 'Other'"
    ).fetchone()[0]
    binned_set = {r[0] for r in con.execute(
        "SELECT DISTINCT primary_genre_binned FROM genre_bin").fetchall()}
    check("structural: genre_bin has 15 distinct source genres", n_src == 15, f"got {n_src}")
    check("structural: genre_bin keeps 8 genres + folds the rest to Other",
          n_kept == 8 and n_folded == 7, f"kept={n_kept} folded={n_folded}")
    check("structural: binned-genre set == the 9 labels (top-8 + Other)",
          binned_set == BINNED_GENRES,
          f"missing={sorted(BINNED_GENRES - binned_set)}; extra={sorted(binned_set - BINNED_GENRES)}")

    # Sparse-cell rule across both count tables: 0 wins=0 rows, 0 wins NULL rows,
    # 0 NULL binned-genre labels.
    for tbl in ("chart_genre_wins_by_decade", "chart_bestpic_genre_by_decade"):
        n_zero = con.execute(f"SELECT COUNT(*) FROM {tbl} WHERE wins = 0").fetchone()[0]
        n_null = con.execute(f"SELECT COUNT(*) FROM {tbl} WHERE wins IS NULL").fetchone()[0]
        n_gnull = con.execute(
            f"SELECT COUNT(*) FROM {tbl} WHERE primary_genre_binned IS NULL").fetchone()[0]
        check(f"structural: {tbl} sparse-cell rule (no wins=0 / NULL / NULL genre)",
              n_zero == 0 and n_null == 0 and n_gnull == 0,
              f"wins=0:{n_zero} wins NULL:{n_null} genre NULL:{n_gnull}")

    # Both heatmaps' decade buckets fall inside 1920..2020.
    for tbl in ("chart_genre_wins_by_decade", "chart_bestpic_genre_by_decade"):
        dmin, dmax = con.execute(f"SELECT MIN(decade), MAX(decade) FROM {tbl}").fetchone()
        check(f"structural: {tbl} decades within 1920..2020",
              1920 <= dmin and dmax <= 2020, f"got [{dmin}, {dmax}]")


def check_chart01_grid(con: duckdb.DuckDBPyConnection) -> None:
    """(b) Chart 1 — the lead categorical grid: 754 cells, 8 majors, one per cell."""
    n = con.execute("SELECT COUNT(*) FROM chart_major_genre_by_year").fetchone()[0]
    check("chart01: chart_major_genre_by_year = 754 rows", n == 754, f"got {n}")

    cats = {r[0] for r in con.execute(
        "SELECT DISTINCT canonical_category FROM chart_major_genre_by_year").fetchall()}
    check("chart01: exactly the 8 major canonical categories present",
          cats == MAJOR_CATEGORIES,
          f"missing={sorted(MAJOR_CATEGORIES - cats)}; extra={sorted(cats - MAJOR_CATEGORIES)}")

    dups = con.execute(
        "SELECT COUNT(*) FROM (SELECT canonical_category, year_int, COUNT(*) c "
        "FROM chart_major_genre_by_year GROUP BY 1, 2 HAVING c > 1)"
    ).fetchone()[0]
    check("chart01: no duplicate (canonical_category, year_int) cells", dups == 0,
          f"{dups} duplicated cell(s)")

    genres = {r[0] for r in con.execute(
        "SELECT DISTINCT primary_genre_binned FROM chart_major_genre_by_year").fetchall()}
    check("chart01: binned genres ⊆ the 9-genre set", genres <= BINNED_GENRES,
          f"unexpected={sorted(genres - BINNED_GENRES)}")
    n_gnull = con.execute(
        "SELECT COUNT(*) FROM chart_major_genre_by_year WHERE primary_genre_binned IS NULL"
    ).fetchone()[0]
    check("chart01: 0 NULL binned-genre rows", n_gnull == 0, f"{n_gnull} null(s)")

    ymin, ymax = con.execute(
        "SELECT MIN(year_int), MAX(year_int) FROM chart_major_genre_by_year").fetchone()
    check("chart01: year span 1928..2025", ymin == 1928 and ymax == 2025,
          f"got [{ymin}, {ymax}]")


def check_chart02_genre_decade(con: duckdb.DuckDBPyConnection) -> None:
    """(b) Chart 2 — genre×decade heatmap (all majors): Drama top (454), 1980s peak (57)."""
    # Sum of every all-majors cell = 756 (every major win is placed exactly once).
    total = con.execute("SELECT SUM(wins) FROM chart_genre_wins_by_decade").fetchone()[0]
    check("chart02: all-majors heatmap sums to 756", total == 756, f"got {total}")

    # Top genre overall = Drama, re-derived (argmax over the genre totals).
    top_genre, top_total = con.execute(
        "SELECT primary_genre_binned, SUM(wins) AS t FROM chart_genre_wins_by_decade "
        "GROUP BY 1 ORDER BY t DESC LIMIT 1"
    ).fetchone()
    check("chart02: top genre overall is Drama", top_genre == "Drama", f"got {top_genre!r}")
    check("chart02: Drama total wins == 454", top_total == 454, f"got {top_total}")

    # Drama's peak decade (argmax over Drama's rows) = the 1980s with 57 wins.
    peak_decade, peak_wins = con.execute(
        "SELECT decade, wins FROM chart_genre_wins_by_decade "
        "WHERE primary_genre_binned = 'Drama' ORDER BY wins DESC, decade LIMIT 1"
    ).fetchone()
    check("chart02: Drama peak decade == 1980", peak_decade == 1980, f"got {peak_decade}")
    check("chart02: Drama peak-decade wins == 57", peak_wins == 57, f"got {peak_wins}")

    # Genre set present in the table == the 9 labels; "Other" is present as the catch-all.
    genres = {r[0] for r in con.execute(
        "SELECT DISTINCT primary_genre_binned FROM chart_genre_wins_by_decade").fetchall()}
    check("chart02: genre set == the 9 binned labels", genres == BINNED_GENRES,
          f"missing={sorted(BINNED_GENRES - genres)}; extra={sorted(genres - BINNED_GENRES)}")
    check("chart02: 'Other' present as the catch-all", "Other" in genres)


def check_chart03_bestpic(con: duckdb.DuckDBPyConnection) -> None:
    """(b) Chart 3 — Best-Picture heatmap: sums to 98 (= BP wins), Drama top (62)."""
    # The BP heatmap sums to 98 AND equals the Best Picture win count in oscars_clean.
    bp_sum = con.execute("SELECT SUM(wins) FROM chart_bestpic_genre_by_decade").fetchone()[0]
    bp_clean = con.execute(
        "SELECT COUNT(*) FROM oscars_clean WHERE canonical_category = 'BEST PICTURE'"
    ).fetchone()[0]
    check("chart03: BP heatmap sums to 98", bp_sum == 98, f"got {bp_sum}")
    check("chart03: BP heatmap sum == oscars_clean BEST PICTURE win count",
          bp_sum == bp_clean == 98, f"heatmap={bp_sum} oscars_clean={bp_clean}")

    # Top genre in the BP cut = Drama with 62 wins (re-derived argmax).
    top_genre, top_wins = con.execute(
        "SELECT primary_genre_binned, SUM(wins) AS t FROM chart_bestpic_genre_by_decade "
        "GROUP BY 1 ORDER BY t DESC LIMIT 1"
    ).fetchone()
    check("chart03: top BP genre is Drama", top_genre == "Drama", f"got {top_genre!r}")
    check("chart03: BP Drama wins == 62", top_wins == 62, f"got {top_wins}")

    # BP genres are a subset of the 9 binned labels (BP uses fewer genres than the
    # all-majors cut), and none are NULL.
    genres = {r[0] for r in con.execute(
        "SELECT DISTINCT primary_genre_binned FROM chart_bestpic_genre_by_decade").fetchall()}
    check("chart03: BP genres ⊆ the 9 binned labels", genres <= BINNED_GENRES,
          f"unexpected={sorted(genres - BINNED_GENRES)}")


def check_export_parity(con: duckdb.DuckDBPyConnection) -> None:
    """(a) EXPORT-vs-DB parity — the per-win CSV matches its DB source frame.

    Re-derives the exact SELECT 03-prepare used (oscars_clean LEFT JOIN
    tmdb_genres_raw on film_id) and compares value-for-value.
    """
    export_dir = PROJECT / "export"
    export_db = con.execute("""
        SELECT o.ceremony, o.year_int, o.decade, o.class, o.competitive,
               o.canonical_category, o.category, o.film, o.name, o.film_id,
               g.primary_genre
        FROM oscars_clean o
        LEFT JOIN tmdb_genres_raw g USING (film_id)
        ORDER BY o.year_int, o.class, o.canonical_category
    """).df()
    check("export parity: DB-derived export frame = 3515 rows",
          len(export_db) == 3515, f"got {len(export_db)}")
    check("export parity: DB-derived primary_genre non-null == 1122",
          int(export_db["primary_genre"].notna().sum()) == 1122,
          f"got {int(export_db['primary_genre'].notna().sum())}")
    assert_csv_matches("oscars_award_wins_v1", export_db,
                       export_dir / "oscars_award_wins_v1.csv")

    # Spot-check the CSV's own primary_genre non-null count matches the DB frame.
    csv_path = export_dir / "oscars_award_wins_v1.csv"
    if csv_path.exists():
        csv = pd.read_csv(csv_path)
        check("export parity: CSV primary_genre non-null == 1122",
              int(csv["primary_genre"].notna().sum()) == 1122,
              f"got {int(csv['primary_genre'].notna().sum())}")

    # Codebook present.
    codebook = export_dir / "oscars_award_wins_v1_codebook.md"
    check("export parity: codebook present", codebook.exists(), f"missing {codebook}")


def check_png_parity() -> None:
    """(d) SOCIAL/WEB PARITY — same 3 stems; social 1600x900, web 1664x936."""
    expected_stems = {
        "01_major_genre_by_year",
        "02_genre_wins_by_decade",
        "03_bestpic_genre_by_decade",
    }
    social_dir = PROJECT / "outputs" / "social"
    web_dir = PROJECT / "outputs" / "web"

    social = {p.stem: p for p in social_dir.glob("*.png")}
    web = {p.stem: p for p in web_dir.glob("*.png")}

    check("png parity: social has the 3 expected stems", set(social) == expected_stems,
          f"got {sorted(social)}")
    check("png parity: web has the 3 expected stems", set(web) == expected_stems,
          f"got {sorted(web)}")
    check("png parity: social and web cover the same stems", set(social) == set(web),
          f"only social: {sorted(set(social)-set(web))}; only web: {sorted(set(web)-set(social))}")

    try:
        from PIL import Image
    except ImportError:
        check("png parity: PIL available for dimension check", False,
              "Pillow not importable")
        return

    for stem, path in sorted(social.items()):
        size = Image.open(path).size
        check(f"png parity: social {stem} is 1600x900", size == (1600, 900), f"got {size}")
    for stem, path in sorted(web.items()):
        size = Image.open(path).size
        check(f"png parity: web {stem} is 1664x936", size == (1664, 936), f"got {size}")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> int:
    cfg = load_config(str(PROJECT / "config.yaml"))
    db = str(PROJECT / cfg["settings"]["duckdb_file"])
    con = duckdb.connect(db, read_only=True)  # READ-ONLY — never fight the writer lock
    try:
        check_structural(con)
        check_chart01_grid(con)
        check_chart02_genre_decade(con)
        check_chart03_bestpic(con)
        check_export_parity(con)
    finally:
        con.close()

    # PNG parity doesn't need the DB.
    check_png_parity()

    print("Pre-publish chart-data validation — oscars-award-wins")
    print("=" * 64)
    for line in checks:
        print(line)
    for line in failures:
        print(line)
    print("=" * 64)
    if failures:
        print(f"RESULT: {len(failures)} FAILURE(S) of {len(checks)+len(failures)} checks "
              f"— DO NOT PUBLISH.")
        return 1
    print(f"RESULT: all {len(checks)} checks passed — safe to publish.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
