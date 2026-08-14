# Leadville Trail 100 Run — 2025 vs 2026 Course Comparison

An interactive single-page visualization comparing the 2025 Leadville Trail 100 Run
course with the rerouted 2026 course (the 2026 edition avoids the Willow Fire burn
areas — Hagerman Pass Road, Sugarloaf, and Powerline are out; the course instead
loops Turquoise Lake outbound over Carter Summit and returns via the east side).

**The page** (`index.html`) shows:

- Both courses overlaid on a map — gray where shared, blue for 2025-only, orange
  for 2026-only — with direction arrows, solid (outbound) vs dashed (return) legs,
  and year/leg filter toggles
- Right-click any line for mile, elevation, and grade at that point
- The 2026 aid stations (official chart: miles, cutoffs, crew access, drop bags)
  as map markers and a leg-by-leg table with distance, gain, and loss per segment
- Overlaid elevation profiles for both years

## Structure

| File | Purpose |
|---|---|
| `index.html` | Built, self-contained page (data inlined) — this is what gets deployed |
| `template.html` | Page source with a `/*__DATA__*/` placeholder |
| `analyze_gpx.py` | Parses the two GPX files, computes divergence/zones/aid data → `course_data.json` |
| `build.py` | Injects `course_data.json` into the template → `index.html` |
| `course_data.json` | Derived course data (committed so the page builds without the raw GPX inputs) |

## Rebuilding

```sh
# optional, only if the GPX inputs change (place them under data/, see .gitignore)
python3 analyze_gpx.py
python3 build.py
```

The raw GPX inputs (a personal 2025 race recording from Strava and the official
2026 RideWithGPS route) are intentionally not committed.

## Data notes

- Elevation gain/loss uses symmetric ±7.5 m hysteresis, calibrated to reproduce the
  official 2026 figure (13,552 ft); the same method is applied to both years.
- Aid-station miles, cutoffs, and crew info come from the 2026 Run Course tab on
  leadvilleraceseries.com (fetched 2026-08-14). The site's drop-bag tab predates the
  reroute; drop-bag info is mapped where station names match and flagged "?" otherwise.
- Map tiles: CARTO / OpenStreetMap (network required when viewing).
