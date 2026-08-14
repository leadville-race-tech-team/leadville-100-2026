#!/usr/bin/env python3
# builds the default download, straight from the official ridewithgps export.
# geometry and elevation are the source of truth and pass through untouched.
# coordinate and elevation strings are copied verbatim so nothing is rounded or simplified.
# see make_baro_gpx.py for the variant that corrects elevation with 2025 barometric data.
import analyze_gpx as ag
import course_common as cc

OUT = "leadville-100-2026-official.gpx"


def main():
    raw, pts, dist, meta = cc.load_track()
    total_mi = dist[-1] / 1609.344
    gain, loss = ag.gain_loss_ft(pts)
    print(f"\ntrack: {len(pts)} points, {total_mi:.3f} mi")
    print(f"  elevation source: ridewithgps dem, {min(p[2] for p in pts)*3.28084:.0f}"
          f"..{max(p[2] for p in pts)*3.28084:.0f} ft")
    print(f"  gain {gain:.0f} ft at 7.5 m hysteresis, "
          f"{ag.gain_loss_ft(pts, thr=0.0)[0]:.0f} ft with no threshold")
    print(f"  loop closure {(pts[-1][2]-pts[0][2])*3.28084:+.1f} ft")

    wpts, csv_total = cc.build_waypoints(pts, dist)
    cc.accuracy_report(total_mi, gain, csv_total, "official dem")

    desc = (f"Official 2026 course. Geometry and elevation from the RideWithGPS GPX Track "
            f"export of route {cc.ROUTE_ID} ({meta[1]}), unrounded and unsimplified. "
            f"Elevation is RideWithGPS DEM. "
            f"{sum(1 for w in wpts if w['type']=='cue')} cue waypoints and "
            f"{sum(1 for w in wpts if w['type']=='poi')} aid station waypoints. "
            f"Track measures {total_mi:.2f} mi with {gain:.0f} ft of gain.")
    cc.write_gpx(OUT, desc, meta, wpts, raw, lambda i: pts[i][2])


if __name__ == "__main__":
    main()
