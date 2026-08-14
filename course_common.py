#!/usr/bin/env python3
# shared pieces for the two course gpx builds.
# both files carry identical geometry and identical waypoints.
# they differ only in the elevation stream, so a reader can compare them directly.
import bisect
import csv
import json
import re
import sys

import analyze_gpx as ag

TRACK = "data/2026_LT_100_RUN.gpx"
ROUTE = "data/2026_LT_100_RUN_cues.gpx"
SHEET = "data/cuesheet.csv"
COURSE = "course_data.json"
ROCHE = "data/2025_race_recording.gpx"

ROUTE_ID = "56633050"
EXPECT_YEAR = "2026"

# thresholds, chosen because the brackets in the spec were left blank.
ELE_FLAG_FT = 10.0
GAIN_TOL_FT = 250.0
DIST_TOL_MI = 0.20
PUB_DIST_MI = 100.00
PUB_GAIN_FT = 13552.0

TRKPT_RE = re.compile(
    r'<trkpt\s+lat="([-\d.]+)"\s+lon="([-\d.]+)"\s*>\s*<ele>([-\d.]+)</ele>', re.S)
RTEPT_RE = re.compile(
    r'<rtept lat="([-\d.]+)" lon="([-\d.]+)">\s*<name>([^<]*)</name>\s*<cmt>([^<]*)</cmt>', re.S)
META_RE = re.compile(r"<metadata>(.*?)</metadata>", re.S)


def xml_escape(s):
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
             .replace('"', "&quot;"))


def check_provenance(path, quiet=False):
    # refuse to build from a cached or prior year export.
    txt = open(path).read()
    m = META_RE.search(txt)
    block = m.group(1) if m else ""
    name = re.search(r"<name>([^<]*)</name>", block)
    time = re.search(r"<time>([^<]*)</time>", block)
    link = re.search(r'href="([^"]*)"', block)
    name = name.group(1) if name else ""
    time = time.group(1) if time else ""
    link = link.group(1) if link else ""
    if not quiet:
        print(f"  {path}")
        print(f"    name {name!r}, exported {time}, route {link}")
    if EXPECT_YEAR not in name or ROUTE_ID not in link:
        sys.exit(f"provenance check failed for {path}: expected {EXPECT_YEAR} and route {ROUTE_ID}")
    return name, time, link


def load_track(quiet=False):
    # returns the original strings alongside floats, so output can stay byte identical.
    if not quiet:
        print("provenance:")
    t_meta = check_provenance(TRACK, quiet)
    r_meta = check_provenance(ROUTE, quiet)
    if not quiet:
        if t_meta[1:] != r_meta[1:]:
            print("  FLAG track and route exports disagree on timestamp or route id")
        else:
            print("  both exports agree on route id and export timestamp")
    raw = TRKPT_RE.findall(open(TRACK).read())
    pts = [(float(a), float(b), float(c)) for a, b, c in raw]
    return raw, pts, ag.cumdist(pts), t_meta


def cell_index(pts, cell=0.002):
    idx = {}
    for i, p in enumerate(pts):
        idx.setdefault((int(p[0] / cell), int(p[1] / cell)), []).append(i)
    return idx


def build_waypoints(pts, dist, report=True):
    """89 cue waypoints from the official exports, plus aid station pois from the race chart."""
    total_mi = dist[-1] / 1609.344
    cues = RTEPT_RE.findall(open(ROUTE).read())
    rows = list(csv.DictReader(open(SHEET)))
    if report:
        print(f"\ncues: {len(cues)} in the route export, {len(rows)} in the cuesheet")
    if len(cues) != len(rows):
        sys.exit("cue counts differ, pairing by order is unsafe")

    idx = cell_index(pts)

    def nearest_i(ll):
        ki, kj = int(ll[0] / 0.002), int(ll[1] / 0.002)
        best, bi = 1e9, None
        for di in (-1, 0, 1):
            for dj in (-1, 0, 1):
                for i in idx.get((ki + di, kj + dj), ()):
                    d = ag.dist_m(pts[i], ll)
                    if d < best:
                        best, bi = d, i
        return bi, best

    def nearest_i_at(ll, target_m, floor_i=0, window_m=1600.0):
        # the course is an out and back and it braids, so a coordinate alone is ambiguous.
        # the cuesheet mileage says which pass we are on, so only search near that distance.
        # cues are in course order, so never look behind the previous cue either.
        # that is what separates the two identical u turn cues at winfield.
        lo = max(bisect.bisect_left(dist, target_m - window_m), floor_i)
        hi = bisect.bisect_right(dist, target_m + window_m)
        if lo >= hi:
            return nearest_i(ll)
        best, bi = 1e9, None
        for i in range(lo, hi):
            d = ag.dist_m(pts[i], ll)
            if d < best:
                best, bi = d, i
        return bi, best

    wpts, ele_flags, dist_flags, off_track = [], [], [], []
    csv_total = float(rows[-1]["Distance (miles) From Start"]) or 1.0
    cursor = 0
    for (la, lo, nm, cmt), row in zip(cues, rows):
        ll = (float(la), float(lo))
        target_m = float(row["Distance (miles) From Start"] or 0) / csv_total * dist[-1]
        i, off = nearest_i_at(ll, target_m, floor_i=cursor)
        if i is None:
            print(f"  FLAG cue {nm!r} is not near the track at all")
            continue
        cursor = i
        if off > 25.0:
            off_track.append((off, nm, cmt))
        trk_ft = pts[i][2] * 3.28084
        trk_mi = dist[i] / 1609.344
        csv_ft = float(row["Elevation (ft)"] or 0)
        csv_mi = float(row["Distance (miles) From Start"] or 0)
        if csv_ft > 0 and abs(csv_ft - trk_ft) > ELE_FLAG_FT:
            ele_flags.append((abs(csv_ft - trk_ft), row["Type"], cmt, csv_ft, trk_ft, trk_mi))
        # the two files disagree on total length, so raw mileage differences are mostly that
        # offset accumulating. compare against the scaled track mile to expose real outliers.
        resid = csv_mi - trk_mi * csv_total / total_mi
        if abs(resid) > 0.05:
            dist_flags.append((abs(resid), row["Type"], cmt, csv_mi, trk_mi))
        wpts.append({
            "lat": la, "lon": lo, "i": i,
            "name": f"{row['Type']} @ {csv_mi:.2f} mi",
            "cmt": cmt or nm,
            "desc": (f"{row['Notes'] or cmt}. cuesheet mile {csv_mi:.2f}, "
                     f"track mile {trk_mi:.2f}. cue from official ridewithgps route export."),
            "sym": row["Type"],
            "type": "cue",
        })

    # pois. the ridewithgps export has none, so these come from the race site chart.
    cd = json.load(open(COURSE))
    pois = 0
    for st in cd["aid"]["stations"]:
        i, off = nearest_i((st["ll"][0], st["ll"][1]))
        if i is None:
            print(f"  FLAG aid station {st['name']!r} is not near the track")
            continue
        miles = ", ".join(f"{v['mile']:.1f} mi" for v in st["visits"])
        cut = ", ".join(v["cutoff"] for v in st["visits"] if v["cutoff"])
        crew = any(v["crew"] for v in st["visits"])
        wpts.append({
            "lat": f"{st['ll'][0]:.5f}", "lon": f"{st['ll'][1]:.5f}", "i": i,
            "name": st["name"],
            "cmt": f"aid station, chart miles {miles}",
            "desc": (f"aid station. chart miles {miles}."
                     + (f" cutoffs {cut}." if cut else "")
                     + (" crew access." if crew else " no crew access.")
                     + (" drop bags." if st["drop"] is True else "")
                     + " source: leadvilleraceseries.com 2026 run course chart,"
                       " not the ridewithgps export, which contains no pois."),
            "sym": "Aid Station",
            "type": "poi",
        })
        pois += 1

    if report:
        print(f"\nwaypoints: {len(wpts)} total, {len(wpts)-pois} cues and {pois} aid station pois")
        print(f"\nflags, elevation disagreement over {ELE_FLAG_FT:.0f} ft "
              f"between cuesheet and track ({len(ele_flags)}):")
        for d, ty, cmt, cf, tf, mi in sorted(ele_flags, reverse=True)[:12]:
            print(f"  {d:6.1f} ft  mile {mi:6.2f}  {ty:12s} csv {cf:9.2f} vs track {tf:9.2f}  {cmt[:44]}")
        if float(rows[0]["Elevation (ft)"] or 0) == 0:
            print("\nflags, cuesheet defect:")
            print(f"  the Start row lists elevation 0 ft. the track says "
                  f"{pts[0][2]*3.28084:.1f} ft. the track value is used.")
        print(f"\nflags, cue mileage residual over 0.05 mi after removing the "
              f"{csv_total/total_mi:.5f} scale offset ({len(dist_flags)}):")
        for d, ty, cmt, cm, tm in sorted(dist_flags, reverse=True)[:10]:
            print(f"  {d:6.3f} mi  {ty:12s} csv {cm:7.2f} vs track {tm:7.2f}  {cmt[:40]}")
        if off_track:
            print(f"\nflags, cue further than 25 m from the track ({len(off_track)}):")
            for d, nm, cmt in sorted(off_track, reverse=True)[:6]:
                print(f"  {d:6.1f} m  {nm:14s} {cmt[:50]}")
    return wpts, csv_total


def accuracy_report(total_mi, gain, csv_total, label):
    print(f"\ncross file totals:")
    print(f"  gpx track  : {total_mi:.3f} mi")
    print(f"  cuesheet   : {csv_total:.3f} mi")
    diff = abs(csv_total - total_mi)
    print(f"  difference : {diff:.3f} mi ({diff*5280:.0f} ft)"
          + ("  FLAG over tolerance" if diff > DIST_TOL_MI else "  within tolerance"))
    print(f"\naccuracy check against published figures ({label}):")
    dd = total_mi - PUB_DIST_MI
    print(f"  distance: {total_mi:.3f} mi vs published {PUB_DIST_MI:.2f} mi -> {dd:+.3f} mi "
          f"({dd*5280:+.0f} ft)  {'PASS' if abs(dd) <= DIST_TOL_MI else 'FAIL'}")
    dg = gain - PUB_GAIN_FT
    print(f"  gain    : {gain:.0f} ft vs published {PUB_GAIN_FT:.0f} ft -> {dg:+.0f} ft  "
          f"{'PASS' if abs(dg) <= GAIN_TOL_FT else 'FAIL'}")


def write_gpx(path, desc, meta, wpts, trk_rows, ele_for_wpt):
    # gpx 1.1 requires wpt before trk.
    name = "Leadville Trail 100 Run 2026 course"
    t_name, t_time, t_link = meta
    with open(path, "w") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        f.write('<gpx version="1.1" creator="therealleadville2026course.com" '
                'xmlns="http://www.topografix.com/GPX/1/1" '
                'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
                'xsi:schemaLocation="http://www.topografix.com/GPX/1/1 '
                'http://www.topografix.com/GPX/1/1/gpx.xsd">\n')
        f.write("  <metadata>\n")
        f.write(f"    <name>{name}</name>\n")
        f.write(f"    <desc>{xml_escape(desc)}</desc>\n")
        f.write(f'    <link href="{xml_escape(t_link)}"><text>{xml_escape(t_name)}</text></link>\n')
        f.write(f"    <time>{xml_escape(t_time)}</time>\n")
        f.write("  </metadata>\n")
        for w in wpts:
            f.write(f'  <wpt lat="{w["lat"]}" lon="{w["lon"]}">\n')
            f.write(f'    <ele>{ele_for_wpt(w["i"]):.1f}</ele>\n')
            f.write(f'    <name>{xml_escape(w["name"])}</name>\n')
            f.write(f'    <cmt>{xml_escape(w["cmt"])}</cmt>\n')
            f.write(f'    <desc>{xml_escape(w["desc"])}</desc>\n')
            f.write(f'    <sym>{xml_escape(w["sym"])}</sym>\n')
            f.write(f'    <type>{xml_escape(w["type"])}</type>\n')
            f.write("  </wpt>\n")
        f.write(f"  <trk>\n    <name>{name}</name>\n    <trkseg>\n")
        for la, lo, el in trk_rows:
            f.write(f'      <trkpt lat="{la}" lon="{lo}"><ele>{el}</ele></trkpt>\n')
        f.write("    </trkseg>\n  </trk>\n</gpx>\n")
    import os
    print(f"\nwrote {path} ({os.path.getsize(path)/1024:.0f} KB)")
