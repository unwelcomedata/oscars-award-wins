# Data Sources — oscars-award-wins

Source standards are **tiered**:
- **Serious tier** (methodology invites scrutiny): use official government or
  authoritative primary sources only. Crowd-edited references (Wikipedia, etc.)
  are NOT used — credibility is the product.
- **Fun tier** (low-stakes pop-culture): crowd-sourced references (fan wikis,
  SuperSummary, etc.) and owner-as-primary (hand-collected counts from a book or
  broadcast) are fine — just cite them plainly below.

This file documents every data source behind the published charts and dataset,
with enough detail that someone else could independently locate and verify the
original data.

---

## Sources

### DLu/oscar_data — `oscars.csv`
- **Publisher:** DLu/oscar_data (David V. Lu), compiled from the Academy of Motion
  Picture Arts & Sciences (AMPAS) Awards Database and IMDb.
- **URL:**
  - Raw file: https://raw.githubusercontent.com/DLu/oscar_data/main/oscars.csv
  - Repository: https://github.com/DLu/oscar_data
  - Underlying primary source: https://awardsdatabase.oscars.org/
- **Format:** TSV (tab-separated values, despite the `.csv` extension).
- **License:** BSD 2-Clause for the compilation/code (© 2022 David V. Lu). The
  underlying facts are from the AMPAS Awards Database + IMDb datasets. This is a
  fun-tier pop-culture project; the compilation is authoritative-primary-backed,
  well above the fun-tier crowd-sourced bar.
- **Fields used:** `Ceremony` (ordinal 1..98), `Year` (string, e.g. `1927/28` …
  `2025`), `Class` (8 broad groupings), `CanonicalCategory` (normalized category
  name across the years), `Winner` (boolean: `True` for a win, blank for a
  non-winning nomination). `Category`, `Film`, `Name` are carried in the raw/export
  but not charted.
- **Coverage:** 1st ceremony (1927/28) through the 98th (2025). 12,137 nomination
  rows; 3,515 are wins (`Winner == True`).
- **How the source collects the data:** AMPAS publishes official nomination and
  winner results in its Awards Database; DLu/oscar_data parses those results and
  enriches each row with IMDb identifiers. One row per nomination.
- **How the source defines the data:** A **win** = one row with `Winner == True`.
  A tie yields two winner rows (both `True`); a multi-film / multi-nominee win is
  still one row. `CanonicalCategory` collapses the many wording changes of the same
  award over the decades (e.g. the leading-acting categories) so a category reads as
  one continuous series; `Category` keeps the exact Oscars.org wording.
- **Methodology changes / series breaks:** Over 98 years, categories were **added,
  retired, and renamed** — so for any category × decade grid an **empty cell means
  the category did not exist that decade, NOT zero wins**. Two of the eight `Class`
  groupings are **non-competitive**: **SciTech** (all 919 rows are `Winner == True`
  — Scientific & Technical awards have no competitive nomination, every entry is a
  recipient) and **Special** (378 of 384 `True` — honorary / governors awards).
  These are **excluded** from the competitive heatmap (counting them as "wins" would
  create artificially hot cells); the six competitive classes are Title, Acting,
  Directing, Writing, Production, and Music.
- **Known controversies / debates:** None material for a wins-by-category count.
  The only interpretive choices are the competitive-vs-honorary split and the
  category-normalization, both documented above and in the codebook.
- **Partial current decade:** the **2020s column is an in-progress decade** as of
  the 2026-10-08 retrieval (ceremonies through the 98th / 2025 only). Its lower
  counts reflect fewer elapsed years, not a decline — read it as incomplete, and
  any published chart carrying a 2020s column should say so.
- **Notes:** `Year` must be parsed to a numeric ceremony year — for a slash span
  like `1927/28` take the latter 4-digit year (`1928`); a plain `2025` stays `2025`.
  `decade = (year_int // 10) * 10`. Multi-value fields (Nominees, NomineeIds) are
  pipe (`|`)-separated in the raw file.
- **Retrieved:** 2026-10-08

### The Movie Database (TMDB) — film genre enrichment
- **Publisher:** The Movie Database (TMDB), https://www.themoviedb.org/
- **Required attribution:** *"This product uses the TMDB API but is not endorsed
  or certified by TMDB."* (TMDB's attribution requirement; carried in every chart
  subtitle that uses genre and in the export codebook.)
- **URL:** API base https://api.themoviedb.org/3 (endpoints `/3/find/{imdb_id}`,
  `/3/search/movie`, `/3/genre/movie/list`).
- **Format:** JSON over the TMDB v3 REST API. An API key is required and is kept
  out of version control (never printed, logged, or committed). Per-film responses
  were cached locally so re-runs are offline.
- **License:** TMDB API Terms of Use — free for non-commercial use with the
  attribution above. The genre labels are TMDB's.
- **Fields used:** `primary_genre` only — the **first** genre of the matched
  movie (`genres[0]`, i.e. the first entry of TMDB's `genre_ids`). The full genre
  list and `tmdb_id` are kept in the cached JSON for provenance but do not flow
  downstream.
- **Coverage:** looked up for the **unique films that won a MAJOR award** (see the
  major-award definition below) — 464 distinct films — not all 3,515 wins. A film
  that won several majors is fetched once; its genre is joined back onto each of
  its winning rows.
- **How the source collects the data:** TMDB is a community-maintained movie
  database; genres are assigned by TMDB's contributors/editors from a fixed TMDB
  genre taxonomy (Drama, Comedy, Action, Romance, etc.).
- **How the source defines the data:** "Primary genre" here is **TMDB's first
  listed genre** for the film (`genres[0]`). TMDB lists multiple genres per film;
  we deliberately keep only the first (owner decision: *primary genre only*). This
  is a single, reproducible label, not a judgment about the film's "true" genre.
- **Match method:** the IMDb id carried by the Oscars dataset (`FilmId`, already
  `tt`-prefixed) is matched to TMDB with **`/3/find/{FilmId}?external_source=imdb_id`
  as the PRIMARY, deterministic match** (no title ambiguity). A **title + ceremony-year
  search (`/3/search/movie`) is used only as a FALLBACK** when `/find` returns no
  movie result. For the 2 major rows whose `FilmId` is pipe-separated
  (multi-film award), the **first** id is used for the genre lookup (the award is
  one win; genre is attributed to the primary/first film).
- **Methodology changes / series breaks:** TMDB genres are **present-day labels**
  from the current TMDB taxonomy — they are the modern genre classification, not
  the contemporaneous (release-era) marketing genre. A 1930s Best Picture carries
  the genre TMDB assigns it today. Treat the genre as a consistent modern lens
  across all decades, not as how the film was marketed at the time.
- **Known controversies / debates:** genre is inherently fuzzy and a film often
  spans several; using only the first TMDB genre is a simplification. Many winners
  are legitimately multi-genre — e.g. *The Silence of the Lambs* is commonly tagged
  Crime/Thriller/Horror and *Oppenheimer* Biography/Drama/History — but each is
  charted under its single TMDB primary genre only. This caveat is carried in the
  README prose above the charts so a reader isn't surprised that a film they think
  of as another genre shows as Drama. Rare genres are binned into "Other" for
  legibility (see codebook).
- **Notes:** `primary_genre` is populated for **major-award films only**; it is
  NULL for non-major wins in the export (documented in the codebook).
- **Retrieved:** 2026-10-08

#### Major-award definition (used for the genre enrichment)
"Major awards" = the eight headline `CanonicalCategory` values, enumerated from
the data (756 winning rows total):

| CanonicalCategory | Class | Wins |
|---|---|---|
| BEST PICTURE | Title | 98 |
| DIRECTING | Directing | 97 |
| ACTOR IN A LEADING ROLE | Acting | 99 |
| ACTRESS IN A LEADING ROLE | Acting | 99 |
| ACTOR IN A SUPPORTING ROLE | Acting | 90 |
| ACTRESS IN A SUPPORTING ROLE | Acting | 90 |
| WRITING (Adapted Screenplay) | Writing | 98 |
| WRITING (Original Screenplay) | Writing | 85 |

**Deliberately excluded** (not "major" in this sense): `DIRECTING (Comedy/Dramatic
Picture)` (1920s one-offs superseded by `DIRECTING`), `ASSISTANT DIRECTOR`,
`WRITING (Original Story)` and `WRITING (Title Writing)` (early/auxiliary writing
awards — Original/Adapted Screenplay are the modern screenplay majors), and every
craft (`Production`), `Music`, short-film, documentary, and honorary category. This
boundary is applied consistently across the whole dataset.

---

## Notes on Data Quality

- Original source files are preserved verbatim and never modified in place.
- **Series breaks:** over 98 years the Academy added, retired, and renamed
  categories, so an empty category × decade cell means the category did not exist
  that decade, not zero wins. The 2020s is an in-progress decade (data through the
  2025 ceremony).
- **Definitions drive comparisons:** the win count, the competitive-vs-honorary
  split, the category normalization, and the single-first-TMDB-genre choice are all
  spelled out above and in the codebook, so the numbers in the charts are defined
  the same way across every decade.
