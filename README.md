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
| `course_common.py` | Shared provenance checks, waypoint building, and GPX writing |
| `make_course_gpx.py` | Builds the default download → `leadville-100-2026-official.gpx` |
| `make_baro_gpx.py` | Builds the measured-elevation variant → `leadville-100-2026-measured-elevation.gpx` |
| `leadville-100-2026-official.gpx` | Default download: official geometry and elevation |
| `leadville-100-2026-measured-elevation.gpx` | Same geometry, barometric elevation on shared ground |

## Rebuilding

```sh
# optional, only if the GPX inputs change (place them under data/, see .gitignore)
python3 analyze_gpx.py
python3 build.py
```

The raw GPX inputs (a personal 2025 race recording from Strava and the official
2026 RideWithGPS route) are intentionally not committed.

## The downloadable GPX

`leadville-100-2026-official.gpx` is built by `make_course_gpx.py` from the **official RideWithGPS
export of route 56633050** as the single source of truth. Provenance is checked on every
build: the script exits unless both exports carry `2026` in the name and the expected
route id, and it reports the export timestamp.

- **Geometry and elevation** come from the GPX Track export (4,858 points, 99.843 mi).
  Coordinate and elevation strings are copied through byte-for-byte, so nothing is
  rounded or simplified. RideWithGPS itself exports 5–6 decimal places (~1 m).
- **Elevation is RideWithGPS DEM.** A drawn route has no barometric data, so DEM is the
  only elevation the source of truth contains.
- **89 cue waypoints** take position from the GPX Route export and text from the cuesheet
  CSV. Waypoint elevation is read off the track, never the CSV, per source priority.
- **7 aid-station waypoints** (12 visits) come from the race site chart, because the
  RideWithGPS export contains no POIs at all. Each says so in its own `<desc>`.

Known source disagreements, flagged rather than resolved:

| | |
|---|---|
| Track total | 99.843 mi |
| Cuesheet total | 99.970 mi (0.127 mi / 669 ft longer) |
| Published | 100.00 mi — track is 827 ft short |
| Gain at ±7.5 m | 13,550 ft vs published 13,552 ft |
| Cuesheet `Start` row | lists elevation 0 ft; the track's 10,144 ft is used |

Gain is threshold-dependent, not a pure property of the data: ±0 m gives 16,688 ft,
±5 m gives 14,364 ft, ±7.5 m gives 13,550 ft, ±15 m gives 12,824 ft. The ±7.5 m figure
matching the published number is calibration, not independent confirmation.

### The measured-elevation variant

`leadville-100-2026-measured-elevation.gpx` is the same file with one variable changed. Geometry,
distance, waypoints, and provenance are byte-for-byte identical to the default; only the
elevation stream differs. Barometric readings from the 2025 race recording replace the DEM
across the **68.5 mi (68.6%)** the two courses share, matched within 25 m; ground new in
2026 keeps DEM, ramped at each of the 16 seams so no step appears. Loop closure is forced
to 0 ft.

It reports **13,405 ft** of gain against the DEM's 13,550 ft, and stays below the DEM at
every filtering threshold:

| Threshold | Official | Measured | Difference |
|---|---|---|---|
| ±0 m | 16,688 ft | 15,855 ft | −833 ft |
| ±5 m | 14,364 ft | 13,809 ft | −555 ft |
| ±7.5 m | 13,550 ft | 13,405 ft | **−144 ft** |
| ±10 m | 13,306 ft | 13,094 ft | −212 ft |
| ±15 m | 12,824 ft | 12,483 ft | −341 ft |

Agreement is close on the climbs and loose on the flats: the seven legs with over 1,000 ft
of gain match the official figures within 5.7%, while legs under 200 ft of gain can differ
by tens of feet in either direction (the 25 ft leg into Outward Bound reads 0 ft measured).

Two corrections are applied before any lookup, and both are required:

1. **De-drift the recording.** It starts and finishes at the same intersection, so the
   19.7 ft of elevation change across it is drift, spread out linearly.
2. **Lock each lookup to one 2025 pass.** Much of the course runs out and back, so the two
   2025 passes sit within metres of each other but were recorded hours apart. Choosing the
   spatially nearest point alone flips between them — 172 times on the Turquoise Lake leg
   alone — and every flip injects that drift as climb that never happened. A pass is held
   until it stops matching for a sustained stretch; the fixed build switches 10 times total.

Without those two fixes the same build reported 14,569 ft and claimed the 2026 course
climbed 875 ft *more* than 2025. That was an artifact, not a finding.

Rebuild with `python3 make_course_gpx.py` and `python3 make_baro_gpx.py` (both need the
raw inputs under `data/`).

## Data notes

- Elevation gain/loss uses symmetric ±7.5 m hysteresis, calibrated to reproduce the
  official 2026 figure (13,552 ft). The same *threshold* is applied to both years, but not
  the same elevation *source*, and the source dominates. The stat tile therefore has an
  **Official / Measured** toggle for 2026:

  | View | 2025 | 2026 | Comparable? |
  |---|---|---|---|
  | Official | 13,694 ft (barometric) | 13,550 ft (terrain model) | **No** — two different kinds of measurement |
  | Measured | 13,694 ft (barometric) | 13,405 ft (barometric) | Yes — 2026 climbs ~290 ft less |

  The 2025 column is barometric in both views, because a barometer is the only record of
  that run. Both views now agree on direction: the 2026 course climbs slightly less than
  2025, by 144 ft on the terrain model and about 290 ft measured. De-drifting the 2025
  recording moves its own total by only 11 ft (13,694 → 13,705 at matched sampling), so it
  is left as published. Both 2026 figures are reproducible from the matching GPX download.
- Aid-station miles, cutoffs, and crew info come from the 2026 Run Course tab on
  leadvilleraceseries.com (fetched 2026-08-14). The site's drop-bag tab predates the
  reroute; drop-bag info is mapped where station names match and flagged "?" otherwise.
- Map tiles: CARTO / OpenStreetMap (network required when viewing).
