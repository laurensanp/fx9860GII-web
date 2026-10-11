"""Builds the web app's skin from a photo of the calculator instead of drawing
it: cuts the calculator out of the white background and writes
web/skin.webp and web/layout.json (positions in 1x units, width 480).

    python3 make_photo_skin.py <photo> <output dir> [preview.png]

skin-photo.webp is a product photo (2000 x 2000), cropped to the calculator
and enlarged 2x with Real-ESRGAN. The positions below were measured in a
1932 px wide version of the original photo.

The enlargement garbles the small lettering, so the labels above the keys
and the REPLAY arrows are set again with the real legends (fonts: Segoe UI,
Cambria and Georgia from $FONTS, default the Windows font folder).
"""
import json
import os
import sys

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont
from scipy import ndimage

PHOTO, OUT = sys.argv[1], sys.argv[2]
FONTS = os.environ.get("FONTS", "/mnt/c/Windows/Fonts")
REF = 1932.0                           # width of the photo the positions were measured in
ORIGINAL = 2000.0                      # width of the original photo
ORIGIN = (530, 90)                     # top left of the crop in the original photo
SCALE = 2                              # enlargement of the crop

GLASS = (615, 310, 1312, 695)          # x0, y0, x1, y1 of the LCD glass
LCD = (648, 341, 632, 316)             # x, y, w, h of the 128x64 pixel area
MENU = (1215, 700, 100, 44)            # the "..." button, right of "USB POWER GRAPHIC"
BADGE = (630, 706)
POP = (960, 748, 350)
LCD_ON, LCD_OFF = (42, 46, 40), (183, 191, 168)
LCD_ON_LIT, LCD_OFF_LIT = (18, 24, 44), (164, 202, 240)

keys = []   # code, name, x0, y0, x1, y1 (photo coordinates)


def row(y0, y1, centres, half, codes):
    for cx, (code, name) in zip(centres, codes):
        keys.append([code, name, cx - half, y0, cx + half, y1])


row(780, 895, [700, 805, 910, 1016, 1122, 1228], 52, [(0x91 + i, f"F{i + 1}") for i in range(6)])
row(925, 998, [697, 803, 909, 1015], 52, [(0x81, "SHIFT"), (0x82, "OPTN"), (0x83, "VARS"), (0x84, "MENU")])
row(1018, 1092, [697, 803, 909, 1015], 52, [(0x71, "ALPHA"), (0x72, "SQUARE"), (0x73, "POWER"), (0x74, "EXIT")])
SIX = [697, 802, 908, 1014, 1120, 1227]
row(1138, 1214, SIX, 52, [(0x61, "XOT"), (0x62, "LOG"), (0x63, "LN"), (0x64, "SIN"), (0x65, "COS"), (0x66, "TAN")])
row(1230, 1306, SIX, 52, [(0x51, "FRAC"), (0x52, "FD"), (0x53, "LEFTP"), (0x54, "RIGHTP"), (0x55, "COMMA"), (0x56, "ARROW")])
FIVE = [703, 831, 959, 1087, 1215]
row(1332, 1420, FIVE, 63, [(0x41, "7"), (0x42, "8"), (0x43, "9"), (0x44, "DEL"), (0x07, "ACON")])
row(1440, 1528, FIVE, 63, [(0x31, "4"), (0x32, "5"), (0x33, "6"), (0x34, "MUL"), (0x35, "DIV")])
row(1548, 1636, FIVE, 63, [(0x21, "1"), (0x22, "2"), (0x23, "3"), (0x24, "ADD"), (0x25, "SUB")])
row(1656, 1746, FIVE, 63, [(0x11, "0"), (0x12, "DOT"), (0x13, "EXP"), (0x14, "NEG"), (0x15, "EXE")])
PX, PY, PR = 1175, 990, 96             # REPLAY pad
for code, name, dx, dy in [(0x86, "UP", 0, -1), (0x75, "DOWN", 0, 1), (0x85, "LEFT", -1, 0), (0x76, "RIGHT", 1, 0)]:
    cx, cy = PX + dx * 58, PY + dy * 58
    keys.append([code, name, cx - 40, cy - 40, cx + 40, cy + 40])

photo = Image.open(PHOTO).convert("RGB")
k = ORIGINAL / REF * SCALE             # photo pixels per reference pixel

# Background: everything near-white that is connected to the image border.
# Found at half size (fast), then enlarged and smoothed for a clean edge.
small = photo.resize((photo.size[0] // 2, photo.size[1] // 2), Image.BILINEAR)
r, g, b = small.split()
near_white = ImageChops.multiply(ImageChops.multiply(*(c.point(lambda v: 255 if v > 236 else 0) for c in (r, g))),
                                 b.point(lambda v: 255 if v > 236 else 0))
fill = near_white.copy()
for seed in [(0, 0), (small.size[0] - 1, 0), (0, small.size[1] - 1), (small.size[0] - 1, small.size[1] - 1)]:
    ImageDraw.floodfill(fill, seed, 128)
body = fill.point(lambda v: 0 if v == 128 else 255).filter(ImageFilter.MinFilter(3))
body = body.resize(photo.size, Image.BICUBIC).filter(ImageFilter.GaussianBlur(2.0))
body = body.point(lambda v: max(0, min(255, round((v - 140) * 2.5 + 128))))
box = body.point(lambda v: 255 if v > 128 else 0).getbbox()
# ---------------- labels set again ----------------
# The enlargement garbles the small lettering, so the labels above the keys
# are removed and set again with the calculator's real legends, in the same
# place and colour. Everything in this part is in photo pixels.

def X(v):
    return v * k - ORIGIN[0] * SCALE


GOLD, RED = (126, 96, 44), (166, 58, 44)       # labels on the silver front
PANEL_GOLD = (216, 184, 116)                   # labels on the black panel
ARROW = (132, 134, 140)
SANS, MATH, SYMBOL, SERIF = "seguisb.ttf", "cambriai.ttf", "seguisym.ttf", "georgiab.ttf"
_fonts = {}


def font(name, size):
    if (name, size) not in _fonts:
        _fonts[name, size] = ImageFont.truetype(os.path.join(FONTS, name), size)
    return _fonts[name, size]


def erase(x0, y0, x1, y1, on="silver"):
    """Remove the lettering in a box: its pixels are refilled from the
    background to the left and right of them."""
    x0, y0, x1, y1 = (int(round(v)) for v in (x0, y0, x1, y1))
    pad = 24
    a = np.asarray(photo.crop((x0 - pad, y0, x1 + pad, y1))).astype(float)
    lum = a.mean(axis=2)
    sat = a.max(axis=2) - a.min(axis=2)
    if on == "panel":
        ink = (lum > np.percentile(lum, 30) + 20) | (sat > 40)
    elif on == "pad":
        ink = lum < np.percentile(lum, 75) - 22
    else:               # coloured or clearly darker; the grey shadow of the keys above stays
        ink = (sat > 16) | (lum < np.percentile(lum, 75) - 50)
        ink[:12] &= sat[:12] > 16
    ink[:, :pad] = False
    ink[:, -pad:] = False
    ink = ndimage.binary_dilation(ink, iterations=5)
    keep = (~ink).astype(float)
    sigma = (2.5, 16)
    weight = np.maximum(ndimage.gaussian_filter(keep, sigma), 1e-6)
    fill = np.dstack([ndimage.gaussian_filter(a[:, :, c] * keep, sigma) / weight for c in range(3)])
    soft = ndimage.gaussian_filter(ink.astype(float), 1.5)[:, :, None]
    out = a * (1 - soft) + fill * soft
    photo.paste(Image.fromarray(out.clip(0, 255).astype("uint8")).crop((pad, 0, pad + x1 - x0, y1 - y0)), (x0, y0))


def label(parts, x, base, colour, align="l", squeeze=1.0):
    """Set a label with its baseline at `base`. `parts` is a text, a list of
    (text, font file, size, raise), or a small drawing. Drawn large and
    scaled down, so the edges stay smooth."""
    if callable(parts):
        parts(x, base, colour)
        return
    if isinstance(parts, str):
        parts = [(parts, SANS, 42, 0)]
    q = 3
    widths = [font(f, size * q).getlength(t) for t, f, size, _ in parts]
    tile = Image.new("L", (int(sum(widths)) + 8 * q, 84 * q), 0)
    d = ImageDraw.Draw(tile)
    tx = 2 * q
    for (t, f, size, up), w in zip(parts, widths):
        d.text((tx, (60 - up) * q), t, font=font(f, size * q), fill=255, anchor="ls")
        tx += w
    tile = tile.resize((max(1, round(tile.size[0] / q * squeeze)), tile.size[1] // q), Image.LANCZOS)
    width = sum(widths) / q * squeeze
    left = x if align == "l" else x - width if align == "r" else x - width / 2
    photo.paste(Image.new("RGB", tile.size, colour), (round(left - 2 * squeeze), round(base) - 60), tile)


def sup(text, exponent, italic=False):
    return [(text, SANS, 40, 0), (exponent, MATH if italic else SANS, 27, 15)]


def drawing(fn, w=64, h=48):
    """A small symbol (w x h, bottom edge 4 px below the baseline), drawn large and scaled down."""
    def paint(x, base, colour):
        q = 4
        tile = Image.new("L", (w * q, h * q), 0)
        fn(ImageDraw.Draw(tile), q)
        tile = tile.resize((w, h), Image.LANCZOS)
        photo.paste(Image.new("RGB", tile.size, colour), (round(x), round(base) - h + 4), tile)
    return paint


def icon_mixed(d, q):      # mixed fraction: filled square, then a fraction of two boxes
    d.rectangle([2 * q, 20 * q, 16 * q, 34 * q], fill=255)
    for y in (4, 31):
        d.rectangle([24 * q, y * q, 46 * q, (y + 14) * q], outline=255, width=round(2.6 * q))
    d.line([22 * q, 24.5 * q, 48 * q, 24.5 * q], fill=255, width=round(2.6 * q))


def icon_fractions(d, q):  # a b/c <-> d/c
    d.text((0, 34 * q), "a", font=font(SANS, 26 * q), fill=255, anchor="ls")
    for x, top in ((24, "b"), (88, "d")):
        d.text((x * q, 21 * q), top, font=font(SANS, 21 * q), fill=255, anchor="ms")
        d.line([(x - 8) * q, 25 * q, (x + 8) * q, 25 * q], fill=255, width=round(2.2 * q))
        d.text((x * q, 44 * q), "c", font=font(SANS, 21 * q), fill=255, anchor="ms")
    d.text((56 * q, 35 * q), "↔", font=font(SYMBOL, 26 * q), fill=255, anchor="ms")


def icon_root3(d, q):      # cube root
    d.text((0, 22 * q), "3", font=font(SANS, 19 * q), fill=255, anchor="ls")
    d.text((10 * q, 44 * q), "√", font=font(SANS, 40 * q), fill=255, anchor="ls")
    d.line([31 * q, 11 * q, 50 * q, 11 * q], fill=255, width=round(2.6 * q))


def icon_boxes(d, q):      # two boxes joined by an arc (shape taken from the photo)
    for x in (2, 36):
        d.rectangle([x * q, 24 * q, (x + 24) * q, 42 * q], outline=255, width=round(3 * q))
    d.arc([14 * q, 8 * q, 48 * q, 40 * q], 180, 360, fill=255, width=round(3 * q))


def icon_stack(d, q):      # box with an arc on top, a filled box in front of it (shape taken from the photo)
    d.rectangle([2 * q, 22 * q, 30 * q, 42 * q], outline=255, width=round(3 * q))
    d.arc([8 * q, 6 * q, 32 * q, 38 * q], 180, 360, fill=255, width=round(3 * q))
    d.rectangle([22 * q, 28 * q, 48 * q, 46 * q], fill=255)


later = []      # labels are set after everything has been erased


def put(*args):
    later.append(args)


ROWS6 = [  # baseline, [(SHIFT legend, ALPHA legend)] for the rows of six keys
    (2179, [([("∠", SYMBOL, 40, 0)], "A"), (sup("10", "x", True), "B"), (sup("e", "x", True), "C"),
            (sup("sin", "-1"), "D"), (sup("cos", "-1"), "E"), (sup("tan", "-1"), "F")]),
    (2369, [(drawing(icon_mixed), "G"), (drawing(icon_fractions, 104), "H"), (drawing(icon_root3), "I"),
            ([("x", MATH, 44, 0), ("-1", SANS, 27, 15)], "J"), (drawing(icon_boxes), "K"), (drawing(icon_stack), "L")]),
]
ROWS5 = [  # baseline, [(SHIFT legend, ALPHA legend, offset of the SHIFT legend or "c" for centred)]
    (2577, [("CAPTURE", "M", 0), ("CLIP", "N", 0), ("PASTE", "O", 0), ("INS", "UNDO", 6), ("OFF", "", "c")]),
    (2800, [("CATALOG", "P", 0), ("", "Q", 0), ("", "R", 0), ("{", "S", 22), ("}", "T", 36)]),
    (3027, [("List", "U", 6), ("Mat", "V", 6), ("", "W", 0), ("[", "X", 24), ("]", "Y", 30)]),
    (3249, [([("i", MATH, 44, 0)], "Z", 24), ("=", "SPACE", 22), ([("π", MATH, 46, 0)], [("”", SERIF, 58, -16)], 18),
            ("Ans", "", "c"), ([("↵", SYMBOL, 58, -4)], "", "c")]),
]
for base, row in ROWS6:
    for cx, (shift, alpha) in zip(SIX, row):
        x0, x1 = X(cx - 44.7), X(cx + 44.7)
        erase(x0 - 26, base - 56, x1 + 10, base + 11)
        put(shift, x0 + 4, base, GOLD, "l", 0.92)
        put(alpha, x1 - 6, base, RED, "r")
for base, row in ROWS5:
    for cx, (shift, alpha, off) in zip(FIVE, row):
        x0, x1 = X(cx - 55), X(cx + 55)
        erase(x0 - 26, base - 46, x1 + 16, base + 11)
        caps = isinstance(shift, str) and shift.isupper()
        if off == "c":
            put(shift, (x0 + x1) / 2, base, GOLD, "c", 0.86 if caps else 0.95)
        elif shift:
            put(shift, x0 - 10 + off, base, GOLD, "l", 0.80 if caps else 0.95)
        if alpha:
            put(alpha, x1 - 8, base, RED, "r", 0.86 if alpha in ("UNDO", "SPACE") else 1.0)

# Names above the F-keys, on the black panel
for cx, name in zip([700, 805, 910, 1016, 1122, 1228], ["Trace", "Zoom", "V-Window", "Sketch", "G-Solv", "G↔T"]):
    erase(X(cx - 60), 1392, X(cx + 60), 1450, "panel")
    parts = [(name, SANS, 40, 0)] if "↔" not in name else [("G", SANS, 40, 0), ("↔", SYMBOL, 34, 2), ("T", SANS, 40, 0)]
    put(parts, X(cx), 1438, PANEL_GOLD, "c", 0.9)
for args in later:
    label(*args)

# REPLAY arrows: small outlined triangles
cxp, cyp = X(PX), PY * k - ORIGIN[1] * SCALE
for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0)):
    ax, ay = cxp + dx * 160, cyp + dy * 160
    erase(ax - 34, ay - 30, ax + 34, ay + 30, "pad")
    q = 4
    tile = Image.new("L", (60 * q, 60 * q), 0)
    tip = (30 + dx * 13, 30 + dy * 13)
    back = [(30 - dx * 9 + dy * 12, 30 - dy * 9 + dx * 12), (30 - dx * 9 - dy * 12, 30 - dy * 9 - dx * 12)]
    ImageDraw.Draw(tile).polygon([(v[0] * q, v[1] * q) for v in [tip] + back], outline=255, width=round(2.4 * q))
    tile = tile.resize((60, 60), Image.LANCZOS)
    photo.paste(Image.new("RGB", tile.size, ARROW), (round(ax) - 30, round(ay) - 30), tile)

# The photo shows a lit screen; blank it, the app draws the real display there.
blank = Image.new("L", photo.size, 0)
ImageDraw.Draw(blank).rectangle([GLASS[0] * k - ORIGIN[0] * SCALE, GLASS[1] * k - ORIGIN[1] * SCALE,
                                 GLASS[2] * k - ORIGIN[0] * SCALE, GLASS[3] * k - ORIGIN[1] * SCALE], fill=255)
photo.paste(Image.new("RGB", photo.size, LCD_OFF), (0, 0), blank.filter(ImageFilter.GaussianBlur(1.2)))
skin = photo.convert("RGBA")
skin.putalpha(body)
skin = skin.crop(box)
skin.save(os.path.join(OUT, "skin.webp"), quality=92, method=6)

u = 480.0 / skin.size[0]               # layout units per photo pixel


def ux(v):
    return round((v * k - ORIGIN[0] * SCALE - box[0]) * u, 1)


def uy(v):
    return round((v * k - ORIGIN[1] * SCALE - box[1]) * u, 1)


def ul(v):
    return round(v * k * u, 1)


layout = {
    "w": 480, "h": round(skin.size[1] * u, 1),
    "lcd": [ux(LCD[0]), uy(LCD[1]), ul(LCD[2]), ul(LCD[3])],
    "glass": [ux(GLASS[0]), uy(GLASS[1]), ul(GLASS[2] - GLASS[0]), ul(GLASS[3] - GLASS[1])],
    "lcd_on": "#%02X%02X%02X" % LCD_ON, "lcd_off": "#%02X%02X%02X" % LCD_OFF,
    "lcd_on_lit": "#%02X%02X%02X" % LCD_ON_LIT, "lcd_off_lit": "#%02X%02X%02X" % LCD_OFF_LIT,
    "menu": [ux(MENU[0]), uy(MENU[1]), ul(MENU[2]), ul(MENU[3])],
    "badge": [ux(BADGE[0]), uy(BADGE[1])],
    "pop": [ux(POP[0]), uy(POP[1]), ul(POP[2])],
    "keys": [[c, n, ux(x0), uy(y0), ux(x1), uy(y1)] for c, n, x0, y0, x1, y1 in keys],
}
json.dump(layout, open(os.path.join(OUT, "layout.json"), "w"), indent=1)
print("skin written:", skin.size, "layout", layout["w"], "x", layout["h"], len(keys), "keys")

if len(sys.argv) > 3:                  # check picture: all areas drawn over the skin
    s = skin.size[0] / 480.0
    prev = Image.new("RGBA", skin.size, (17, 22, 28, 255))
    prev.alpha_composite(skin)
    d = ImageDraw.Draw(prev, "RGBA")
    gx, gy, gw, gh = layout["glass"]
    d.rectangle([gx * s, gy * s, (gx + gw) * s, (gy + gh) * s], fill=LCD_OFF + (255,))
    lx, ly, lw, lh = layout["lcd"]
    d.rectangle([lx * s, ly * s, (lx + lw) * s, (ly + lh) * s], outline=(255, 0, 0, 255))
    for _, _, x0, y0, x1, y1 in layout["keys"]:
        d.rectangle([x0 * s, y0 * s, x1 * s, y1 * s], outline=(255, 0, 200, 255), width=2)
    mx, my, mw, mh = layout["menu"]
    d.rectangle([mx * s, my * s, (mx + mw) * s, (my + mh) * s], outline=(0, 255, 255, 255), width=2)
    prev.convert("RGB").save(sys.argv[3])
