"""Draws the web app's calculator skin, modelled on the real fx-9860GII:
body tapering below the display, black side trim, black upper panel with the
LCD (backlight off), shield-shaped F-keys, pill-shaped keys. Writes web/skin@3x.png (with
transparent corners) and web/layout.json (positions in 1x units).

    python3 make_skin.py <output dir> <font dir>
"""
import json
import math
import os
import sys

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

OUT, FONTS = sys.argv[1], sys.argv[2]
W, H = 480, 1015          # 1x units
OUT_SCALE = 3             # written at 3x for high-density phone screens
SS = 2                    # drawn at twice that and scaled down, for smooth edges
S = OUT_SCALE * SS
CX = W / 2

# --- colours, taken from the product photo ---
SHELL = (44, 46, 51)
SILVER_TOP, SILVER_BOTTOM = (220, 222, 224), (198, 200, 203)
PANEL = (34, 34, 37)          # matte lower part of the black panel
HOUSING = (12, 12, 14)        # glossy display housing
LCD_ON, LCD_OFF = (42, 46, 40), (183, 191, 168)   # backlight off
LCD_ON_LIT, LCD_OFF_LIT = (18, 24, 44), (164, 202, 240)   # backlight on (SHIFT + OPTN)
BRAND = (52, 54, 58)
PANEL_LABEL = (204, 178, 128)
GOLD = (170, 128, 62)
RED = (176, 70, 58)

STYLES = {  # face, lip (the darker edge below), text
    "fkey": ((190, 192, 196), (112, 114, 118), (255, 255, 255)),
    "shift": ((216, 178, 72), (128, 100, 34), (255, 255, 255)),
    "alpha": ((216, 100, 58), (126, 52, 28), (255, 255, 255)),
    "menu": ((150, 156, 172), (86, 90, 104), (255, 255, 255)),
    "dark": ((46, 47, 50), (8, 8, 10), (246, 246, 246)),
    "light": ((246, 246, 244), (150, 152, 156), (58, 60, 64)),
    "grey": ((180, 182, 186), (108, 110, 114), (48, 50, 54)),
    "exe": ((188, 186, 234), (118, 116, 170), (40, 44, 120)),
}


def font(name, size):
    return ImageFont.truetype(os.path.join(FONTS, name), round(size * S))


img = Image.new("RGBA", (W * S, H * S), (0, 0, 0, 0))
d = ImageDraw.Draw(img)


def pts(points):
    return [(x * S, y * S) for x, y in points]


def text(x, y, s, f, fill, anchor="mm"):
    d.text((x * S, y * S), s, font=f, fill=fill, anchor=anchor)


def smooth(ctrl, y, ease=True):
    """Value at height y between the control points [(y, value), ...]: eased, or straight lines."""
    if y <= ctrl[0][0]:
        return ctrl[0][1]
    for (y0, a), (y1, b) in zip(ctrl, ctrl[1:]):
        if y <= y1:
            t = (y - y0) / (y1 - y0)
            if ease:
                t = t * t * (3 - 2 * t)
            return a + (b - a) * t
    return ctrl[-1][1]


def outline(half, y0, y1, r_top, r_bot):
    """Polygon of a symmetric shape with half-width half(y) and rounded corners."""
    right = []
    y = y0
    while y <= y1 + 1e-6:
        hw = half(y)
        if y - y0 < r_top:
            k = r_top - (y - y0)
            hw -= r_top - math.sqrt(max(0.0, r_top * r_top - k * k))
        if y1 - y < r_bot:
            k = r_bot - (y1 - y)
            hw -= r_bot - math.sqrt(max(0.0, r_bot * r_bot - k * k))
        right.append((CX + hw, y))
        y += 0.5
    return right + [(2 * CX - x, yy) for x, yy in reversed(right)]


def fill_gradient(poly, top, bottom):
    """Fill a polygon with a vertical gradient."""
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).polygon(pts(poly), fill=255)
    grad = Image.new("RGBA", (1, img.size[1]))
    for yy in range(img.size[1]):
        t = yy / (img.size[1] - 1)
        grad.putpixel((0, yy), tuple(round(a + (b - a) * t) for a, b in zip(top, bottom)) + (255,))
    img.paste(grad.resize(img.size), (0, 0), mask)


def poly_mask(poly):
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).polygon(pts(poly), fill=255)
    return mask


def bevel(poly, depth, strength):
    """Darken a shape towards its edges, so it reads as a rounded surface."""
    mask = poly_mask(poly)
    small = mask.resize((img.size[0] // 4, img.size[1] // 4), Image.BILINEAR)
    soft = small.filter(ImageFilter.GaussianBlur(depth * S / 4)).resize(img.size, Image.BILINEAR)
    edge = ImageChops.multiply(mask, ImageChops.invert(soft)).point(lambda v: min(255, round(v * 2 * strength)))
    img.paste(Image.new("RGBA", img.size, (60, 62, 68, 255)), (0, 0), edge)


def shade(c, k):
    return tuple(max(0, min(255, round(v * k))) for v in c)


# --- body: full width around the display, then one straight, gentle taper
# down to the lower keyboard. The silver faceplate pulls in below the panel
# and runs straight back out to the bottom, which leaves the black shell
# visible as a trim on both sides. ---
SHELL_CTRL = [(0, 240), (300, 240), (640, 221), (1015, 221)]


def shell_hw(y):
    return smooth(SHELL_CTRL, y, ease=False)


def face_hw(y):
    if y <= 606:
        return shell_hw(y) - smooth([(0, 0), (520, 0), (606, 18)], y)
    return shell_hw(y) - smooth([(606, 18), (1015, 2)], y, ease=False)


d.polygon(pts(outline(shell_hw, 0, H, 46, 58)), fill=SHELL)
FACE = outline(face_hw, 0, 1013, 46, 56)
fill_gradient(FACE, SILVER_TOP, SILVER_BOTTOM)
bevel(FACE, 9, 0.55)

# Brand
x = 44
f_brand = font("DejaVuSans-Bold.ttf", 21)
for ch in "CASIO":
    text(x, 41, ch, f_brand, BRAND, "ls")
    x += d.textlength(ch, font=f_brand) / S + 1.2
model = Image.new("RGBA", (round(130 * S), round(30 * S)), (0, 0, 0, 0))
ImageDraw.Draw(model).text((10 * S, 22 * S), "fx-9860GII", font=font("DejaVuSerif.ttf", 15), fill=BRAND + (255,), anchor="ls")
model = model.transform(model.size, Image.AFFINE, (1, 0.25, -6 * S, 0, 1, 0), resample=Image.BICUBIC)
img.paste(model, (round(318 * S), round(19 * S)), model)

# --- black upper panel with the screen ---
PANEL_CTRL = [(68, 221), (300, 221), (598, 196)]
PANEL_POLY = outline(lambda y: smooth(PANEL_CTRL, y, ease=False), 68, 598, 28, 40)
d.polygon(pts(PANEL_POLY), fill=PANEL)


def housing(dy, colour):
    """The display housing: the top of the panel, down to a shallow curved edge."""
    edge = [(x, 350 + dy + 24 * (1 - ((x - CX) / 240) ** 2)) for x in range(0, W + 1, 4)]
    cut = poly_mask([(0, 0), (W, 0)] + list(reversed(edge)))
    img.paste(Image.new("RGBA", img.size, colour + (255,)), (0, 0), ImageChops.multiply(poly_mask(PANEL_POLY), cut))


housing(1.4, (74, 76, 82))      # light catching the lower edge
housing(0, HOUSING)
# LCD glass, a little larger than the 128x64 pixel area and in the same colour
GLASS = (30, 108, 450, 332)
LCD = (36, 118, 408, 204)           # x, y, w, h of the pixel area
d.rectangle([GLASS[0] * S, GLASS[1] * S, GLASS[2] * S - 1, GLASS[3] * S - 1], fill=LCD_OFF)

# "USB POWER GRAPHIC"
f_usb = font("DejaVuSans-BoldOblique.ttf" if os.path.exists(os.path.join(FONTS, "DejaVuSans-BoldOblique.ttf"))
             else "DejaVuSans-Bold.ttf", 11)
f_pg = font("DejaVuSans-Bold.ttf", 8.5)
usb_w = d.textlength("USB", font=f_usb) / S
pg_w = d.textlength(" POWER GRAPHIC", font=f_pg) / S
x0 = CX - (usb_w + pg_w) / 2
text(x0, 362, "USB", f_usb, (150, 152, 158), "ls")
text(x0 + usb_w, 362, " POWER GRAPHIC", f_pg, (150, 152, 158), "ls")

keys = []


def add(code, name, box):
    keys.append([code, name] + [round(v) for v in box])


def key_shape(x0, y0, x1, y1, rt, rb, bow):
    """Key outline as on the real calculator: nearly square at the top,
    round at the bottom, with a slightly bulging lower edge."""
    out = []
    for cx, cy, r, a0 in ((x0 + rt, y0 + rt, rt, 180), (x1 - rt, y0 + rt, rt, 270), (x1 - rb, y1 - rb, rb, 0)):
        out += [(cx + r * math.cos(math.radians(a0 + k)), cy + r * math.sin(math.radians(a0 + k))) for k in range(0, 91, 6)]
    mid, half = (x0 + x1) / 2, (x1 - x0) / 2 - rb
    out += [(mid + half * t / 10, y1 + bow * (1 - (t / 10) ** 2) ** 2) for t in range(9, -10, -1)]
    out += [(x0 + rb + rb * math.cos(math.radians(90 + k)), y1 - rb + rb * math.sin(math.radians(90 + k))) for k in range(0, 91, 6)]
    return out


def pill(box, style, label, f, panel=False):
    """A key with a darker lip below and a soft highlight on top."""
    face, lip, fg = STYLES[style]
    x0, y0, x1, y1 = box
    h = y1 - y0
    rt = h * (0.20 if panel or style == "dark" else 0.28)
    rb = h * (0.42 if panel else 0.47)
    bow = 1.0 if panel else 1.6
    d.polygon(pts(key_shape(x0, y0 + 3.2, x1, y1 + 3.2, rt, rb, bow)), fill=lip)
    d.polygon(pts(key_shape(x0, y0, x1, y1, rt, rb, bow)), fill=face)
    d.rounded_rectangle([(x0 + 3) * S, (y0 + 1.5) * S, (x1 - 3) * S, (y0 + h * 0.5) * S],
                        radius=max(1, rt - 1.5) * S, fill=shade(face, 1.3 if sum(face) < 200 else 1.05))
    text((x0 + x1) / 2, (y0 + y1) / 2, label, f, fg)


def shield(cx, y0, w, h, style, label, f):
    """F-key: rounded top, sides tapering to a rounded tip."""
    face, lip, fg = STYLES[style]

    def shape(dy):
        cap, tip = h * 0.30, h * 0.26
        out = []
        yy = 0.0
        while yy <= h + 1e-6:
            if yy < cap:
                hw = (w / 2) * (1 - ((cap - yy) / cap) ** 2.6) ** (1 / 2.6)
            elif yy <= h - tip:
                hw = (w / 2) * (1 - 0.40 * ((yy - cap) / (h - cap - tip)) ** 1.7)
            else:
                hw = (w / 2) * 0.60 * math.sqrt(max(0.0, 1 - ((yy - (h - tip)) / tip) ** 2))
            out.append((cx + hw, y0 + yy + dy))
            yy += 0.4
        return out + [(2 * cx - x, yy2) for x, yy2 in reversed(out)]

    d.polygon(pts(shape(3.0)), fill=lip)
    d.polygon(pts(shape(0.0)), fill=face)
    text(cx, y0 + h * 0.44, label, f, fg)


# --- F-keys ---
f_small = font("DejaVuSans-Bold.ttf", 8.5)
f_fkey = font("DejaVuSans-Bold.ttf", 13)
FX = [78, 143, 208, 272, 337, 402]
for i, (cx, lab) in enumerate(zip(FX, ["Trace", "Zoom", "V-Window", "Sketch", "G-Solv", "G↔T"])):
    text(cx, 391, lab, f_small, PANEL_LABEL)
    shield(cx, 404, 50, 52, "fkey", f"F{i + 1}", f_fkey)
    add(0x91 + i, f"F{i + 1}", (cx - 28, 400, cx + 28, 462))

# --- SHIFT / OPTN / VARS / MENU and ALPHA / x² / ^ / EXIT ---
COLS = [(54, 105), (116, 167), (178, 229), (240, 291)]
ROWS = [
    (487, 520, 476, [(0x81, "SHIFT", "SHIFT", "shift", ""), (0x82, "OPTN", "OPTN", "dark", "LIGHT"),
                     (0x83, "VARS", "VARS", "dark", "PRGM"), (0x84, "MENU", "MENU", "menu", "SET UP")]),
    (541, 574, 531, [(0x71, "ALPHA", "ALPHA", "alpha", "A-LOCK"), (0x72, "SQUARE", "x²", "dark", "√      r"),
                     (0x73, "POWER", "^", "dark", "ˣ√      θ"), (0x74, "EXIT", "EXIT", "dark", "QUIT")]),
]


def boxed(cx, cy, s):
    """A panel label in dark letters on a gold box."""
    w = d.textlength(s, font=f_small) / S + 5
    d.rounded_rectangle([(cx - w / 2) * S, (cy - 5.5) * S, (cx + w / 2) * S, (cy + 5.5) * S], radius=1.5 * S, fill=PANEL_LABEL)
    text(cx, cy, s, f_small, PANEL)


for y0, y1, ly, row in ROWS:
    for (x0, x1), (code, name, label, style, top) in zip(COLS, row):
        cx = (x0 + x1) / 2
        if top == "LIGHT":      # cyan sun, "LIGHT" on a gold box
            text(cx - 22, ly, "☀", font("DejaVuSans.ttf", 12), (96, 204, 226))
            boxed(cx + 7, ly, "LIGHT")
        elif top == "A-LOCK":   # boxed A
            boxed(cx - 18, ly, "A")
            text(cx - 12, ly, "-LOCK", f_small, PANEL_LABEL, "lm")
        elif top:
            text(cx, ly, top, f_small, PANEL_LABEL)
        pill((x0, y0, x1, y1), style, label, font("DejaVuSans-Bold.ttf", 10.5 if len(label) > 3 else 14), panel=True)
        add(code, name, (x0 - 4, y0 - 5, x1 + 4, y1 + 7))

# --- REPLAY pad ---
px, py, R = 368, 530, 56
d.ellipse([(px - R - 2.5) * S, (py - R - 2) * S, (px + R + 2.5) * S, (py + R + 4) * S], fill=(6, 6, 7))
d.ellipse([(px - R) * S, (py - R) * S, (px + R) * S, (py + R) * S], fill=(168, 170, 175))
d.ellipse([(px - R + 1.5) * S, (py - R + 1) * S, (px + R - 1.5) * S, (py + R - 3) * S], fill=(210, 212, 215))
d.ellipse([(px - R + 14) * S, (py - R + 14) * S, (px + R - 14) * S, (py + R - 14) * S], fill=(200, 202, 206))
d.ellipse([(px - R + 15) * S, (py - R + 15.5) * S, (px + R - 15) * S, (py + R - 14) * S], fill=(214, 216, 219))
text(px, py, "REPLAY", font("DejaVuSans.ttf", 9), (150, 152, 158))
for ang, (code, name) in zip((90, 270, 180, 0), [(0x86, "UP"), (0x75, "DOWN"), (0x85, "LEFT"), (0x76, "RIGHT")]):
    a = math.radians(ang)
    tx, ty = px + math.cos(a) * (R - 8), py - math.sin(a) * (R - 8)
    tri = [(tx + math.cos(a + math.radians(k)) * 4.2, ty - math.sin(a + math.radians(k)) * 4.2) for k in (0, 130, 230)]
    d.polygon(pts(tri), fill=(150, 152, 158))
    zx, zy = px + math.cos(a) * (R - 22), py - math.sin(a) * (R - 22)
    add(code, name, (zx - 23, zy - 23, zx + 23, zy + 23))

# --- lower keyboard ---
LOWER = [
    (624, 658, 614, [78, 143, 208, 272, 337, 402], 52,
     [(0x61, "XOT", "X,θ,T", "dark", "∠", "A"), (0x62, "LOG", "log", "dark", "10ˣ", "B"),
      (0x63, "LN", "ln", "dark", "eˣ", "C"), (0x64, "SIN", "sin", "dark", "sin⁻¹", "D"),
      (0x65, "COS", "cos", "dark", "cos⁻¹", "E"), (0x66, "TAN", "tan", "dark", "tan⁻¹", "F")]),
    (679, 713, 669, [78, 143, 208, 272, 337, 402], 52,
     [(0x51, "FRAC", "a b/c", "dark", "", "G"), (0x52, "FD", "F↔D", "dark", "", "H"),
      (0x53, "LEFTP", "(", "dark", "∛", "I"), (0x54, "RIGHTP", ")", "dark", "x⁻¹", "J"),
      (0x55, "COMMA", ",", "dark", "", "K"), (0x56, "ARROW", "→", "dark", "", "L")]),
    (743, 784, 731, [84, 162, 240, 318, 396], 64,
     [(0x41, "7", "7", "light", "CAPTURE", "M"), (0x42, "8", "8", "light", "CLIP", "N"),
      (0x43, "9", "9", "light", "PASTE", "O"), (0x44, "DEL", "DEL", "grey", "INS", "UNDO"),
      (0x07, "ACON", "AC/ON", "grey", "", "OFF")]),
    (808, 849, 796, [84, 162, 240, 318, 396], 64,
     [(0x31, "4", "4", "light", "CATALOG", "P"), (0x32, "5", "5", "light", "", "Q"),
      (0x33, "6", "6", "light", "", "R"), (0x34, "MUL", "×", "light", "{", "S"),
      (0x35, "DIV", "÷", "light", "}", "T")]),
    (874, 915, 862, [84, 162, 240, 318, 396], 64,
     [(0x21, "1", "1", "light", "List", "U"), (0x22, "2", "2", "light", "Mat", "V"),
      (0x23, "3", "3", "light", "", "W"), (0x24, "ADD", "+", "light", "[", "X"),
      (0x25, "SUB", "−", "light", "]", "Y")]),
    (941, 982, 929, [84, 162, 240, 318, 396], 64,
     [(0x11, "0", "0", "light", "i", "Z"), (0x12, "DOT", "•", "light", "=", "SPACE"),
      (0x13, "EXP", "EXP", "light", "π", "\""), (0x14, "NEG", "(−)", "light", "Ans", ""),
      (0x15, "EXE", "EXE", "exe", "↵", "")]),
]
f_big = font("DejaVuSans.ttf", 22)
for y0, y1, ly, centres, kw, row in LOWER:
    for cx, (code, name, label, style, sh, al) in zip(centres, row):
        x0, x1 = cx - kw / 2, cx + kw / 2
        if sh:
            text(x0 + 2, ly, sh, f_small, GOLD, "lm")
        if al:
            text(x1 - 2, ly, al, f_small, RED, "rm")
        if style in ("light", "exe") and len(label) == 1:
            f = f_big
        elif len(label) > 3:
            f = font("DejaVuSans-Bold.ttf", 11)
        else:
            f = font("DejaVuSans-Bold.ttf", 14.5)
        pill((x0, y0, x1, y1), style, label, f)
        gap = 6 if len(row) == 6 else 7
        add(code, name, (x0 - gap, y0 - 6, x1 + gap, y1 + 8))

# --- write ---
final = img.resize((W * OUT_SCALE, H * OUT_SCALE), Image.LANCZOS)
final.save(os.path.join(OUT, "skin@3x.png"), optimize=True)
layout = {
    "w": W, "h": H,
    "lcd": list(LCD),
    "glass": [GLASS[0], GLASS[1], GLASS[2] - GLASS[0], GLASS[3] - GLASS[1]],
    "lcd_on": "#%02X%02X%02X" % LCD_ON, "lcd_off": "#%02X%02X%02X" % LCD_OFF,
    "lcd_on_lit": "#%02X%02X%02X" % LCD_ON_LIT, "lcd_off_lit": "#%02X%02X%02X" % LCD_OFF_LIT,
    "menu": [398, 347, 56, 30],       # the "..." button, right of "USB POWER GRAPHIC"
    "badge": [30, 352],               # the TURBO badge, left of it
    "pop": [244, 380, 200],           # x, y, width of the pop-up menu
    "keys": keys,
}
json.dump(layout, open(os.path.join(OUT, "layout.json"), "w"), indent=1)
print("skin written:", final.size, len(keys), "keys")
