# oscars-award-wins — Dataset Codebook
Generated: 2026-10-08

## Columns

### `ceremony`
- **Type**: `int64`
- **Non-null**: 3,515 / 3,515 (100.0%)
- **Description**: Academy Awards ceremony ordinal (1 = 1927/28 ... 98 = 2025).

### `year_int`
- **Type**: `int32`
- **Non-null**: 3,515 / 3,515 (100.0%)
- **Description**: Ceremony year as a 4-digit integer. For the earliest slash-span years (e.g. '1927/28') this is the latter year (1928).

### `decade`
- **Type**: `int32`
- **Non-null**: 3,515 / 3,515 (100.0%)
- **Description**: Decade the ceremony falls in, as the starting year (e.g. 1928 -> 1920, 1999 -> 1990).

### `class`
- **Type**: `str`
- **Non-null**: 3,515 / 3,515 (100.0%)
- **Description**: Broad award grouping (Title, Acting, Directing, Writing, Production, Music, SciTech, Special).

### `competitive`
- **Type**: `bool`
- **Non-null**: 3,515 / 3,515 (100.0%)
- **Description**: True for competitive classes; False for SciTech and Special (non-competitive honorary/technical awards where every entry is a recipient).

### `canonical_category`
- **Type**: `str`
- **Non-null**: 3,515 / 3,515 (100.0%)
- **Description**: Normalized category name that collapses the many wording changes of the same award over the years, so a category reads as one continuous series.

### `category`
- **Type**: `str`
- **Non-null**: 3,515 / 3,515 (100.0%)
- **Description**: Exact category wording as published by the Academy for that ceremony.

### `film`
- **Type**: `str`
- **Non-null**: 2,261 / 3,515 (64.3%)
- **Description**: Film associated with the win (may be empty for some honorary/non-film categories).

### `name`
- **Type**: `str`
- **Non-null**: 2,314 / 3,515 (65.8%)
- **Description**: Person(s) or entity credited with the win (may be empty for some categories).

### `film_id`
- **Type**: `str`
- **Non-null**: 2,261 / 3,515 (64.3%)
- **Description**: IMDb title identifier (e.g. tt0019071) for the winning film; the first id when an award covers multiple films (pipe-separated in the source).

### `primary_genre`
- **Type**: `str`
- **Non-null**: 1,122 / 3,515 (31.9%)
- **Description**: Primary film genre (TMDB genres[0]), looked up by IMDb id; populated for MAJOR-award films only (Best Picture, Directing, the four acting awards, and the two screenplay awards) and NULL for all other wins. Source: TMDB (this product uses the TMDB API but is not endorsed or certified by TMDB).

## Notes

Source: DLu/oscar_data (David V. Lu), oscars.csv — Academy Awards nominations +
winners, compiled from the AMPAS Awards Database (https://awardsdatabase.oscars.org/)
and IMDb. License: BSD 2-Clause for the compilation; underlying facts from AMPAS/IMDb.
Film genre is from The Movie Database (TMDB): this product uses the TMDB API but is not
endorsed or certified by TMDB; primary_genre = TMDB genres[0], populated for major-award
films only. Scope: WINS ONLY (one row per winning award), 1st ceremony (1927/28) through
the 98th (2025). A win = one row with Winner=True; a tie yields two winner rows. SciTech
and Special are non-competitive (every entry a recipient) and are flagged competitive=False.
This is a fun-tier pop-culture dataset; see SOURCES.md.
