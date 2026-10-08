"""Web ingestion utilities.

Handles three source types:
  - html_table  : pandas read_html on a static page
  - html_scrape : BeautifulSoup for custom element extraction
  - csv / json  : direct download and save to data/raw

All raw files land in data/raw unchanged. Call load_config() once per notebook
to get paths and source definitions from config.yaml.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import pandas as pd
import requests
import yaml
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

def load_config(config_path: str | Path = "config.yaml") -> dict[str, Any]:
    """Load project config.yaml and return it as a dict."""
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def raw_path(cfg: dict, filename: str) -> Path:
    """Return a Path inside data/raw, creating the directory if needed."""
    p = Path(cfg["paths"]["data_raw"]) / filename
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

_CACHE_DIR: Path | None = None


def _get_cache_dir(cfg: dict) -> Path:
    """Return the cache directory (data/raw by default)."""
    global _CACHE_DIR
    if _CACHE_DIR is None:
        _CACHE_DIR = Path(cfg["paths"]["data_raw"])
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return _CACHE_DIR


def fetch_html(url: str, headers: dict | None = None, timeout: int = 30) -> str:
    """Fetch a URL and return the response text.

    Raises requests.HTTPError on non-2xx status.
    """
    hdrs = {**_DEFAULT_HEADERS, **(headers or {})}
    resp = requests.get(url, headers=hdrs, timeout=timeout)
    resp.raise_for_status()
    return resp.text


def fetch_cached(
    url: str,
    filename: str,
    cfg: dict,
    max_age_hours: float = 24.0,
    headers: dict | None = None,
    timeout: int = 30,
) -> str:
    """Fetch a URL with local file caching.

    If a cached file exists and is younger than max_age_hours, returns its
    contents without making a network request. Otherwise fetches, saves to
    data/raw/{filename}, and returns the content.

    Args:
        url:            URL to fetch.
        filename:       Cache filename (saved in data/raw/).
        cfg:            Loaded config dict.
        max_age_hours:  Re-fetch if cache is older than this (0 = always fetch).
        headers:        Optional extra HTTP headers.
        timeout:        Request timeout in seconds.

    Returns:
        Response text (from cache or network).
    """
    cache_path = _get_cache_dir(cfg) / filename
    if cache_path.exists() and max_age_hours > 0:
        age_hours = (time.time() - cache_path.stat().st_mtime) / 3600
        if age_hours < max_age_hours:
            return cache_path.read_text(encoding="utf-8")

    text = fetch_html(url, headers=headers, timeout=timeout)
    cache_path.write_text(text, encoding="utf-8")
    return text


def fetch_with_retry(
    url: str,
    headers: dict | None = None,
    timeout: int = 30,
    max_retries: int = 3,
    rate_limit_seconds: float = 1.5,
) -> str:
    """Fetch a URL with rate limiting and exponential backoff on 429s.

    Args:
        url:                 URL to fetch.
        headers:             Optional extra HTTP headers.
        timeout:             Request timeout in seconds.
        max_retries:         Max retry attempts on 429/5xx.
        rate_limit_seconds:  Minimum delay between requests.

    Returns:
        Response text.

    Raises:
        requests.HTTPError after exhausting retries.
    """
    hdrs = {**_DEFAULT_HEADERS, **(headers or {})}
    time.sleep(rate_limit_seconds)

    for attempt in range(max_retries + 1):
        resp = requests.get(url, headers=hdrs, timeout=timeout)
        if resp.status_code == 429 or resp.status_code >= 500:
            if attempt < max_retries:
                wait = rate_limit_seconds * (2 ** attempt)
                print(f"  ⚠ {resp.status_code} on {url} — retrying in {wait:.0f}s")
                time.sleep(wait)
                continue
        resp.raise_for_status()
        return resp.text

    resp.raise_for_status()  # will raise on the last failed attempt
    return ""  # unreachable


def fetch_html_js(url: str, wait_selector: str | None = None, timeout: int = 30000) -> str:
    """Fetch a JS-rendered page using Playwright (headless Chromium).

    Use this when fetch_html() returns an empty or incomplete page.
    Requires: playwright install chromium

    Args:
        url:           Page URL.
        wait_selector: Optional CSS selector to wait for before returning HTML.
        timeout:       Playwright timeout in milliseconds.
    """
    from playwright.sync_api import sync_playwright  # lazy import

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page(extra_http_headers=_DEFAULT_HEADERS)
        page.goto(url, timeout=timeout)
        if wait_selector:
            page.wait_for_selector(wait_selector, timeout=timeout)
        else:
            page.wait_for_load_state("networkidle", timeout=timeout)
        html = page.content()
        browser.close()
    return html


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------

def parse_html_table(html: str, table_index: int = 0) -> pd.DataFrame:
    """Extract a <table> from HTML by index and return it as a DataFrame.

    Cleans up column names: lowercase, spaces → underscores.

    Note: pandas 3.x no longer accepts a raw HTML *string* — it must be a
    file-like object — so the string is wrapped in StringIO.
    """
    from io import StringIO

    tables = pd.read_html(StringIO(html))
    if not tables:
        raise ValueError("No tables found in the provided HTML.")
    if table_index >= len(tables):
        raise IndexError(
            f"table_index {table_index} out of range — page has {len(tables)} table(s)."
        )
    df = tables[table_index]
    df.columns = [
        str(c).strip().lower().replace(" ", "_").replace("-", "_")
        for c in df.columns
    ]
    return df


def parse_html_scrape(
    html: str,
    row_selector: str,
    field_map: dict[str, str],
) -> pd.DataFrame:
    """Scrape structured rows from HTML using CSS selectors.

    Args:
        html:          Raw HTML string.
        row_selector:  CSS selector that matches each "row" element.
        field_map:     Dict mapping output column name → CSS selector
                       relative to each row element.
                       Use '' (empty string) to get the row's own text.

    Example:
        parse_html_scrape(html, "tr.data-row", {"name": "td.name", "value": "td.val"})
    """
    soup = BeautifulSoup(html, "lxml")
    rows = soup.select(row_selector)
    records = []
    for row in rows:
        record: dict[str, str] = {}
        for col, selector in field_map.items():
            el = row.select_one(selector) if selector else row
            record[col] = el.get_text(" ", strip=True) if el else ""
        records.append(record)
    return pd.DataFrame(records)


# ---------------------------------------------------------------------------
# Download helpers
# ---------------------------------------------------------------------------

def download_file(url: str, dest: Path, headers: dict | None = None, timeout: int = 60) -> Path:
    """Stream-download a file (CSV, JSON, zip, etc.) to dest and return the path."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    hdrs = {**_DEFAULT_HEADERS, **(headers or {})}
    with requests.get(url, headers=hdrs, timeout=timeout, stream=True) as resp:
        resp.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in resp.iter_content(chunk_size=65536):
                f.write(chunk)
    return dest


# ---------------------------------------------------------------------------
# Source-driven ingest (reads config.yaml sources block)
# ---------------------------------------------------------------------------

def ingest_source(
    name: str,
    cfg: dict,
    save_raw: bool = True,
    js_wait_selector: str | None = None,
    row_selector: str | None = None,
    field_map: dict[str, str] | None = None,
    rate_limit_seconds: float = 1.0,
) -> pd.DataFrame:
    """Ingest a named source from config.yaml and return a DataFrame.

    Args:
        name:               Key under `sources:` in config.yaml.
        cfg:                Loaded config dict (from load_config()).
        save_raw:           If True, save the raw HTML/bytes to data/raw/.
        js_wait_selector:   Passed to fetch_html_js() if js_render is true.
        row_selector:       Required for html_scrape type.
        field_map:          Required for html_scrape type.
        rate_limit_seconds: Polite delay before fetching.
    """
    source = cfg["sources"][name]
    url: str = source["url"]
    source_type: str = source.get("type", "html_table")
    js_render: bool = source.get("js_render", False)
    table_index: int = source.get("table_index", 0)

    time.sleep(rate_limit_seconds)

    if source_type == "csv":
        dest = raw_path(cfg, f"{name}.csv")
        download_file(url, dest)
        return pd.read_csv(dest, encoding=cfg["settings"]["encoding"])

    if source_type == "json":
        dest = raw_path(cfg, f"{name}.json")
        download_file(url, dest)
        with open(dest, encoding=cfg["settings"]["encoding"]) as f:
            data = json.load(f)
        return pd.json_normalize(data)

    # HTML-based types
    html = fetch_html_js(url, wait_selector=js_wait_selector) if js_render else fetch_html(url)

    if save_raw:
        raw_path(cfg, f"{name}.html").write_text(html, encoding="utf-8")

    if source_type == "html_table":
        return parse_html_table(html, table_index=table_index)

    if source_type == "html_scrape":
        if row_selector is None or field_map is None:
            raise ValueError("html_scrape requires row_selector and field_map arguments.")
        return parse_html_scrape(html, row_selector, field_map)

    raise ValueError(f"Unknown source type '{source_type}'. Use: html_table, html_scrape, csv, json.")


# ---------------------------------------------------------------------------
# Project-specific ingest: the Oscars award dataset (TAB-separated)
# ---------------------------------------------------------------------------

def ingest_oscars(cfg: dict, rate_limit_seconds: float = 1.0) -> pd.DataFrame:
    """Download the DLu/oscar_data `oscars.csv` and return it UNtransformed.

    The file is **tab-separated** (despite the `.csv` extension), so it is read
    with ``sep="\\t"``. Nothing is cleaned or reshaped here — this is the raw
    stage: one row per Academy Award nomination, all 14 source columns intact.
    Cleaning happens in ``02-clean``.

    The raw file is cached to ``data/raw/oscars.csv`` via ``download_file``; if a
    cached copy already exists it is reused (no network request), so re-runs are
    free. A polite ``rate_limit_seconds`` delay is applied before any network
    fetch.

    Args:
        cfg:                Loaded config dict (from ``load_config()``).
        rate_limit_seconds: Minimum delay before a network download (>= 1.0s).

    Returns:
        The raw nominations DataFrame (12,137 rows x 14 columns).
    """
    source = cfg["sources"]["oscars"]
    url: str = source["url"]
    dest = raw_path(cfg, "oscars.csv")

    if dest.exists():
        print(f"Using cached raw file -> {dest}")
    else:
        time.sleep(max(rate_limit_seconds, 1.0))  # polite delay before fetching
        download_file(url, dest)
        print(f"Downloaded -> {dest}")

    # TAB-separated, NOT comma. keep_default_na so the blank Winner cells read as
    # NaN (non-winner) and True reads as a winner — no transformation applied.
    df = pd.read_csv(dest, sep="\t", encoding=cfg["settings"]["encoding"])
    print(f"Read {len(df):,} rows x {df.shape[1]} columns (raw, untransformed)")
    return df


# ---------------------------------------------------------------------------
# Environment / secrets (.env) — no python-dotenv dependency
# ---------------------------------------------------------------------------

def load_env(env_path: str | Path = ".env") -> dict[str, str]:
    """Load KEY=VALUE lines from a .env file into os.environ and return them.

    Ignores blank lines and comments. Does not overwrite already-set vars.
    Never logs values. The .env file is gitignored — keys stay local.
    """
    import os
    env: dict[str, str] = {}
    p = Path(env_path)
    if not p.exists():
        return env
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip()
        env[k] = v
        os.environ.setdefault(k, v)
    return env


# ---------------------------------------------------------------------------
# TMDB genre enrichment (cached + rate-limited)
# ---------------------------------------------------------------------------
# External enrichment via an API is INGESTION, not cleaning (per workspace
# norms), so the TMDB lookups live here in src/ingest.py and are narrated in
# 01-ingest. The TMDB v3 API key is read from the gitignored .env as
# TMDB_API_KEY (load_env) — it is NEVER printed, logged, or committed.
#
# Matching strategy (deterministic first):
#   PRIMARY  — GET /3/find/{imdb_id}?external_source=imdb_id (exact IMDb-id match)
#   FALLBACK — GET /3/search/movie?query=title&year=... (only if /find misses)
# "Primary genre" = genres[0] (TMDB's genre_ids order). Every call is cached per
# film as JSON under data/raw/tmdb/ so re-runs are fully offline.

_TMDB_BASE = "https://api.themoviedb.org/3"
_tmdb_genre_map: dict[int, str] | None = None


def _tmdb_cache_dir(cfg: dict) -> Path:
    """Return (creating) the per-film TMDB JSON cache dir under data/raw/tmdb/."""
    d = Path(cfg["paths"]["data_raw"]) / "tmdb"
    d.mkdir(parents=True, exist_ok=True)
    return d


def tmdb_genre_map(api_key: str) -> dict[int, str]:
    """Return TMDB's genre id -> name mapping (fetched once, memoized)."""
    global _tmdb_genre_map
    if _tmdb_genre_map is None:
        resp = requests.get(
            f"{_TMDB_BASE}/genre/movie/list",
            params={"api_key": api_key}, timeout=20,
        )
        resp.raise_for_status()
        _tmdb_genre_map = {g["id"]: g["name"] for g in resp.json()["genres"]}
    return _tmdb_genre_map


def _safe_slug(title: str, year: int | None) -> str:
    import re
    s = re.sub(r"[^A-Za-z0-9]+", "_", str(title)).strip("_").lower()
    return f"{s}_{year or 'na'}"


def tmdb_find_by_imdb_id(
    imdb_id: str,
    api_key: str,
    cfg: dict,
    rate_limit_seconds: float = 0.3,
) -> dict[str, Any]:
    """PRIMARY matcher: resolve a film's TMDB primary genre by its IMDb id.

    Uses GET /3/find/{imdb_id}?external_source=imdb_id — an exact IMDb-id lookup
    (no title ambiguity). Reads movie_results[0]; maps its genre_ids to names via
    tmdb_genre_map; primary_genre = the first genre name (or None). Cached per id
    under data/raw/tmdb/find_{imdb_id}.json so re-runs are offline.

    Returns {imdb_id, tmdb_id, tmdb_title, genres (list[str]), primary_genre,
    matched (bool)}. ``matched`` is False when /find returns no movie_results.
    """
    cache_path = _tmdb_cache_dir(cfg) / f"find_{imdb_id}.json"
    if cache_path.exists():
        return json.loads(cache_path.read_text(encoding="utf-8"))

    time.sleep(rate_limit_seconds)  # polite
    resp = requests.get(
        f"{_TMDB_BASE}/find/{imdb_id}",
        params={"api_key": api_key, "external_source": "imdb_id"}, timeout=20,
    )
    resp.raise_for_status()
    results = resp.json().get("movie_results", [])

    gmap = tmdb_genre_map(api_key)
    if results:
        top = results[0]
        genres = [gmap.get(i) for i in top.get("genre_ids", []) if gmap.get(i)]
        rec = {
            "imdb_id": imdb_id,
            "tmdb_id": top.get("id"),
            "tmdb_title": top.get("title"),
            "genres": genres,
            "primary_genre": genres[0] if genres else None,
            "matched": True,
        }
    else:
        rec = {
            "imdb_id": imdb_id, "tmdb_id": None, "tmdb_title": None,
            "genres": [], "primary_genre": None, "matched": False,
        }
    cache_path.write_text(json.dumps(rec), encoding="utf-8")
    return rec


def tmdb_lookup_movie(
    title: str,
    year: int | None,
    api_key: str,
    cfg: dict,
    rate_limit_seconds: float = 0.3,
) -> dict[str, Any]:
    """FALLBACK matcher: look up a film on TMDB by title (+year) search.

    Used only when ``tmdb_find_by_imdb_id`` returns no movie_results (a film with
    no usable IMDb id, or an id TMDB doesn't carry). GET /3/search/movie with the
    title and (optional) year; takes the first result. Cached per title+year
    under data/raw/tmdb/ so re-runs are offline.

    Returns {title, year, tmdb_id, tmdb_title, genres (list[str]), primary_genre,
    matched (bool)}.
    """
    cache_path = _tmdb_cache_dir(cfg) / f"{_safe_slug(title, year)}.json"
    if cache_path.exists():
        return json.loads(cache_path.read_text(encoding="utf-8"))

    time.sleep(rate_limit_seconds)  # polite
    params = {"api_key": api_key, "query": title}
    if year:
        params["year"] = year
    resp = requests.get(f"{_TMDB_BASE}/search/movie", params=params, timeout=20)
    resp.raise_for_status()
    results = resp.json().get("results", [])

    gmap = tmdb_genre_map(api_key)
    if results:
        top = results[0]
        genres = [gmap.get(i) for i in top.get("genre_ids", []) if gmap.get(i)]
        rec = {
            "title": title, "year": year,
            "tmdb_id": top.get("id"),
            "tmdb_title": top.get("title"),
            "genres": genres,
            "primary_genre": genres[0] if genres else None,
            "matched": True,
        }
    else:
        rec = {
            "title": title, "year": year, "tmdb_id": None, "tmdb_title": None,
            "genres": [], "primary_genre": None, "matched": False,
        }
    cache_path.write_text(json.dumps(rec), encoding="utf-8")
    return rec


def enrich_major_award_genres(
    unique_films: pd.DataFrame,
    api_key: str,
    cfg: dict,
    rate_limit_seconds: float = 0.3,
) -> pd.DataFrame:
    """Attach a TMDB primary genre to each UNIQUE major-award-winning film.

    ``unique_films`` is a DataFrame with one row per distinct film, columns:
      - ``film_id``  : the IMDb id to match on (first id of a pipe-separated
                       FilmId; already 'tt'-prefixed in this dataset),
      - ``film``     : film title (fallback search),
      - ``year_int`` : ceremony year as int (fallback search year).

    Per film: try the deterministic IMDb-id match (``tmdb_find_by_imdb_id``);
    only if that misses, fall back to a title+year search (``tmdb_lookup_movie``).
    Every TMDB response is cached under data/raw/tmdb/ so re-runs are offline;
    a polite ``rate_limit_seconds`` (>= 0.3s) precedes each LIVE call.

    Returns a tidy DataFrame
    ``[film_id, film, year_int, tmdb_id, primary_genre, matched, match_method]``,
    one row per unique film. ``match_method`` is 'imdb_id', 'title_year', or
    'none'. The caller (02-clean) joins ``primary_genre`` back onto the per-award
    winning rows by ``film_id`` and reports the match rate.
    """
    recs = []
    for _, r in unique_films.iterrows():
        film_id = (str(r["film_id"]).strip() if r.get("film_id") is not None else "")
        title = r.get("film")
        year = r.get("year_int")
        year = int(year) if pd.notna(year) else None

        rec = {"film_id": film_id, "film": title, "year_int": year,
               "tmdb_id": None, "primary_genre": None, "matched": False,
               "match_method": "none"}

        if film_id:
            found = tmdb_find_by_imdb_id(film_id, api_key, cfg, rate_limit_seconds)
            if found["matched"]:
                rec.update(tmdb_id=found["tmdb_id"],
                           primary_genre=found["primary_genre"],
                           matched=True, match_method="imdb_id")

        if not rec["matched"] and title:
            alt = tmdb_lookup_movie(title, year, api_key, cfg, rate_limit_seconds)
            if alt["matched"]:
                rec.update(tmdb_id=alt["tmdb_id"],
                           primary_genre=alt["primary_genre"],
                           matched=True, match_method="title_year")

        recs.append(rec)

    return pd.DataFrame(recs, columns=[
        "film_id", "film", "year_int", "tmdb_id",
        "primary_genre", "matched", "match_method",
    ])
