"""Draw the deployment guide's map as SVG paths, from Natural Earth's 1:50m country outlines.

Run once by hand when the covered countries change (the outlines don't):
  curl -sSLo /tmp/ne50.geojson https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_50m_admin_0_countries.geojson
  python3 scripts/make_deploy_map.py /tmp/ne50.geojson
It writes scripts/deploy-map.svg, which build_pages.py puts into /deploy/. Countries listed in
deploy-countries.json are clickable; their neighbours are drawn grey for context.
Natural Earth is public domain.
"""
import json
import math
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
W0, W1, S, N = -18.0, 64.0, -6.5, 42.5  # lon/lat box
K = math.cos(math.radians(20))  # equirectangular, true at 20°N
SCALE = 1000 / ((W1 - W0) * K)
H = round((N - S) * SCALE)
TOL = 0.7  # simplification tolerance, in SVG units


def xy(lon, lat):
    return ((lon - W0) * K * SCALE, (N - lat) * SCALE)


def simplify(pts, tol):
    # Douglas-Peucker
    if len(pts) < 3:
        return pts
    (x1, y1), (x2, y2) = pts[0], pts[-1]
    dx, dy = x2 - x1, y2 - y1
    d = math.hypot(dx, dy) or 1e-9
    far, idx = 0, 0
    for i in range(1, len(pts) - 1):
        x, y = pts[i]
        dist = abs(dy * x - dx * y + x2 * y1 - y2 * x1) / d
        if dist > far:
            far, idx = dist, i
    if far <= tol:
        return [pts[0], pts[-1]]
    return simplify(pts[: idx + 1], tol)[:-1] + simplify(pts[idx:], tol)


def ring_path(ring):
    pts = [xy(*p[:2]) for p in ring]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    if max(xs) < -20 or min(xs) > 1020 or max(ys) < -20 or min(ys) > H + 20:
        return ""
    # Split the closed ring in two so the simplifier keeps its shape.
    half = len(pts) // 2
    pts = simplify(pts[: half + 1], TOL)[:-1] + simplify(pts[half:], TOL)
    if len(pts) < 4 and (max(xs) - min(xs)) < 3:
        pts = [xy(*p[:2]) for p in ring]  # tiny islands like Bahrain: keep every point
    return "M" + "L".join(f"{x:.1f},{y:.1f}" for x, y in pts) + "Z"


def main(src):
    covered = {c["iso2"] for c in json.loads((ROOT / "deploy-countries.json").read_text())["countries"]}
    alias = {"SOL": "SO"}  # Somaliland is shown as part of Somalia, as the FCDO does
    out, labels = [], []
    for f in json.load(open(src))["features"]:
        p, g = f["properties"], f["geometry"]
        polys = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
        d = "".join(ring_path(poly[0]) for poly in polys)
        if not d:
            continue
        iso = alias.get(p["ADM0_A3"], p["ISO_A2_EH"])
        if iso in covered:
            out.append(f'<path class="c" data-iso="{iso}" d="{d}"><title>{p["NAME"] if p["ADM0_A3"] != "SOL" else "Somalia (Somaliland)"}</title></path>')
        else:
            out.append(f'<path class="n" d="{d}"><title>{p["NAME"]} (not covered yet)</title></path>')
    svg = (f'<svg id="map" viewBox="0 0 1000 {H}" role="group" aria-label="Map of the Horn of Africa and the Middle East and North Africa. Choose a country.">\n'
           '<rect class="sea" width="1000" height="' + str(H) + '"/>\n' + "\n".join(out) + "\n</svg>\n")
    (ROOT / "scripts" / "deploy-map.svg").write_text(svg)
    print(f"Wrote {len(out)} shapes, {len(svg) // 1024} KB")


if __name__ == "__main__":
    main(sys.argv[1])
