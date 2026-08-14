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

MATCH_M = 25.0        # how close a recording point must be to lend its elevation
RELOCK_AFTER = 10     # consecutive misses before the locked recording leg may change


def main():
    raw, pts, dist, meta = cc.load_track()
    total_mi = dist[-1] / 1609.344
    dem = [p[2] for p in pts]
    dem_gain, _ = ag.gain_loss_ft(pts)

    roche = ag.parse(cc.ROCHE)
    print(f"\n2025 recording: {len(roche)} points, "
          f"{ag.cumdist(roche)[-1]/1609.344:.2f} mi, barometric elevation")

    # step one, remove the recording's own barometric drift.
    # it starts and finishes at the same intersection, so any elevation change over the run is drift.
    # spreading that out first shrinks the disagreement between its outbound and return passes.
    rdist = ag.cumdist(roche)
    drift = roche[-1][2] - roche[0][2]
    roche = [(p[0], p[1], p[2] - drift * rdist[i] / (rdist[-1] or 1.0))
             for i, p in enumerate(roche)]
    print(f"  removed {drift*3.28084:+.1f} ft of barometric drift across the recording")
    rturn = max(range(len(roche)), key=lambda i: ag.dist_m(roche[i], roche[0]))

    # step two, look up elevation with the recording leg locked.
    # much of the course is run out and back, so both 2025 passes sit within metres of each other.
    # picking the spatially nearest point alone flips between passes recorded hours apart.
    # each flip injects the drift between them as a fake step, and those steps read as climb.
    # so a leg is held until it stops matching for a sustained stretch.
    ridx = {}
    for i, p in enumerate(roche):
        ridx.setdefault((int(p[0] / 0.002), int(p[1] / 0.002)), []).append(i)

    def nearest(p, leg):
        ki, kj = int(p[0] / 0.002), int(p[1] / 0.002)
        best, bi = MATCH_M, None
        for di in (-1, 0, 1):
            for dj in (-1, 0, 1):
                for i in ridx.get((ki + di, kj + dj), ()):
                    if leg == "out" and i >= rturn:
                        continue
                    if leg == "in" and i < rturn:
                        continue
                    d = ag.dist_m(p, roche[i])
                    if d < best:
                        best, bi = d, i
        return bi, best

    baro = []
    lock = None
    misses = 0
    switches = 0
    for p in pts:
        hit = None
        if lock is not None:
            i, _ = nearest(p, lock)
            if i is not None:
                hit, misses = i, 0
            else:
                misses += 1
                if misses > RELOCK_AFTER:
                    lock = None
        if lock is None:
            # relock to whichever pass is actually closer here.
            cands = [(d, i, lg) for lg in ("out", "in")
                     for i, d in [nearest(p, lg)] if i is not None]
            if cands:
                _, i, lg = min(cands)
                if lock != lg:
                    switches += 1
                lock, hit, misses = lg, i, 0
        baro.append(roche[hit][2] if hit is not None else None)
    print(f"  leg locked lookup switched pass {switches} times, "
          f"instead of flipping at every point")

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

    # aid station stats on the same boundaries, so the table can swap elevation without moving legs.
    # station locating still runs on the dem, which is what keeps the boundaries fixed.
    marks = ag.landmarks(roche, ag.cumdist(roche))
    a_off = ag.aid_data(pts, dist, marks)
    a_meas = ag.aid_data(pts, dist, marks, stats_ele=ele)
    assert [s["gpx_mile"] for s in a_off["segments"]] == [s["gpx_mile"] for s in a_meas["segments"]], \
        "aid segment boundaries moved, the two views would not be comparable"
    aid_measured = {
        "segments": [{"gain": s["gain"], "loss": s["loss"], "ele": s["ele"]} for s in a_meas["segments"]],
        "stations": [{"ele": s["ele"]} for s in a_meas["stations"]],
    }
    flat = [(s["to"], o["gain"], s["gain"]) for o, s in zip(a_off["segments"], a_meas["segments"])
            if o["gain"] and abs(s["gain"] - o["gain"]) / o["gain"] > 0.5]
    print(f"\naid stats: {len(a_meas['segments'])} segments, {len(a_meas['stations'])} stations")
    print(f"  {len(flat)} flat segments where barometric noise moves gain by over 50 percent:")
    for name, o, m in flat:
        print(f"    {name:<26} official {o:>5} ft, measured {m:>5} ft")

    wpts, csv_total = cc.build_waypoints(pts, dist, report=False)
    print(f"\nwaypoints: {len(wpts)} total, identical to the default file")
    cc.accuracy_report(total_mi, gain, csv_total, "barometric correction")

    rows = [(la, lo, f"{ele[k]:.1f}") for k, (la, lo, _) in enumerate(raw)]
    desc = (f"Official 2026 course with corrected elevation. Geometry is the RideWithGPS GPX "
            f"Track export of route {cc.ROUTE_ID} ({meta[1]}), unchanged. Elevation is "
            f"barometric, taken from a 2025 race recording across the {covered_mi:.1f} mi the two "
            f"courses share; ground new in 2026 keeps RideWithGPS DEM, ramped at the seams. "
            f"Measures {total_mi:.2f} mi with {gain:.0f} ft of gain, against {dem_gain:.0f} ft "
            f"for the DEM. The recording's own barometric drift is removed first, and each lookup is "
            f"locked to a single 2025 pass, so out-and-back sections cannot mix readings taken hours "
            f"apart. Use leadville-100-2026-official.gpx if you need official-only provenance.")
    cc.write_gpx(OUT, desc, meta, wpts, rows, lambda i: ele[i])

    with open(STATS, "w") as f:
        json.dump({
            "threshold_m": 7.5,
            "official": {"gain_ft": round(dem_gain), "loss_ft": round(ag.gain_loss_ft(pts)[1])},
            "measured": {"gain_ft": round(gain), "loss_ft": round(loss),
                         "coverage_mi": round(covered_mi, 1),
                         "coverage_pct": round(covered_mi / total_mi * 100, 1),
                         # same sampling as analyze_gpx profile2026, so the chart can swap series.
                         "profile": ag.profile(corrected, dist),
                         # same segment boundaries as course_data, only the elevation differs.
                         "aid": aid_measured},
        }, f, separators=(",", ":"))
    print(f"wrote {STATS}")


if __name__ == "__main__":
    main()
