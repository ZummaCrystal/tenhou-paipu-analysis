# -*- coding: utf-8 -*-
r"""svg2ico.py - 纯标准库 SVG(牌图子集) -> ICO/PNG 转换器

为打包生成应用图标，不引入任何第三方依赖（Pillow / cairosvg 等）。

用途: 生成 build/icon.ico（PyInstaller --icon / electron-builder win.icon 都用它）。
实测（全部 40 个素材）：萬子 0m-9m、字牌 1z-7z、back/Front 正常渲染；5z 与 Blank.svg 本来就是空牌面（0 条填充路径，输出空牌面图标）；筒子/索子里用到圆弧 A 命令的（5p.svg、1s.svg）会明确报错并且不产出文件。

支持范围（够用即止）:
  * 元素: <svg> / <g> / <path> / <rect> / <circle> / <ellipse> / <polygon>；defs 等忽略
  * transform: translate / scale / matrix / rotate(含 rotate(a,cx,cy))
  * <path> 命令: M L H V C S Q T Z（大小写、相对/绝对、隐式重复）
  * 仅填充（fill / fill-opacity / fill-rule=nonzero|evenodd），忽略 stroke
  * 忽略: marker / pattern / gradient / clip-path / mask / 弧线命令 A

用法:
  python tools\svg2ico.py --svg media\tiles\6m.svg --out build\icon.ico --png-dir build --ascii
"""
import argparse, io, math, os, re, struct, sys, zlib
import xml.etree.ElementTree as ET

IDENT = "MmZzLlHhVvCcSsQqTtAa"
TOK_RE = re.compile(r"[MmZzLlHhVvCcSsQqTtAa]|[-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?")


# ---------- 矩阵 ----------
def mul(p, c):
    """先 c 后 p: (p o c)"""
    pa, pb, pc, pd, pe, pf = p
    ca, cb, cc, cd, ce, cf = c
    return (pa * ca + pc * cb, pb * ca + pd * cb,
            pa * cc + pc * cd, pb * cc + pd * cd,
            pa * ce + pc * cf + pe, pb * ce + pd * cf + pf)


def parse_transform(s):
    m = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
    for name, args in re.findall(r"([a-zA-Z]+)\s*\(([^)]*)\)", s or ""):
        v = [float(x) for x in re.split(r"[\s,]+", args.strip()) if x]
        if not v:
            continue
        if name == "translate":
            t = (1.0, 0.0, 0.0, 1.0, v[0], v[1] if len(v) > 1 else 0.0)
        elif name == "scale":
            t = (v[0], 0.0, 0.0, v[1] if len(v) > 1 else v[0], 0.0, 0.0)
        elif name == "matrix":
            t = tuple(v[:6])
        elif name == "rotate":
            a = math.radians(v[0]); ca, sa = math.cos(a), math.sin(a)
            t = (ca, sa, -sa, ca, 0.0, 0.0)
            if len(v) >= 3:
                t = mul(mul((1, 0, 0, 1, v[1], v[2]), t), (1, 0, 0, 1, -v[1], -v[2]))
        else:
            continue
        m = mul(m, t)
    return m


def xf(m, x, y):
    return (m[0] * x + m[2] * y + m[4], m[1] * x + m[3] * y + m[5])


# ---------- path 解析 / 离散化 ----------
def parse_path(d):
    toks = TOK_RE.findall(d or "")
    subs = []
    cur = None
    cx = cy = sx = sy = 0.0
    prevc2 = prevq = None
    cmd = None
    i = 0
    warn = set()

    def newsub(x, y):
        nonlocal cur
        cur = [(x, y)]
        subs.append(cur)

    def n():
        nonlocal i
        v = float(toks[i]); i += 1
        return v

    while i < len(toks):
        tk = toks[i]
        if tk in IDENT:
            cmd = tk; i += 1
            if cmd in "Zz":
                if cur:
                    cur.append((sx, sy))
                cx, cy = sx, sy
                prevc2 = prevq = None
                continue
        else:
            if cmd is None:
                break
            if cmd == "M":
                cmd = "L"
            elif cmd == "m":
                cmd = "l"
        rel = cmd.islower()
        c = cmd.upper()
        if c == "M":
            if i + 1 >= len(toks):
                break
            x, y = n(), n()
            if rel:
                x, y = cx + x, cy + y
            cx = sx = x; cy = sy = y
            newsub(x, y)
        elif c == "L":
            x, y = n(), n()
            if rel:
                x, y = cx + x, cy + y
            if cur is None:
                newsub(cx, cy)
            cur.append((x, y)); cx, cy = x, y
        elif c == "H":
            x = n()
            if rel:
                x = cx + x
            if cur is None:
                newsub(cx, cy)
            cur.append((x, cy)); cx = x
        elif c == "V":
            y = n()
            if rel:
                y = cy + y
            if cur is None:
                newsub(cx, cy)
            cur.append((cx, y)); cy = y
        elif c == "C":
            x1, y1, x2, y2, x, y = n(), n(), n(), n(), n(), n()
            if rel:
                x1 += cx; y1 += cy; x2 += cx; y2 += cy; x += cx; y += cy
            if cur is None:
                newsub(cx, cy)
            _bez3(cur, cx, cy, x1, y1, x2, y2, x, y)
            prevc2 = (x2, y2); cx, cy = x, y
        elif c == "S":
            x2, y2, x, y = n(), n(), n(), n()
            if rel:
                x2 += cx; y2 += cy; x += cx; y += cy
            x1, y1 = (2 * cx - prevc2[0], 2 * cy - prevc2[1]) if prevc2 else (cx, cy)
            if cur is None:
                newsub(cx, cy)
            _bez3(cur, cx, cy, x1, y1, x2, y2, x, y)
            prevc2 = (x2, y2); cx, cy = x, y
        elif c == "Q":
            x1, y1, x, y = n(), n(), n(), n()
            if rel:
                x1 += cx; y1 += cy; x += cx; y += cy
            if cur is None:
                newsub(cx, cy)
            _bez2(cur, cx, cy, x1, y1, x, y)
            prevq = (x1, y1); cx, cy = x, y
        elif c == "T":
            x, y = n(), n()
            if rel:
                x += cx; y += cy
            x1, y1 = (2 * cx - prevq[0], 2 * cy - prevq[1]) if prevq else (cx, cy)
            if cur is None:
                newsub(cx, cy)
            _bez2(cur, cx, cy, x1, y1, x, y)
            prevq = (x1, y1); cx, cy = x, y
        else:
            raise NotImplementedError("不支持的命令「%s」（这种绘图方式本工具不认识）" % (c,))
        if c not in ("C", "S"):
            prevc2 = None
        if c not in ("Q", "T"):
            prevq = None
    return subs


def _bez3(pts, x0, y0, x1, y1, x2, y2, x3, y3, seg=48):
    for k in range(1, seg + 1):
        t = k / seg
        u = 1 - t
        a = u * u * u; b = 3 * u * u * t; c = 3 * u * t * t; d = t * t * t
        pts.append((a * x0 + b * x1 + c * x2 + d * x3, a * y0 + b * y1 + c * y2 + d * y3))


def _bez2(pts, x0, y0, x1, y1, x2, y2, seg=32):
    for k in range(1, seg + 1):
        t = k / seg
        u = 1 - t
        a = u * u; b = 2 * u * t; c = t * t
        pts.append((a * x0 + b * x1 + c * x2, a * y0 + b * y1 + c * y2))


# ---------- 画布 ----------
class Canvas:
    def __init__(self, w, h):
        self.w = w; self.h = h
        self.rgb = bytearray(w * h * 3)
        self.a = bytearray(w * h)

    def put(self, x, y, rgb):
        if 0 <= x < self.w and 0 <= y < self.h:
            i = y * self.w + x
            self.rgb[i * 3] = rgb[0]; self.rgb[i * 3 + 1] = rgb[1]; self.rgb[i * 3 + 2] = rgb[2]
            self.a[i] = 255

    def fill(self, polys, rgb, rule="nonzero"):
        edges = []
        for pts in polys:
            n = len(pts)
            if n < 3:
                continue
            for i in range(n):
                x0, y0 = pts[i]
                x1, y1 = pts[(i + 1) % n]
                if y0 != y1:
                    edges.append((x0, y0, x1, y1))
        if not edges:
            return 0
        ymin = max(0, int(math.floor(min(e[1] for e in edges))))
        ymax = min(self.h - 1, int(math.ceil(max(e[3] for e in edges))))
        W = self.w; filled = 0
        for py in range(ymin, ymax + 1):
            yc = py + 0.5
            xs = []
            for (x0, y0, x1, y1) in edges:
                if (y0 <= yc < y1) or (y1 <= yc < y0):
                    t = (yc - y0) / (y1 - y0)
                    xs.append((x0 + (x1 - x0) * t, 1 if y1 > y0 else -1))
            if not xs:
                continue
            xs.sort()
            if rule == "evenodd":
                for k in range(0, len(xs) - 1, 2):
                    filled += self._span(py, xs[k][0], xs[k + 1][0], rgb)
            else:
                wind = 0
                for k in range(len(xs) - 1):
                    wind += xs[k][1]
                    if wind != 0:
                        filled += self._span(py, xs[k][0], xs[k + 1][0], rgb)
        return filled

    def _span(self, py, xa, xb, rgb):
        if xb <= xa:
            return 0
        ia = max(0, int(math.ceil(xa - 0.5)))
        ib = min(self.w - 1, int(math.floor(xb - 0.5)))
        for x in range(ia, ib + 1):
            self.put(x, py, rgb)
        return max(0, ib - ia + 1)


def roundrect_polys(x0, y0, x1, y1, r, seg=24):
    r = max(0.0, min(r, (x1 - x0) / 2, (y1 - y0) / 2))
    pts = []
    if r <= 0.01:
        return [[(x0, y0), (x1, y0), (x1, y1), (x0, y1)]]
    corners = [(x1 - r, y1 - r, 0), (x0 + r, y1 - r, 90), (x0 + r, y0 + r, 180), (x1 - r, y0 + r, 270)]
    for cx, cy, a0 in corners:
        for k in range(seg + 1):
            a = math.radians(a0 + 90 * k / seg)
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return [pts]


# ---------- SVG 遍历 ----------
def shape_polys(el, t):
    """rect / circle / ellipse / polygon -> 子路径点列（用户坐标）"""
    def num(a, d=0.0):
        try:
            return float(el.get(a))
        except (TypeError, ValueError):
            return d
    if t == "rect":
        x, y, w, h = num("x"), num("y"), num("width"), num("height")
        r = max(num("rx"), num("ry"))
        return roundrect_polys(x, y, x + w, y + h, r) if r > 0 else \
            [[(x, y), (x + w, y), (x + w, y + h), (x, y + h)]]
    if t in ("circle", "ellipse"):
        cx, cy = num("cx"), num("cy")
        if t == "circle":
            rx = ry = num("r")
        else:
            rx, ry = num("rx"), num("ry")
        seg = 72
        return [[(cx + rx * math.cos(2 * math.pi * k / seg), cy + ry * math.sin(2 * math.pi * k / seg))
                 for k in range(seg)]]
    pts = [float(v) for v in re.split(r"[\s,]+", (el.get("points") or "").strip()) if v]
    return [[(pts[i], pts[i + 1]) for i in range(0, len(pts) - 1, 2)]]


def collect(svg_path, canvas_m, warn):
    tree = ET.parse(svg_path)
    root = tree.getroot()
    skip = ("defs", "metadata", "namedview", "marker", "pattern", "style", "title", "path-effect")
    items = []

    def tag(el):
        return el.tag.split("}")[-1]

    def walk(el, m):
        t = tag(el)
        if t in skip:
            return
        m = mul(m, parse_transform(el.get("transform")))
        if t == "path":
            subs = parse_path(el.get("d"))
        elif t in ("rect", "circle", "ellipse", "polygon"):
            subs = shape_polys(el, t)
        else:
            subs = None
        if subs is not None:
            style = el.get("style") or ""
            fill = el.get("fill")
            fo = el.get("fill-opacity")
            rule = el.get("fill-rule")
            for part in style.split(";"):
                if ":" not in part:
                    continue
                k, v = part.split(":", 1)
                k = k.strip(); v = v.strip()
                if k == "fill":
                    fill = v
                elif k == "fill-opacity":
                    fo = v
                elif k == "fill-rule":
                    rule = v
            if fill and fill != "none":
                polys = [[xf(mul(canvas_m, m), px, py) for (px, py) in sp] for sp in subs]
                items.append((polys, parse_color(fill), (rule or "nonzero").strip(),
                              float(fo) if fo else 1.0))
        for ch in list(el):
            walk(ch, m)
    walk(root, (1.0, 0.0, 0.0, 1.0, 0.0, 0.0))
    return items


def parse_color(v):
    v = v.strip()
    if v.startswith("#"):
        h = v[1:]
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        if len(h) >= 6:
            return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
    m = re.match(r"rgb\(\s*(\d+)[,\s]+(\d+)[,\s]+(\d+)", v)
    if m:
        return tuple(int(x) for x in m.groups())
    return (0, 0, 0)


# ---------- 缩放 / 输出 ----------
def axis_weights(S, n):
    out = []
    for j in range(n):
        a = j * S / n; b = (j + 1) * S / n
        ia = int(math.floor(a)); ib = int(math.ceil(b))
        items = []
        tot = 0.0
        for k in range(ia, ib):
            ov = min(b, k + 1) - max(a, k)
            if ov > 0:
                items.append((k, ov))
                tot += ov
        out.append([(k, v / tot) for (k, v) in items])
    return out


def downsample(canv, n):
    """盒式（面积加权）降采样：master -> n x n RGBA"""
    S = canv.w
    wx = axis_weights(S, n)
    wy = axis_weights(S, n)
    a = canv.a; rgb = canv.rgb
    ma = [0.0] * (n * S); mr = [0.0] * (n * S); mg = [0.0] * (n * S); mb = [0.0] * (n * S)
    for y in range(S):
        base = y * S
        for j, items in enumerate(wx):
            sa = sr = sg = sb = 0.0
            for (k, w) in items:
                i = base + k
                al = a[i]
                sa += al * w
                sr += rgb[i * 3] * al * w
                sg += rgb[i * 3 + 1] * al * w
                sb += rgb[i * 3 + 2] * al * w
            o = j * S + y
            ma[o] = sa; mr[o] = sr; mg[o] = sg; mb[o] = sb
    out = bytearray(n * n * 4)
    for j in range(n):
        for y in range(n):
            sa = sr = sg = sb = 0.0
            for (k, w) in wy[y]:
                o = j * S + k
                sa += ma[o] * w; sr += mr[o] * w; sg += mg[o] * w; sb += mb[o] * w
            if sa > 0.5:
                p = (y * n + j) * 4
                out[p] = min(255, int(sr / sa + 0.5))
                out[p + 1] = min(255, int(sg / sa + 0.5))
                out[p + 2] = min(255, int(sb / sa + 0.5))
                out[p + 3] = min(255, int(sa + 0.5))
    return out

def alpha_span(sa):
    return max(0, min(255, int(round(sa / 255.0))))


def png_bytes(w, h, rgba):
    raw = bytearray()
    for y in range(h):
        raw.append(0)
        raw += rgba[y * w * 4:(y + 1) * w * 4]

    def chunk(typ, data):
        return (struct.pack(">I", len(data)) + typ + data
                + struct.pack(">I", zlib.crc32(typ + data) & 0xffffffff))
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(bytes(raw), 9)) + chunk(b"IEND", b""))


def bmp_bytes(w, h, rgba):
    px = bytearray()
    for y in range(h - 1, -1, -1):
        row = rgba[y * w * 4:(y + 1) * w * 4]
        for x in range(w):
            px += bytes((row[x * 4 + 2], row[x * 4 + 1], row[x * 4], row[x * 4 + 3]))
    mask_row = ((w + 31) // 32) * 4
    mask = bytes(mask_row * h)
    hdr = struct.pack("<IiiHHIIiiII", 40, w, h * 2, 1, 32, 0, len(px) + len(mask), 0, 0, 0, 0)
    return hdr + bytes(px) + mask


def ico_bytes(images):
    n = len(images)
    out = struct.pack("<HHH", 0, 1, n)
    off = 6 + 16 * n
    body = b""
    for (size, data) in images:
        out += struct.pack("<BBBBHHII", size if size < 256 else 0, size if size < 256 else 0, 0, 0, 1, 32, len(data), off + len(body))
        body += data
    return out + body


def ascii_preview(rgba, n, cols=46):
    rows = max(1, int(cols * n / n)) if False else cols
    lines = []
    for y in range(n):
        line = ""
        for x in range(n):
            p = (y * n + x) * 4
            al = rgba[p + 3]
            if al < 40:
                line += " "
            else:
                lum = (rgba[p] * 299 + rgba[p + 1] * 587 + rgba[p + 2] * 114) // 1000
                line += "@" if lum < 80 else ("+" if lum < 170 else ".")
        lines.append(line)
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--svg", required=True)
    ap.add_argument("--out", default="build\\icon.ico")
    ap.add_argument("--sizes", default="16,32,48,64,128,256")
    ap.add_argument("--master", type=int, default=1024)
    ap.add_argument("--face", default="#ffffff", help="牌面底色，none=透明")
    ap.add_argument("--radius", type=float, default=0.09, help="圆角比例(相对牌宽)")
    ap.add_argument("--preview-size", type=int, default=48)
    ap.add_argument("--ascii", action="store_true")
    ap.add_argument("--png-dir", default="")
    args = ap.parse_args()

    svg = os.path.abspath(args.svg)
    tree = ET.parse(svg)
    svg_el = tree.getroot()
    vb = (svg_el.get("viewBox") or "").replace(",", " ").split()
    if len(vb) == 4:
        vx, vy, vw, vh = (float(t) for t in vb)
    else:
        vx, vy, vw, vh = 0.0, 0.0, float(svg_el.get("width", 100)), float(svg_el.get("height", 100))
    S = args.master
    scale = min(S / vw, S / vh)
    tx = (S - vw * scale) / 2.0 - vx * scale
    ty = (S - vh * scale) / 2.0 - vy * scale
    canvas_m = (scale, 0.0, 0.0, scale, tx, ty)
    print("viewBox=(%g,%g,%g,%g) master=%d scale=%.6f 牌面像素=%.0fx%.0f"
          % (vx, vy, vw, vh, S, scale, vw * scale, vh * scale))

    canv = Canvas(S, S)
    if args.face and args.face.lower() != "none":
        face = parse_color(args.face)
        r = args.radius * (vw * scale)
        p = roundrect_polys(tx + vx * scale, ty + vy * scale,
                            tx + (vx + vw) * scale, ty + (vy + vh) * scale, r)
        canv.fill(p, face, "nonzero")
        print("牌面: %s r=%.1f" % (args.face, r))

    try:
        items = collect(svg, canvas_m, set())
    except NotImplementedError as exc:
        print("!! %s：%s" % (os.path.basename(svg), exc))
        print("!! 没有生成 %s —— 宁可失败也不产出残缺图标。" % args.out)
        return 2
    print("路径数=%d" % len(items))
    if not items:
        print("?? 没有任何填充路径（空牌面素材如 5z/Blank.svg 属正常；若是筒子/索子则是本工具没认出来）")
    for (polys, rgb, rule, fo) in items:
        npts = sum(len(p) for p in polys)
        got = canv.fill(polys, rgb, rule)
        print("  fill #%02x%02x%02x rule=%-8s op=%.2f subpaths=%d pts=%d 着色=%d px"
              % (rgb[0], rgb[1], rgb[2], rule, fo, len(polys), npts, got))

    sizes = [int(x) for x in args.sizes.split(",") if x.strip()]
    images = []
    for n in sizes:
        rgba = downsample(canv, n)
        data = png_bytes(n, n, rgba) if n > 64 else bmp_bytes(n, n, rgba)
        images.append((n, data))
        if args.png_dir:
            os.makedirs(args.png_dir, exist_ok=True)
            with open(os.path.join(args.png_dir, "icon_%d.png" % n), "wb") as f:
                f.write(png_bytes(n, n, rgba))
    out = os.path.abspath(args.out)
    d = os.path.dirname(out)
    if d:
        os.makedirs(d, exist_ok=True)
    with open(out, "wb") as f:
        f.write(ico_bytes(images))
    print("已写出 %s (%d 字节, 尺寸=%s)" % (out, os.path.getsize(out), sizes))
    if args.ascii:
        pv = downsample(canv, args.preview_size)
        print("---- ASCII 预览 (%dx%d) ----" % (args.preview_size, args.preview_size))
        print(ascii_preview(pv, args.preview_size))
    return 0


if __name__ == "__main__":
    sys.exit(main())