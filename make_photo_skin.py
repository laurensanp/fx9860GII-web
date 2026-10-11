"""Builds the web app's skin from a photo of the calculator instead of drawing
it: cuts the calculator out of the white background and writes
web/skin@3x.png and web/layout.json (positions in 1x units, width 480).

    python3 make_photo_skin.py <photo> <output dir> [preview.png]

The positions below are measured in the photo, in a 1932 px wide version of it.
"""
import json
import os
import sys

from PIL import Image, ImageChops, ImageDraw, ImageFilter

PHOTO, OUT = sys.argv[1], sys.argv[2]
REF = 1932.0

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
k = photo.size[0] / REF                # photo pixels per reference pixel

# Background: everything near-white that is connected to the image border.
near_white = photo.point(lambda v: 255 if v > 236 else 0).convert("L").point(lambda v: 255 if v == 255 else 0)
r, g, b = photo.split()
near_white = ImageChops.multiply(ImageChops.multiply(*(c.point(lambda v: 255 if v > 236 else 0) for c in (r, g))),
                                 b.point(lambda v: 255 if v > 236 else 0))
fill = near_white.copy()
for seed in [(0, 0), (photo.size[0] - 1, 0), (0, photo.size[1] - 1), (photo.size[0] - 1, photo.size[1] - 1)]:
    ImageDraw.floodfill(fill, seed, 128)
body = fill.point(lambda v: 0 if v == 128 else 255)
body = body.filter(ImageFilter.MinFilter(3)).filter(ImageFilter.GaussianBlur(0.8))
box = body.point(lambda v: 255 if v > 128 else 0).getbbox()
skin = photo.filter(ImageFilter.UnsharpMask(radius=1.2, percent=60, threshold=2)).convert("RGBA")
skin.putalpha(body)
skin = skin.crop(box)
skin.save(os.path.join(OUT, "skin@3x.png"), optimize=True)

u = 480.0 / skin.size[0]               # layout units per photo pixel


def ux(v):
    return round((v * k - box[0]) * u, 1)


def uy(v):
    return round((v * k - box[1]) * u, 1)


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
