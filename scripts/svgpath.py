"""Accurate bbox for an SVG path, including elliptical arcs.

Supports M/m L/l H/h V/v A/a Z/z, converting arcs to cubic beziers and
sampling each segment so the bbox reflects curve extrema rather than just
endpoints. Used to centre and scale the wrench glyph inside favicon.svg.
"""
import math
import re

NUM = re.compile(r"[-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?")
CMD = re.compile(r"([MmLlHhVvAaZzCcSsQqTt])")


def tokenize(d):
    out = []
    parts = CMD.split(d)
    i = 1
    while i < len(parts):
        cmd = parts[i]
        nums = [float(x) for x in NUM.findall(parts[i + 1])] if i + 1 < len(parts) else []
        out.append((cmd, nums))
        i += 2
    return out


def arc_to_beziers(x0, y0, rx, ry, phi, fa, fs, x1, y1):
    """Endpoint -> centre parameterisation (SVG spec F.6.5), then beziers."""
    if rx == 0 or ry == 0:
        return [((x0, y0), (x1, y1))]
    rx, ry = abs(rx), abs(ry)
    p = math.radians(phi)
    cosp, sinp = math.cos(p), math.sin(p)
    dx2, dy2 = (x0 - x1) / 2.0, (y0 - y1) / 2.0
    x1p = cosp * dx2 + sinp * dy2
    y1p = -sinp * dx2 + cosp * dy2
    lam = x1p * x1p / (rx * rx) + y1p * y1p / (ry * ry)
    if lam > 1:
        s = math.sqrt(lam)
        rx, ry = rx * s, ry * s
    num = rx * rx * ry * ry - rx * rx * y1p * y1p - ry * ry * x1p * x1p
    den = rx * rx * y1p * y1p + ry * ry * x1p * x1p
    co = math.sqrt(max(0.0, num / den)) if den else 0.0
    if fa == fs:
        co = -co
    cxp = co * rx * y1p / ry
    cyp = -co * ry * x1p / rx
    cx = cosp * cxp - sinp * cyp + (x0 + x1) / 2.0
    cy = sinp * cxp + cosp * cyp + (y0 + y1) / 2.0

    def ang(ux, uy, vx, vy):
        dot = ux * vx + uy * vy
        n = math.hypot(ux, uy) * math.hypot(vx, vy)
        a = math.acos(max(-1.0, min(1.0, dot / n))) if n else 0.0
        return -a if ux * vy - uy * vx < 0 else a

    th1 = ang(1, 0, (x1p - cxp) / rx, (y1p - cyp) / ry)
    dth = ang((x1p - cxp) / rx, (y1p - cyp) / ry, (-x1p - cxp) / rx, (-y1p - cyp) / ry)
    if not fs and dth > 0:
        dth -= 2 * math.pi
    elif fs and dth < 0:
        dth += 2 * math.pi

    n = max(1, int(math.ceil(abs(dth) / (math.pi / 2))))
    delta = dth / n
    t = 4.0 / 3.0 * math.tan(delta / 4.0)
    out = []
    th = th1
    px, py = x0, y0
    for _ in range(n):
        c1, s1 = math.cos(th), math.sin(th)
        th2 = th + delta
        c2, s2 = math.cos(th2), math.sin(th2)
        ex = cx + rx * cosp * c2 - ry * sinp * s2
        ey = cy + rx * sinp * c2 + ry * cosp * s2
        dx1 = -rx * cosp * s1 - ry * sinp * c1
        dy1 = -rx * sinp * s1 + ry * cosp * c1
        dx2 = -rx * cosp * s2 - ry * sinp * c2
        dy2 = -rx * sinp * s2 + ry * cosp * c2
        out.append(((px, py),
                    (px + t * dx1, py + t * dy1),
                    (ex - t * dx2, ey - t * dy2),
                    (ex, ey)))
        px, py = ex, ey
        th = th2
    return out


def flatten(d, samples=24):
    """Return sampled points along the path."""
    toks = tokenize(d)
    pts = []
    cx = cy = 0.0
    sx = sy = 0.0
    i = 0
    cur = None
    prev_c2 = None
    for cmd, nums in toks:
        if cmd in "Zz":
            cx, cy = sx, sy
            cur = None
            continue
        rel = cmd.islower()
        c = cmd.upper()
        j = 0
        if c == "M":
            while j + 1 < len(nums):
                x, y = nums[j], nums[j + 1]
                j += 2
                if rel:
                    x, y = cx + x, cy + y
                if cur is None:
                    cx, cy = x, y
                    sx, sy = x, y
                    cur = "L"
                    pts.append((cx, cy))
                else:
                    cx, cy = x, y
                    cur = "L"
                    pts.append((cx, cy))
        elif c == "L":
            while j + 1 < len(nums):
                x, y = nums[j], nums[j + 1]
                j += 2
                cx, cy = (cx + x, cy + y) if rel else (x, y)
                pts.append((cx, cy))
        elif c == "H":
            while j < len(nums):
                x = nums[j]; j += 1
                cx = cx + x if rel else x
                pts.append((cx, cy))
        elif c == "V":
            while j < len(nums):
                y = nums[j]; j += 1
                cy = cy + y if rel else y
                pts.append((cx, cy))
        elif c == "A":
            while j + 6 < len(nums):
                rx, ry, rot, fa, fs, x, y = nums[j:j + 7]
                j += 7
                if rel:
                    x, y = cx + x, cy + y
                for p0, p1, p2, p3 in arc_to_beziers(cx, cy, rx, ry, rot, int(fa), int(fs), x, y):
                    for s in range(samples + 1):
                        t = s / samples
                        mt = 1 - t
                        bx = (mt ** 3 * p0[0] + 3 * mt ** 2 * t * p1[0]
                              + 3 * mt * t ** 2 * p2[0] + t ** 3 * p3[0])
                        by = (mt ** 3 * p0[1] + 3 * mt ** 2 * t * p1[1]
                              + 3 * mt * t ** 2 * p2[1] + t ** 3 * p3[1])
                        pts.append((bx, by))
                cx, cy = x, y
        elif c == "C":
            while j + 5 < len(nums):
                x1, y1, x2, y2, x, y = nums[j:j + 6]
                j += 6
                if rel:
                    x1, y1, x2, y2, x, y = (cx + x1, cy + y1, cx + x2, cy + y2, cx + x, cy + y)
                for s in range(samples + 1):
                    t = s / samples
                    mt = 1 - t
                    pts.append((
                        mt ** 3 * cx + 3 * mt ** 2 * t * x1 + 3 * mt * t ** 2 * x2 + t ** 3 * x,
                        mt ** 3 * cy + 3 * mt ** 2 * t * y1 + 3 * mt * t ** 2 * y2 + t ** 3 * y,
                    ))
                cx, cy = x, y
        elif c in "Qq":
            while j + 3 < len(nums):
                qx, qy, x, y = nums[j:j + 4]
                j += 4
                if rel:
                    qx, qy, x, y = cx + qx, cy + qy, cx + x, cy + y
                c1 = (cx + 2.0 / 3 * (qx - cx), cy + 2.0 / 3 * (qy - cy))
                c2 = (x + 2.0 / 3 * (qx - x), y + 2.0 / 3 * (qy - y))
                for p0, p1, p2, p3 in arc_to_beziers.__wrapped__ if False else \
                        [((cx, cy), c1, c2, (x, y))]:
                    for s in range(samples + 1):
                        t = s / samples
                        mt = 1 - t
                        pts.append((
                            mt ** 3 * p0[0] + 3 * mt ** 2 * t * p1[0] + 3 * mt * t ** 2 * p2[0] + t ** 3 * p3[0],
                            mt ** 3 * p0[1] + 3 * mt ** 2 * t * p1[1] + 3 * mt * t ** 2 * p2[1] + t ** 3 * p3[1],
                        ))
                cx, cy = x, y
        prev_c2 = None
    return pts


def bbox(d):
    pts = flatten(d)
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys), len(pts)


if __name__ == "__main__":
    import sys
    WRENCH = ("M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77"
              "a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91"
              "a6 6 0 0 1 7.94-7.94l-3.76 3.76z")
    minx, miny, maxx, maxy, n = bbox(WRENCH)
    print(f"wrench path sampled {n} points")
    print(f"  raw bbox (24x24 space): x {minx:.3f}..{maxx:.3f}  y {miny:.3f}..{maxy:.3f}")
    w, h = maxx - minx, maxy - miny
    print(f"  size: {w:.3f} x {h:.3f}")
    cx, cy = (minx + maxx) / 2, (miny + maxy) / 2
    print(f"  centre: ({cx:.3f}, {cy:.3f})")
    if minx >= -0.01 and miny >= -0.01 and maxx <= 24.01 and maxy <= 24.01:
        print("  ok: glyph fits inside its 24x24 viewBox")
    else:
        print("  WARN: glyph exceeds the 24x24 viewBox")
