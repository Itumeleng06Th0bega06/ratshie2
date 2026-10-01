"""Check favicon.svg geometry using the real arc-aware path parser.

Confirms the glyph stays inside the 32x32 tile, is optically centred, and
leaves even padding so the rounded corner never clips the stroke.
"""
import re
import xml.etree.ElementTree as ET

from svgpath import flatten

SVG = "static/img/brand/favicon.svg"
NS = "{http://www.w3.org/2000/svg}"

root = ET.parse(SVG).getroot()
rect = root.find(f"{NS}rect")
g = root.find(f"{NS}g")
path = g.find(f"{NS}path")

vb = [float(v) for v in root.get("viewBox").split()]
TILE = vb[2]
rx = float(rect.get("rx"))
sw = float(g.get("stroke-width"))
m = re.search(r"translate\(([-\d.]+)[ ,]+([-\d.]+)\)", g.get("transform"))
tx, ty = float(m.group(1)), float(m.group(2))

pts = flatten(path.get("d"))
xs = [p[0] + tx for p in pts]
ys = [p[1] + ty for p in pts]
minx, maxx = min(xs), max(xs)
miny, maxy = min(ys), max(ys)
half = sw / 2.0

gx0, gx1 = minx - half, maxx + half
gy0, gy1 = miny - half, maxy + half
print(f"tile {TILE:.0f} (rx={rx}), stroke-width {sw}, translate ({tx}, {ty})")
print(f"glyph+stroke bbox: x {gx0:.3f}..{gx1:.3f}  y {gy0:.3f}..{gy1:.3f}")
print(f"glyph size: {gx1-gx0:.3f} x {gy1-gy0:.3f}")

ok = True
print()
# 1. inside the tile
if gx0 < 0 or gy0 < 0 or gx1 > TILE or gy1 > TILE:
    print(f"FAIL: glyph escapes the {TILE:.0f}x{TILE:.0f} tile")
    ok = False
else:
    print("ok: glyph inside tile")

# 2. clear of the rounded corner: a glyph point is safe only if it sits inside
# the tile AND, in a corner quadrant, is no further than the corner arc radius
# from the arc centre. This is the true rounded-rect containment test.
import math

OFFS = [(0, 0)]
for k in range(8):
    a = k * math.pi / 4
    OFFS.append((math.cos(a) * half, math.sin(a) * half))


def inside_round_rect(x, y):
    lim = TILE - rx
    cx = min(max(x, rx), lim)
    cy = min(max(y, rx), lim)
    return (x - cx) ** 2 + (y - cy) ** 2 <= rx * rx + 1e-9


worst = None
for x, y in pts:
    for ox, oy in OFFS:
        px, py = x + tx + ox, y + ty + oy
        if not (0 <= px <= TILE and 0 <= py <= TILE):
            worst = (px, py, "outside tile")
            break
        if not inside_round_rect(px, py):
            worst = (px, py, "clipped by corner radius")
            break
    if worst:
        break
if worst:
    print(f"FAIL: glyph {worst[2]} at ({worst[0]:.3f}, {worst[1]:.3f})")
    ok = False
else:
    print("ok: glyph fully inside tile incl. rounded corners (stroke included)")

# 3. optical centring
cx, cy = (gx0 + gx1) / 2, (gy0 + gy1) / 2
dx, dy = cx - TILE / 2, cy - TILE / 2
print(f"centre ({cx:.3f}, {cy:.3f}) vs tile centre ({TILE/2:.2f}, {TILE/2:.2f}) "
      f"-> offset ({dx:+.3f}, {dy:+.3f})")
if abs(dx) > 0.35 or abs(dy) > 0.35:
    print("FAIL: glyph is not centred within 0.35px")
    ok = False
else:
    print("ok: centred within 0.35px")

# 4. balanced padding
pads = {"left": gx0, "top": gy0, "right": TILE - gx1, "bottom": TILE - gy1}
print("padding: " + "  ".join(f"{k}={v:.2f}" for k, v in pads.items()))
if min(pads.values()) < 1.5:
    print("FAIL: padding under 1.5px on some side")
    ok = False
else:
    print("ok: padding >= 1.5px on every side")

print()
print("RESULT:", "PASS" if ok else "NEEDS ADJUSTMENT")
raise SystemExit(0 if ok else 1)
