#!/usr/bin/env python3
"""Recover data/2026_LT_100_RUN_cues.gpx and data/cuesheet.csv from a published build.

The two cue inputs are RideWithGPS exports and, like the rest of data/, are not
committed. When the 2026 track was re-exported after the Twin Lakes revision they
were no longer on disk, so they are recovered here from the waypoint block of the
last published leadville-100-2026-official.gpx, which was built from them:

  wpt name "<Type> @ <mile> mi" -> cuesheet Type and Distance (miles) From Start
  wpt cmt                       -> rtept cmt (the RideWithGPS cue text)
  wpt desc up to ". cuesheet"   -> cuesheet Notes

Elevation is written as 0, which is how the cuesheet's own Start row reads and which
switches off the elevation cross check for those rows -- the recovered sheet cannot
support that check, and pretending otherwise would be worse than skipping it.

This is a recovery path, not the normal one. Re-export both files from the route page
whenever the route changes; the cue list here is the one that shipped with the
pre-revision route.
"""
import csv
import re
import sys

SRC = "leadville-100-2026-official.gpx"
OUT_GPX = "data/2026_LT_100_RUN_cues.gpx"
OUT_CSV = "data/cuesheet.csv"
TRACK = "data/2026_LT_100_RUN.gpx"

WPT_RE = re.compile(r'<wpt lat="([-\d.]+)" lon="([-\d.]+)">(.*?)</wpt>', re.S)
TAG = lambda t, s: (re.search(rf"<{t}>(.*?)</{t}>", s, re.S) or [None, ""])[1]
NAME_RE = re.compile(r"^(.*) @ ([\d.]+) mi$")


def unescape(s):
    return (s.replace("&lt;", "<").replace("&gt;", ">")
             .replace("&quot;", '"').replace("&amp;", "&"))


def escape(s):
    return (s.replace("&", "&amp;").replace("<", "&lt;")
             .replace(">", "&gt;").replace('"', "&quot;"))


def main():
    src = open(SRC).read()
    meta = re.search(r"<metadata>(.*?)</metadata>", open(TRACK).read(), re.S).group(1)
    rows, rtepts = [], []
    for lat, lon, body in WPT_RE.findall(src):
        if TAG("type", body) != "cue":
            continue
        m = NAME_RE.match(unescape(TAG("name", body)))
        if not m:
            sys.exit(f"waypoint name {TAG('name', body)!r} is not a cue name")
        typ, mile = m.group(1), m.group(2)
        cmt = unescape(TAG("cmt", body))
        notes = unescape(TAG("desc", body)).split(". cuesheet mile")[0]
        rows.append({"Type": typ, "Distance (miles) From Start": mile,
                     "Elevation (ft)": "0", "Notes": notes})
        rtepts.append(f'    <rtept lat="{lat}" lon="{lon}">\n'
                      f'      <name>{escape(cmt)}</name>\n'
                      f'      <cmt>{escape(cmt)}</cmt>\n'
                      f"    </rtept>")

    with open(OUT_GPX, "w") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n'
                '<gpx xmlns="http://www.topografix.com/GPX/1/1" version="1.1" '
                'creator="rebuild_cue_inputs.py from ridewithgps cues">\n'
                f"  <metadata>{meta}</metadata>\n"
                "  <rte>\n    <name>2026 LT 100 RUN</name>\n"
                + "\n".join(rtepts) + "\n  </rte>\n</gpx>\n")
    with open(OUT_CSV, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["Type", "Distance (miles) From Start",
                                          "Elevation (ft)", "Notes"])
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {OUT_GPX} and {OUT_CSV}: {len(rows)} cues recovered from {SRC}")


if __name__ == "__main__":
    main()
