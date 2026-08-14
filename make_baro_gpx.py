#!/usr/bin/env python3
# builds the alternate download with corrected elevation.
# geometry stays exactly the official ridewithgps track, so distance and provenance do not move.
# only the elevation stream changes, so this file and the default differ in one variable.
#
# the official elevation is dem sampled along a drawn line.
# the 2025 race recording carries barometric elevation from a device that was actually there.
# on shared ground the dem reads lower, so the recording replaces it point by point.
# ground new in 2026 has no recording, so it keeps dem, ramped at the seams to avoid a step.
import json

import analyze_gpx as ag
import course_common as cc

OUT = "leadville-100-2026-measured-elevation.gpx"
# the page reads this so the two gain figures are never hardcoded in the template.
STATS = "elevation_sources.json"

MATCH_M = 25.0   # how close a recording point must be to lend its elevation


def main():
    raw, pts, dist, meta = cc.load_track()
    total_mi = dist[-1] / 1609.344
    dem = [p[2] for p in pts]
    dem_gain, _ = ag.gain_loss_ft(pts)

    roche = ag.parse(cc.ROCHE)
    print(f"\n2025 recording: {len(roche)} points, "
          f"{ag.cumdist(roche)[-1]/1609.344:.2f} mi, barometric elevation")

    # nearest recording elevation for every official track point.
    ridx = {}
    for i, p in enumerate(roche):
        ridx.setdefault((int(p[0] / 0.002), int(p[1] / 0.002)), []).append(i)

    baro = []
    for p in pts:
        ki, kj = int(p[0] / 0.002), int(p[1] / 0.002)
        best, be = MATCH_M, None
        for di in (-1, 0, 1):
            for dj in (-1, 0, 1):
                for i in ridx.get((ki + di, kj + dj), ()):
                    d = ag.dist_m(p, roche[i])
                    if d < best:
                        best, be = d, roche[i][2]
        baro.append(be)

    have = sum(1 for b in baro if b is not None)
    covered_mi = 0.0
    for i in range(1, len(pts)):
        if baro[i] is not None and baro[i - 1] is not None:
            covered_mi += ag.dist_m(pts[i - 1], pts[i]) / 1609.344
    print(f"  matched {have} of {len(pts)} track points within {MATCH_M:.0f} m")
    print(f"  covers {covered_mi:.2f} mi of {total_mi:.2f} mi "
          f"({covered_mi/total_mi*100:.1f}% of the course)")

    diffs = [(baro[i] - dem[i]) for i in range(len(pts)) if baro[i] is not None]
    ds = sorted(diffs)
    n = len(ds)
    print(f"  baro minus dem on matched ground: mean {sum(ds)/n:+.1f} m, "
          f"median {ds[n//2]:+.1f} m, p5 {ds[int(n*.05)]:+.1f} m, p95 {ds[int(n*.95)]:+.1f} m")

    # build the corrected stream. dem runs are ramped so each seam meets the baro data.
    ele = list(baro)
    ramps = 0
    i = 0
    while i < len(ele):
        if ele[i] is not None:
            i += 1
            continue
        j = i
        while j < len(ele) and ele[j] is None:
            j += 1
        d0 = (ele[i - 1] - dem[i - 1]) if i > 0 else None
        d1 = (ele[j] - dem[j]) if j < len(ele) else None
        if d0 is None and d1 is None:
            d0 = d1 = 0.0
        elif d0 is None:
            d0 = d1
        elif d1 is None:
            d1 = d0
        span = (dist[j - 1] - dist[i]) or 1.0
        for k in range(i, j):
            t = (dist[k] - dist[i]) / span
            ele[k] = dem[k] + d0 + (d1 - d0) * t
        ramps += 1
        i = j
    print(f"  ramped {ramps} dem runs to meet the barometric seams")

    # start and finish are the same intersection, so remove any residual drift.
    resid = ele[-1] - ele[0]
    for k in range(len(ele)):
        ele[k] -= resid * dist[k] / (dist[-1] or 1.0)
    print(f"  closed loop elevation, removed {resid*3.28084:+.1f} ft of drift")

    # round first, to one decimal, exactly as the file is written.
    # otherwise the page would quote a gain nobody can reproduce from the download.
    ele = [round(e, 1) for e in ele]
    corrected = [(pts[i][0], pts[i][1], ele[i]) for i in range(len(pts))]
    gain, loss = ag.gain_loss_ft(corrected)
    print(f"\ncorrected: {total_mi:.3f} mi, gain {gain:.0f} ft, loss {loss:.0f} ft")
    print(f"  official dem gain was {dem_gain:.0f} ft, difference {gain-dem_gain:+.0f} ft")

    wpts, csv_total = cc.build_waypoints(pts, dist, report=False)
    print(f"\nwaypoints: {len(wpts)} total, identical to the default file")
    cc.accuracy_report(total_mi, gain, csv_total, "barometric correction")

    rows = [(la, lo, f"{ele[k]:.1f}") for k, (la, lo, _) in enumerate(raw)]
    desc = (f"Official 2026 course with corrected elevation. Geometry is the RideWithGPS GPX "
            f"Track export of route {cc.ROUTE_ID} ({meta[1]}), unchanged. Elevation is "
            f"barometric, taken from a 2025 race recording across the {covered_mi:.1f} mi the two "
            f"courses share; ground new in 2026 keeps RideWithGPS DEM, ramped at the seams. "
            f"Measures {total_mi:.2f} mi with {gain:.0f} ft of gain, against {dem_gain:.0f} ft "
            f"for the DEM. That difference is largely barometric noise, so treat the gain figure "
            f"with caution. Use leadville-100-2026-official.gpx if you need official-only provenance.")
    cc.write_gpx(OUT, desc, meta, wpts, rows, lambda i: ele[i])

    with open(STATS, "w") as f:
        json.dump({
            "threshold_m": 7.5,
            "official": {"gain_ft": round(dem_gain), "loss_ft": round(ag.gain_loss_ft(pts)[1])},
            "measured": {"gain_ft": round(gain), "loss_ft": round(loss),
                         "coverage_mi": round(covered_mi, 1),
                         "coverage_pct": round(covered_mi / total_mi * 100, 1)},
        }, f, separators=(",", ":"))
    print(f"wrote {STATS}")


if __name__ == "__main__":
    main()
