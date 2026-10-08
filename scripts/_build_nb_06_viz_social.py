"""Build notebooks/06-viz-social.ipynb for the oscars-award-wins project.

The owner reviewed `04-viz` and confirmed the social lineup (3 GENRE charts) and
said to drop cut 4 (the class x year count grid) from social — it stays
exploration-only. This notebook renders the **publication-ready** set. It is a
CONSUMER: it opens the DB **read-only** and renders the 3 owner-approved charts
from the chart-ready tables that `03-prepare` built. It must NOT create any
chart_* table.

Three charts, each rendered in TWO targets from the SAME config (so social and
web can't drift) — the standard two-target render system:
  - SOCIAL: full chrome (title/subtitle/source/watermark), twitter_landscape
            (1600x900) -> outputs/social/   (via render_chart, which also displays)
  - WEB:    web_mode=True (drops title/subtitle/source, keeps only the
            @unwelcomedata watermark), web preset (1664x936) -> outputs/web/
            (built from the same base config, saved + displayed inline)

The 3 confirmed charts (GENRE-based; cut 4 EXCLUDED):
  1. LEAD   — categorical_grid: major-award wins by film genre, year by year.
  2. SUPPORT — heatmap (heatmap_teal): genres winning major Oscars, by decade.
  3. SUPPORT — heatmap (heatmap_teal): Best Picture winners by genre, by decade.

Regenerate with:  .venv/bin/python scripts/_build_nb_06_viz_social.py
Then execute with:
    .venv/bin/python -m jupyter nbconvert --to notebook --execute --inplace \
        --ExecutePreprocessor.kernel_name=oscars-venv \
        --ExecutePreprocessor.timeout=1800 notebooks/06-viz-social.ipynb
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
# 06 — Social: Oscar major-award wins by film genre

The owner reviewed `04-viz` and confirmed the framing + lineup (3 **genre** charts)
and said to drop cut 4 (the pre-genre class\\u00d7year count grid) from social, so this
notebook renders the **publication-ready** set. It **CONSUMES** the three chart-ready
tables `03-prepare` built and renders them **read-only**; it does **not** build any
chart table.

**Two-target render system (standard).** Each chart is rendered **twice from the
same config** so the two can't drift:

- **Social** — full chrome (title, subtitle, source, `@unwelcomedata` watermark),
  `twitter_landscape` (1600\\u00d7900) \\u2192 `outputs/social/`.
- **Web** — `web_mode=True` (drops title/subtitle/source, keeps only the
  `@unwelcomedata` watermark), `web` preset (1664\\u00d7936) \\u2192 `outputs/web/`. These get
  copied to `docs/` and embedded on the Pages site later, which supplies its own
  headings.

**The 3 confirmed charts (genre-based):**
1. **LEAD** \\u2014 `categorical_grid`: each major-award win at its (canonical category,
   year) cell, colored by the winning film's **primary genre** (top-8 + Other),
   genre legend as a single horizontal row above the grid.
2. `heatmap` (sequential teal): genre \\u00d7 decade count of **all** major-award wins.
3. `heatmap` (sequential teal): genre \\u00d7 decade count of **Best Picture wins only**.

*Titles are **descriptive** (house default). Read-only DuckDB, closed in the
Cleanup cell. Cut 4 is NOT rendered here.*
"""))

# ── Cell 1 — info-preservation (web charts) ──────────────────────────────────
cells.append(nbformat.v4.new_markdown_cell("""\
## Info-preservation (web charts)

Web mode **drops the title, subtitle, and source**, so any load-bearing fact that
lives ONLY in that chrome is lost on the web chart and must be restated in the
Pages README **above** each chart. What must TRAVEL to the page:

**Shared across all three:** the metric is **major-award WINS**; genre = the film's
**TMDB PRIMARY genre** (`genres[0]`); genre is **binned to the top-8 + "Other"
(9 colors)**; provenance = **AMPAS Awards Database via DLu/oscar_data; genre via
TMDB (not endorsed/certified by TMDB)**. "Major awards" = Best Picture, Directing,
the four acting awards, the two screenplay awards.

1. **Lead grid (`categorical_grid`)** — color = genre, no in-cell numbers; rows =
   the major categories, columns = ceremony year; empty cell = no major win for
   that category that year. The genre\\u2192color legend survives in-image (top row);
   the title/subtitle (what "color" means, the TMDB provenance) do NOT.
2. **All-majors heatmap** — cell = count of major-award wins per binned genre per
   decade; sequential teal (hotter = more); empty = no major win that decade. The
   "count of wins / all majors" framing lives only in the chrome.
3. **Best-Picture-only heatmap** — **the "Best Picture ONLY" subset is the
   load-bearing fact**: stripped of its title this chart is visually the same shape
   as chart 2 but means something different. Must restate: these are the **98 Best
   Picture winners only**, genre \\u00d7 decade, count, sequential teal.
"""))

# ── Cell 2 — setup (read-only) + render_pair helper ──────────────────────────
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
from IPython.display import Image as IPImage, display
from chart_factory import render_chart, _CHART_TYPES
from colors import c

DB_PATH = "data/project.duckdb"

# 03-prepare is the writer; this notebook only reads. Open read-only.
con = duckdb.connect(DB_PATH, read_only=True)

# Guard: the chart-ready tables must already exist (built by 03-prepare).
_tables = [t[0] for t in con.execute("SHOW TABLES").fetchall()]
_required = [
    "chart_major_genre_by_year",
    "chart_genre_wins_by_decade",
    "chart_bestpic_genre_by_decade",
]
_missing = [t for t in _required if t not in _tables]
assert not _missing, (
    f"Prepared chart tables missing: {_missing}. "
    "Run notebooks/03-prepare.ipynb first (it builds the chart_* tables)."
)

# Output dirs.
SOCIAL_DIR = Path("outputs/social"); SOCIAL_DIR.mkdir(parents=True, exist_ok=True)
WEB_DIR = Path("outputs/web"); WEB_DIR.mkdir(parents=True, exist_ok=True)

# Single Source line (template adds the "Source:" label — do NOT prefix it here).
SOURCE = "AMPAS Awards Database via DLu/oscar_data; genre via TMDB (not endorsed/certified by TMDB), retrieved 2026-10-08"

# Compact decade label used by both heatmaps.
decade_label = lambda d: f"{int(d)}s"


def render_pair(base_cfg: dict, filename: str):
    \"\"\"Render ONE chart config to BOTH targets so they can't drift.

    - social: full chrome at twitter_landscape -> outputs/social/<filename>.png,
      displayed inline (render_chart handles save + display).
    - web: web_mode=True at the web preset -> outputs/web/<filename>.png, built
      from the SAME base config via the router, saved + displayed inline.

    The chart type is read from base_cfg["type"] so this works for both the
    categorical_grid (chart 1) and the heatmaps (charts 2 & 3). base_cfg must NOT
    carry preset/web_mode/filename — the helper supplies those per target.
    \"\"\"
    # SOCIAL — full chrome. render_chart saves to outputs/social and displays.
    render_chart({
        **base_cfg,
        "preset": "twitter_landscape",
        "web_mode": False,
        "filename": filename,
    })

    # WEB — same config, chrome stripped, web canvas. Build via the router
    # directly so we can save to outputs/web (render_chart only writes social).
    web_img = _CHART_TYPES[base_cfg["type"]]({
        **base_cfg,
        "preset": "web",
        "web_mode": True,
    }, con)
    web_path = WEB_DIR / f"{filename}.png"
    web_img.save(web_path, format="PNG", optimize=True)
    print(f"Saved web -> {web_path}  ({web_img.size[0]}x{web_img.size[1]} px)")
    display(IPImage(filename=str(web_path)))


print("Connected (read-only). Prepared chart tables present:", _required)
"""))

# ── Cell 3 — Chart 1: LEAD categorical grid ──────────────────────────────────
cells.append(nbformat.v4.new_markdown_cell("""\
## Chart 1 — LEAD: major-award wins by film genre, year by year

The grid: the major competitive categories down the left, every ceremony year
across the top, each occupied cell colored by the **primary genre** (TMDB
`genres[0]`, binned to the top-8 + "Other") of the film that won that award that
year. The genre\\u2192color legend sits as a **single horizontal row above** the grid
(`legend_loc="top"`); there are **no in-cell numbers** — the color carries the
story. Empty cell = no major win for that category that year.
"""))

cells.append(nbformat.v4.new_code_cell("""\
major_genre_by_year = con.execute(
    "SELECT * FROM chart_major_genre_by_year ORDER BY canonical_category, year_int"
).df()

render_pair({
    "type": "categorical_grid",
    "table": major_genre_by_year,       # inline DataFrame (factory accepts df under "table")
    "row_col": "canonical_category",
    "col_col": "year_int",
    "category_col": "primary_genre_binned",
    "legend_title": "Primary genre",
    "legend_loc": "top",                # single horizontal legend row above the grid
    "col_label_fmt": lambda y: f"'{int(y) % 100:02d}",   # compact year label
    "title": "Oscar major-award wins by film genre, year by year",
    "subtitle": "Best Picture, Directing, the four acting awards & the two screenplay awards \\u00b7 color = TMDB primary genre of each winning film",
    "source": SOURCE,
}, "01_major_genre_by_year")
"""))

# ── Cell 4 — Chart 2: genre x decade count heatmap (all majors) ──────────────
cells.append(nbformat.v4.new_markdown_cell("""\
## Chart 2 — Genres winning major Oscars, by decade (count, all majors)

The magnitude view across **all** major awards: binned primary genre down the
left, decades across the top, each cell = the number of major-award wins that
genre took that decade (sequential teal \\u2014 hotter = more; in-cell numbers). Empty
cell = no major win that decade.
"""))

cells.append(nbformat.v4.new_code_cell("""\
genre_by_decade = con.execute(
    "SELECT * FROM chart_genre_wins_by_decade ORDER BY primary_genre_binned, decade"
).df()

render_pair({
    "type": "heatmap",
    "table": genre_by_decade,
    "row_col": "primary_genre_binned",
    "col_col": "decade",
    "value_col": "wins",
    "palette": "heatmap_teal",
    "col_label_fmt": decade_label,
    "show_values": True,                # in-cell numbers (default)
    "title": "Genres winning major Oscars, by decade",
    "subtitle": "Count of major-award wins per primary genre \\u00b7 empty cell = no major win that decade",
    "source": SOURCE,
}, "02_genre_wins_by_decade")
"""))

# ── Cell 5 — Chart 3: Best Picture-only genre x decade heatmap ───────────────
cells.append(nbformat.v4.new_markdown_cell("""\
## Chart 3 — Best Picture winners by genre, by decade (count, Best Picture only)

The headline category on its own: how the **Best Picture** genre mix shifts over
the decades. Same shape as chart 2, but **restricted to the 98 Best Picture wins**
(this subset is the load-bearing fact that the web version's stripped title drops).
Sequential teal, in-cell numbers; empty cell = no Best Picture of that genre that
decade.
"""))

cells.append(nbformat.v4.new_code_cell("""\
bestpic_by_decade = con.execute(
    "SELECT * FROM chart_bestpic_genre_by_decade ORDER BY primary_genre_binned, decade"
).df()

render_pair({
    "type": "heatmap",
    "table": bestpic_by_decade,
    "row_col": "primary_genre_binned",
    "col_col": "decade",
    "value_col": "wins",
    "palette": "heatmap_teal",          # task-specified teal (04 explored it warm)
    "col_label_fmt": decade_label,
    "show_values": True,
    "title": "Best Picture winners by genre, by decade",
    "subtitle": "Count of Best Picture wins per primary genre (98 BP wins) \\u00b7 empty cell = none that decade",
    "source": SOURCE,
}, "03_bestpic_genre_by_decade")
"""))

# ── Cell 6 — parity check ────────────────────────────────────────────────────
cells.append(nbformat.v4.new_markdown_cell("""\
## Social / web parity check

Confirm the same three chart names landed in both `outputs/social/` and
`outputs/web/`, and print each file's pixel dimensions (social = 1600\\u00d7900,
web = 1664\\u00d7936).
"""))

cells.append(nbformat.v4.new_code_cell("""\
from PIL import Image

NAMES = [
    "01_major_genre_by_year",
    "02_genre_wins_by_decade",
    "03_bestpic_genre_by_decade",
]
print("name                           social (WxH)      web (WxH)")
for n in NAMES:
    sp = SOCIAL_DIR / f"{n}.png"
    wp = WEB_DIR / f"{n}.png"
    ss = Image.open(sp).size if sp.exists() else None
    ws = Image.open(wp).size if wp.exists() else None
    print(f"{n:30s} {str(ss):17s} {str(ws)}")

social_set = {p.stem for p in SOCIAL_DIR.glob("*.png")} & set(NAMES)
web_set = {p.stem for p in WEB_DIR.glob("*.png")} & set(NAMES)
assert social_set == set(NAMES) == web_set, (
    f"parity mismatch: social={sorted(social_set)} web={sorted(web_set)}"
)
print("\\nParity OK: all 3 chart names present in BOTH outputs/social and outputs/web.")
"""))

# ── Cell 7 — cleanup ─────────────────────────────────────────────────────────
cells.append(nbformat.v4.new_markdown_cell("## Cleanup"))
cells.append(nbformat.v4.new_code_cell("""\
con.close()
print("Connection closed.")
"""))

nb.cells = cells

out = Path("notebooks/06-viz-social.ipynb")
nbformat.write(nb, out)
print(f"Written: {out}")
