"""Generate og-card.html (1200x630) from course_data.json, for screenshotting to og-image.png."""
import json, math

data = json.load(open("course_data.json"))

# Fit both tracks into the right-hand panel of the card.
W, H = 640, 560
PAD = 28
all_pts = data["t2025"]["pts"] + data["t2026"]["pts"]
lats = [p[0] for p in all_pts]
lons = [p[1] for p in all_pts]
lat0, lat1, lon0, lon1 = min(lats), max(lats), min(lons), max(lons)
klon = math.cos(math.radians((lat0 + lat1) / 2))
span_x = (lon1 - lon0) * klon
span_y = lat1 - lat0
s = min((W - 2 * PAD) / span_x, (H - 2 * PAD) / span_y)
ox = (W - span_x * s) / 2
oy = (H - span_y * s) / 2

def xy(p):
    x = ox + (p[1] - lon0) * klon * s
    y = oy + (lat1 - p[0]) * s
    return f"{x:.1f},{y:.1f}"

def polys(track, want_div, color, width, opacity):
    out = []
    for seg in track["segs"]:
        if bool(seg["div"]) != want_div:
            continue
        pts = track["pts"][seg["a"]:seg["b"] + 1]
        path = " ".join(xy(p) for p in pts[::2] or pts)
        out.append(f'<polyline points="{path}" fill="none" stroke="{color}" '
                   f'stroke-width="{width}" stroke-opacity="{opacity}" '
                   f'stroke-linecap="round" stroke-linejoin="round"/>')
    return "\n".join(out)

svg_lines = "\n".join([
    polys(data["t2026"], False, "#6b6a66", 3, 0.9),   # shared
    polys(data["t2025"], True, "#3987e5", 4, 0.95),    # 2025 only
    polys(data["t2026"], True, "#d95926", 4.5, 1.0),   # 2026 only
])

html = f"""<!doctype html><html><head><meta charset="utf-8"><style>
  html, body {{ margin: 0; padding: 0; }}
  .card {{
    width: 1200px; height: 630px; background: #1a1a19; color: #ffffff;
    font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
    display: flex; align-items: center; overflow: hidden; position: relative;
  }}
  .left {{ width: 530px; padding: 0 0 0 56px; box-sizing: border-box; }}
  .logo {{ margin-bottom: 26px; }}
  h1 {{ font-size: 44px; line-height: 1.12; font-weight: 700; letter-spacing: -0.015em; margin: 0 0 14px; }}
  h1 .y25 {{ color: #3987e5; }}
  h1 .y26 {{ color: #d95926; }}
  .sub {{ font-size: 21px; color: #c3c2b7; margin: 0 0 26px; line-height: 1.4; }}
  .stats {{ font-size: 18px; color: #c3c2b7; }}
  .stats b {{ color: #ffffff; font-weight: 650; }}
  .stats .row {{ margin-bottom: 7px; }}
  .dot {{ display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-right: 8px; }}
  .domain {{ position: absolute; left: 56px; bottom: 34px; font-size: 17px; color: #898781; font-weight: 550; }}
  .map {{ position: absolute; right: 10px; top: 35px; }}
</style></head><body>
<div class="card">
  <div class="left">
    <div class="logo">
      <svg width="64" height="64" viewBox="0 0 64 64">
        <rect width="64" height="64" rx="14" fill="#242423"/>
        <path d="M6 46 L20 20 L30 38 L42 13 L58 46" fill="none" stroke="#eb6834" stroke-width="6" stroke-linecap="round" stroke-linejoin="round"/>
        <path d="M6 53 L22 36 L34 47 L48 30 L58 42" fill="none" stroke="#2a78d6" stroke-width="4.5" stroke-linecap="round" stroke-linejoin="round" opacity="0.92"/>
      </svg>
    </div>
    <h1>Leadville 100 Run<br><span class="y25">2025</span> vs <span class="y26">2026</span> course</h1>
    <p class="sub">Interactive map of the 2026 reroute, with aid stations, cutoffs and elevation.</p>
    <div class="stats">
      <div class="row"><span class="dot" style="background:#d95926"></span><b>28.7 mi</b> of new 2026 routing</div>
      <div class="row"><span class="dot" style="background:#3987e5"></span><b>19.0 mi</b> of the 2025 course dropped</div>
      <div class="row"><span class="dot" style="background:#6b6a66"></span><b>13,550 ft</b> of climbing &nbsp;·&nbsp; <b>12</b> aid stations</div>
    </div>
    <div class="domain">therealleadville2026course.com &nbsp;·&nbsp; unofficial fan project</div>
  </div>
  <div class="map">
    <svg width="{W}" height="{H}" viewBox="0 0 {W} {H}">
{svg_lines}
    </svg>
  </div>
</div>
</body></html>"""

open("og-card.html", "w").write(html)
print("wrote og-card.html")
