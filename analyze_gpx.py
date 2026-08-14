#!/usr/bin/env python3
"""Compare two Leadville 100 GPX tracks and emit JSON for a map visualization."""
import json, math, re, sys

F2025 = "data/2025_race_recording.gpx"
F2026 = "data/2026_LT_100_RUN.gpx"
OUT = "course_data.json"

PT_RE = re.compile(r'<trkpt\s+lat="([-\d.]+)"\s+lon="([-\d.]+)"\s*>.*?<ele>([-\d.]+)</ele>', re.S)

def parse(path):
    with open(path) as f:
        txt = f.read()
    pts = [(float(a), float(b), float(c)) for a, b, c in PT_RE.findall(txt)]
    return pts

# equirectangular distance in meters, fine at this scale
LAT0 = 39.25
MPERDEG_LAT = 111132.0
MPERDEG_LON = 111320.0 * math.cos(math.radians(LAT0))

def dist_m(p, q):
    dy = (p[0] - q[0]) * MPERDEG_LAT
    dx = (p[1] - q[1]) * MPERDEG_LON
    return math.hypot(dx, dy)

def cumdist(pts):
    d = [0.0]
    for i in range(1, len(pts)):
        d.append(d[-1] + dist_m(pts[i - 1], pts[i]))
    return d

class Grid:
    """Bucket points into ~cell_deg cells for nearest-neighbor queries."""
    def __init__(self, pts, cell_deg=0.002):
        self.cell = cell_deg
        self.buckets = {}
        for p in pts:
            key = (int(p[0] / cell_deg), int(p[1] / cell_deg))
            self.buckets.setdefault(key, []).append(p)

    def min_dist(self, p, cap=500.0):
        ki, kj = int(p[0] / self.cell), int(p[1] / self.cell)
        best = cap
        for di in (-1, 0, 1):
            for dj in (-1, 0, 1):
                for q in self.buckets.get((ki + di, kj + dj), ()):
                    d = dist_m(p, q)
                    if d < best:
                        best = d
        return best

def densify(pts, max_gap=15.0):
    """Insert points so consecutive spacing <= max_gap meters (for grid completeness)."""
    out = [pts[0]]
    for i in range(1, len(pts)):
        p, q = pts[i - 1], pts[i]
        d = dist_m(p, q)
        if d > max_gap:
            n = int(d // max_gap)
            for k in range(1, n + 1):
                t = k / (n + 1)
                out.append((p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t, p[2] + (q[2] - p[2]) * t))
        out.append(q)
    return out

DIVERGE_M = 70.0      # farther than this from the other track = divergent
MIN_ZONE_M = 250.0    # runs shorter than this are GPS noise, not a course change

def classify(pts, other_grid):
    return [other_grid.min_dist(p) > DIVERGE_M for p in pts]

def smooth_flags(flags, dists, min_len=MIN_ZONE_M):
    """Drop divergent runs shorter than min_len; also fill shared gaps < 100m inside divergent runs."""
    flags = flags[:]
    # fill short shared gaps between divergent runs
    runs = to_runs(flags)
    for val, a, b in runs:
        if not val and dists[b] - dists[a] < 100.0 and 0 < a and b < len(flags) - 1:
            for i in range(a, b + 1):
                flags[i] = True
    # drop short divergent runs
    runs = to_runs(flags)
    for val, a, b in runs:
        if val and dists[b] - dists[a] < min_len:
            for i in range(a, b + 1):
                flags[i] = False
    return flags

def to_runs(flags):
    runs = []
    start = 0
    for i in range(1, len(flags) + 1):
        if i == len(flags) or flags[i] != flags[start]:
            runs.append((flags[start], start, i - 1))
            start = i
    return runs

def thin(pts, flags, min_gap=12.0):
    """Thin points but always keep flag transitions. Also returns kept original indices
    so true along-track distances survive thinning."""
    out, outf, idx = [pts[0]], [flags[0]], [0]
    for i in range(1, len(pts) - 1):
        if flags[i] != flags[i - 1] or flags[i] != flags[i + 1] or dist_m(out[-1], pts[i]) >= min_gap:
            out.append(pts[i]); outf.append(flags[i]); idx.append(i)
    out.append(pts[-1]); outf.append(flags[-1]); idx.append(len(pts) - 1)
    return out, outf, idx

def build_track(pts, flags, dists):
    """Point array [[lat,lon,mile,ele_ft],...] plus index-range segments split at
    divergence transitions and at the turnaround (outbound vs return leg)."""
    start = pts[0]
    turn = max(range(len(pts)), key=lambda i: dist_m(pts[i], start))
    arr = [[round(p[0], 5), round(p[1], 5), round(dists[i] / 1609.344, 3), round(p[2] * 3.28084)]
           for i, p in enumerate(pts)]
    segs = []
    a = 0
    for i in range(1, len(pts)):
        if flags[i] != flags[a] or i == turn or i == len(pts) - 1:
            segs.append({"a": a, "b": i, "div": flags[a], "leg": "out" if a < turn else "in"})
            a = i
    return {"pts": arr, "segs": segs, "turn_mile": round(dists[turn] / 1609.344, 2),
            "total_mile": round(dists[-1] / 1609.344, 2)}

def div_runs(flags, dists):
    """(d0, d1) meter ranges of divergent runs, for zone building."""
    return [(dists[a], dists[b]) for val, a, b in to_runs(flags) if val]

def landmarks(p25, d25):
    """Aid stations / features located from the 2025 activity track at known race miles."""
    def at_mile(mi):
        t = mi * 1609.344
        j = min(range(len(d25)), key=lambda i: abs(d25[i] - t))
        return (round(p25[j][0], 5), round(p25[j][1], 5))
    # Hope Pass = highest point of the outbound leg (miles 40-50)
    lo = min(range(len(d25)), key=lambda i: abs(d25[i] - 40 * 1609.344))
    hi = min(range(len(d25)), key=lambda i: abs(d25[i] - 50 * 1609.344))
    hp = max(range(lo, hi), key=lambda i: p25[i][2])
    return [
        {"name": "Start / Finish", "ll": at_mile(0)},
        {"name": "Turquoise Lake Dam", "ll": at_mile(5.3)},
        {"name": "Turquoise Lake north shore", "ll": at_mile(9.0)},
        {"name": "May Queen", "ll": at_mile(13.4)},
        {"name": "Sugarloaf / Powerline", "ll": at_mile(17.5)},
        {"name": "Outward Bound", "ll": at_mile(24.5)},
        {"name": "Half Pipe", "ll": at_mile(29.3)},
        {"name": "Twin Lakes", "ll": at_mile(37.9)},
        {"name": "Hope Pass", "ll": (round(p25[hp][0], 5), round(p25[hp][1], 5))},
        {"name": "Winfield (turnaround)", "ll": at_mile(50.5)},
    ]

def zones_from(pts, flags, dists, year, marks):
    out = []
    for val, a, b in to_runs(flags):
        if not val:
            continue
        seg = pts[a:b + 1]
        lats = [p[0] for p in seg]; lons = [p[1] for p in seg]
        clat = sum(lats) / len(lats); clon = sum(lons) / len(lons)
        near = min(marks, key=lambda m: dist_m((clat, clon), m["ll"]))
        out.append({
            "year": year,
            "bbox": [round(min(lats), 5), round(min(lons), 5), round(max(lats), 5), round(max(lons), 5)],
            "mile0": round(dists[a] / 1609.344, 2), "mile1": round(dists[b] / 1609.344, 2),
            "len_mi": round((dists[b] - dists[a]) / 1609.344, 2),
            "near": near["name"].split(" (")[0],
        })
    return out

def profile(pts, dists, step_m=80.0):
    """Sample (mile, ft) elevation profile every step_m."""
    out = []
    target = 0.0
    j = 0
    while target <= dists[-1]:
        while j < len(dists) - 1 and dists[j + 1] < target:
            j += 1
        # linear interp
        if j < len(dists) - 1 and dists[j + 1] > dists[j]:
            t = (target - dists[j]) / (dists[j + 1] - dists[j])
            ele = pts[j][2] + (pts[j + 1][2] - pts[j][2]) * t
        else:
            ele = pts[j][2]
        out.append([round(target / 1609.344, 3), round(ele * 3.28084, 1)])
        target += step_m
    return out

def gain_loss_ft(pts, thr=7.5):
    """Total ascent/descent in feet with symmetric hysteresis (moves < thr meters are
    treated as noise). thr=7.5 m calibrated so the 2026 route reproduces the official
    13,552 ft figure; the same method is applied to both years for comparability."""
    g = l = 0.0
    base = pts[0][2]
    for p in pts:
        d = p[2] - base
        if d >= thr:
            g += d; base = p[2]
        elif d <= -thr:
            l -= d; base = p[2]
    return g * 3.28084, l * 3.28084

# Official 2026 aid-station chart (leadvilleraceseries.com "2026 Run Course" tab,
# fetched 2026-08-14): 12 stations. Crew is allowed ONLY at Outward Bound, Pipeline
# and Twin Lakes Village (each visited twice). The site's drop-bag tab still lists
# the pre-fire locations (Mayqueen / Outward Bound / Half Pipe / Twin Lakes /
# Winfield) — mapped here where names match; Pipeline is "?" since the old list
# names Half Pipe, which is not a 2026 station.
AID_STOPS = [
    {"name": "Start (6th & Harrison)", "loc": "Start / Finish", "mile": 0.0, "cutoff": None, "crew": None, "drop": None},
    {"name": "Carter Summit", "loc": "Carter Summit", "leg": "out", "mile": 10.0, "cutoff": None, "crew": False, "drop": False},
    {"name": "Turquoise Lake Dam", "loc": "Turquoise Lake Dam", "leg": "out", "mile": 20.5, "cutoff": "10:15 AM", "crew": False, "drop": False},
    {"name": "Outward Bound", "loc": "Outward Bound", "leg": "out", "mile": 26.0, "cutoff": "11:15 AM", "crew": True, "drop": True},
    {"name": "Pipeline", "loc": "Pipeline", "leg": "out", "mile": 29.6, "cutoff": "12:45 PM", "crew": True, "drop": "?"},
    {"name": "Twin Lakes Village", "loc": "Twin Lakes", "leg": "out", "mile": 40.5, "cutoff": "2:15 PM", "crew": True, "drop": True},
    {"name": "Hope Pass", "loc": "Hope Pass", "leg": "out", "mile": 45.6, "cutoff": "4:45 PM", "crew": False, "drop": False},
    {"name": "Winfield", "loc": "Winfield", "leg": "turn", "mile": 52.3, "cutoff": "6:50 PM", "crew": False, "drop": True},
    {"name": "Hope Pass", "loc": "Hope Pass", "leg": "in", "mile": 59.1, "cutoff": None, "crew": False, "drop": False},
    {"name": "Twin Lakes Village", "loc": "Twin Lakes", "leg": "in", "mile": 64.2, "cutoff": "11:00 PM", "crew": True, "drop": True},
    {"name": "Pipeline", "loc": "Pipeline", "leg": "in", "mile": 75.1, "cutoff": "2:00 AM Sun", "crew": True, "drop": "?"},
    {"name": "Outward Bound", "loc": "Outward Bound", "leg": "in", "mile": 78.7, "cutoff": "3:45 AM Sun", "crew": True, "drop": True},
    {"name": "Turquoise Lake Dam", "loc": "Turquoise Lake Dam", "leg": "in", "mile": 84.2, "cutoff": "5:30 AM Sun", "crew": False, "drop": False},
    {"name": "Finish (6th & Harrison)", "loc": "Start / Finish", "mile": 100.0, "cutoff": "10:00 AM Sun (30 h)", "crew": None, "drop": None},
]

def aid_data(p26, dist26, marks):
    """Locate each official 2026 stop at its PHYSICAL location on the 2026 route
    (the chart's miles don't line up with GPX mileage), then compute between-stop
    stats from the GPX. Chart miles/cutoffs stay as the displayed planning numbers."""
    turn = max(range(len(p26)), key=lambda i: dist_m(p26[i], p26[0]))
    lm = {m["name"]: m["ll"] for m in marks}
    anchors = {
        "Turquoise Lake Dam": lm["Turquoise Lake Dam"],
        "Outward Bound": lm["Outward Bound"],
        "Twin Lakes": lm["Twin Lakes"],
        "Winfield": lm["Winfield (turnaround)"],
    }
    def nearest(ll, lo, hi):
        return min(range(lo, hi), key=lambda i: dist_m(p26[i], ll))
    # Hope Pass aid ("Hopeless") sits at treeline ~11,900 ft on the north approach,
    # below the summit — locate it by elevation on each leg's climb
    summit_out = max(range(turn), key=lambda i: p26[i][2])
    summit_in = max(range(turn, len(p26)), key=lambda i: p26[i][2])
    HOPELESS_M = 3628.0  # ~11,900 ft
    hope_out = min(range(summit_out - 400 if summit_out > 400 else 0, summit_out),
                   key=lambda i: abs(p26[i][2] - HOPELESS_M))
    hope_in = min(range(summit_in, min(summit_in + 400, len(p26))),
                  key=lambda i: abs(p26[i][2] - HOPELESS_M))
    def snap(s):
        """Physical location on the correct leg for anchored stops; None for stops
        without an independent anchor (resolved by chart-mile interpolation below)."""
        loc, leg = s["loc"], s.get("leg", "out" if s["mile"] == 0 else "in")
        if loc == "Start / Finish":
            return (0 if s["mile"] == 0 else len(p26) - 1), False
        if loc == "Hope Pass":
            return (hope_out if leg == "out" else hope_in), False
        if leg == "turn":
            return turn, False
        if loc not in anchors:
            return None, False
        lo, hi = (0, turn) if leg == "out" else (turn, len(p26))
        j = nearest(anchors[loc], lo, hi)
        if dist_m(p26[j], anchors[loc]) > 400:
            return None, True  # chart lists a stop the route doesn't visit; interpolate
        return j, False

    snapped = [snap(s) for s in AID_STOPS]
    # resolve anchor-less stops (Carter Summit, Pipeline) by interpolating GPX
    # distance between the surrounding snapped stops' (chart mile, gpx meters) pairs
    ctrl = [(AID_STOPS[k]["mile"], dist26[snapped[k][0]]) for k in range(len(AID_STOPS)) if snapped[k][0] is not None]
    def interp_idx(mile):
        for (m0, d0), (m1, d1) in zip(ctrl, ctrl[1:]):
            if m0 <= mile <= m1:
                t = d0 + (d1 - d0) * (mile - m0) / (m1 - m0)
                return min(range(len(p26)), key=lambda i: abs(dist26[i] - t))
        return min(range(len(p26)), key=lambda i: abs(dist26[i] - mile / 100.0 * dist26[-1]))

    stations = {}
    seg_idx = []
    for s, (j, approx) in zip(AID_STOPS, snapped):
        if j is None:
            j = interp_idx(s["mile"])
        seg_idx.append(j)
        if s["loc"] == "Start / Finish":
            continue  # start/finish already a landmark
        st = stations.setdefault(s["loc"], {
            "name": s["name"], "ll": [round(p26[j][0], 5), round(p26[j][1], 5)],
            "ele": round(p26[j][2] * 3.28084), "visits": [], "drop": s["drop"],
        })
        st["visits"].append({"leg": s.get("leg"), "mile": s["mile"], "cutoff": s["cutoff"],
                             "crew": s["crew"], "approx": approx})
    approx_flags = [a for (_, a) in snapped]
    segments = []
    for k in range(1, len(AID_STOPS)):
        a, b = seg_idx[k - 1], seg_idx[k]
        g, l = gain_loss_ft(p26[a:b + 1])
        s = AID_STOPS[k]
        segments.append({
            "to": s["name"], "leg": s.get("leg"), "mile": s["mile"],
            "dist": round(s["mile"] - AID_STOPS[k - 1]["mile"], 1),
            "gpx_dist": round((dist26[b] - dist26[a]) / 1609.344, 1),
            "gpx_mile": round(dist26[b] / 1609.344, 1),
            "gain": round(g), "loss": round(l),
            "cutoff": s["cutoff"], "crew": s["crew"], "drop": s["drop"],
            "ele": round(p26[b][2] * 3.28084),
            "approx": approx_flags[k] or approx_flags[k - 1],
        })
    return {"stations": list(stations.values()), "segments": segments}

def main():
    p25 = parse(F2025)
    p26 = parse(F2026)
    print(f"parsed 2025={len(p25)} 2026={len(p26)}")

    d26_dense = densify(p26)
    d25_dense = densify(p25)
    g26 = Grid(d26_dense)
    g25 = Grid(d25_dense)

    dist25 = cumdist(p25)
    dist26 = cumdist(p26)

    f25 = smooth_flags(classify(p25, g26), dist25)
    f26 = smooth_flags(classify(p26, g25), dist26)

    # thin for output; distances at kept points are the ORIGINAL along-track distances
    t25, tf25, ti25 = thin(p25, f25)
    t26, tf26, ti26 = thin(p26, f26)
    td25 = [dist25[i] for i in ti25]
    td26 = [dist26[i] for i in ti26]

    trk25 = build_track(t25, tf25, td25)
    trk26 = build_track(t26, tf26, td26)

    marks = landmarks(p25, dist25)
    zones = sorted(zones_from(t25, tf25, td25, 2025, marks) + zones_from(t26, tf26, td26, 2026, marks),
                   key=lambda z: z["mile0"])

    div25_mi = sum(d1 - d0 for d0, d1 in div_runs(tf25, td25)) / 1609.344
    div26_mi = sum(d1 - d0 for d0, d1 in div_runs(tf26, td26)) / 1609.344

    g25, l25 = gain_loss_ft(p25)
    g26, l26 = gain_loss_ft(p26)
    data = {
        "stats": {
            "dist2025_mi": dist25[-1] / 1609.344,
            "dist2026_mi": dist26[-1] / 1609.344,
            "gain2025_ft": g25, "loss2025_ft": l25,
            "gain2026_ft": g26, "loss2026_ft": l26,
            "div2025_mi": div25_mi,
            "div2026_mi": div26_mi,
        },
        "aid": aid_data(p26, dist26, marks),
        "t2025": trk25,
        "t2026": trk26,
        "zones": zones,
        "landmarks": marks,
        "profile2025": profile(p25, dist25),
        "profile2026": profile(p26, dist26),
    }
    with open(OUT, "w") as f:
        json.dump(data, f, separators=(",", ":"))
    print(f"2025: {dist25[-1]/1609.344:.1f} mi, gain {g25:.0f}/loss {l25:.0f} ft, divergent {div25_mi:.1f} mi, "
          f"{len(trk25['pts'])} pts, {len(trk25['segs'])} segs, turn mi {trk25['turn_mile']}")
    print(f"2026: {dist26[-1]/1609.344:.1f} mi, gain {g26:.0f}/loss {l26:.0f} ft, divergent {div26_mi:.1f} mi, "
          f"{len(trk26['pts'])} pts, {len(trk26['segs'])} segs, turn mi {trk26['turn_mile']}")
    print(f"zones: {len(zones)}")
    for z in zones:
        print("  ", {k: (round(v, 2) if isinstance(v, float) else v) for k, v in z.items() if k != "bbox"})
    import os
    print("json bytes:", os.path.getsize(OUT))

if __name__ == "__main__":
    main()
