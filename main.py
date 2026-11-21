#!/usr/bin/env python3
"""One-image summary of world news, Friday 20 November 2026.

Renders a 1024x1024 newspaper front page from news.json and writes it to
/output/entry.png (or ./entry.png when /output does not exist).

Standard library only. Text is typeset from embedded font data
(fontdata.py): glyphs rasterized from Noto fonts (OFL) at fixed pixel
sizes, so the program needs no font files at run time. The output is
fully deterministic: run it twice, get identical bytes.
"""

import json
import os
import struct
import sys
import zlib

import fontdata

W = 1024
H = 1024
MARGIN = 28
CONTENT = W - 2 * MARGIN  # 968

# --- palette ---------------------------------------------------------------
PAPER = (250, 246, 236)
INK = (26, 26, 26)
RED = (178, 34, 34)
DARKRED = (120, 20, 20)
GRAY = (110, 105, 95)
LIGHT = (233, 227, 211)
HAIR = (198, 190, 170)
LAND = (206, 199, 171)
WHITE = (255, 255, 255)

REGIONS = {
    "EUROPE": (30, 80, 160),
    "MIDEAST": (180, 60, 20),
    "ASIA": (0, 130, 90),
    "AMERICAS": (120, 40, 140),
    "AFRICA": (200, 140, 0),
    "OCEANIA": (0, 140, 170),
}


def tint(color, frac):
    """Mix a color toward PAPER; frac is how much PAPER to use."""
    return tuple(int(c * (1.0 - frac) + p * frac) for c, p in zip(color, PAPER))


# --- canvas ----------------------------------------------------------------
class Canvas:
    def __init__(self, w, h, bg):
        self.w = w
        self.h = h
        self.buf = bytearray(bg * (w * h))

    def set(self, x, y, color):
        if 0 <= x < self.w and 0 <= y < self.h:
            i = (y * self.w + x) * 3
            self.buf[i] = color[0]
            self.buf[i + 1] = color[1]
            self.buf[i + 2] = color[2]

    def fill_rect(self, x, y, w, h, color):
        x0 = max(0, x)
        y0 = max(0, y)
        x1 = min(self.w, x + w)
        y1 = min(self.h, y + h)
        if x1 <= x0 or y1 <= y0:
            return
        row = bytes(color) * (x1 - x0)
        for yy in range(y0, y1):
            i = (yy * self.w + x0) * 3
            self.buf[i:i + len(row)] = row

    def hline(self, x, y, w, color, thick=1):
        self.fill_rect(x, y, w, thick, color)

    def vline(self, x, y, h, color, thick=1):
        self.fill_rect(x, y, thick, h, color)

    def outline(self, x, y, w, h, color, thick=1):
        self.fill_rect(x, y, w, thick, color)
        self.fill_rect(x, y + h - thick, w, thick, color)
        self.fill_rect(x, y, thick, h, color)
        self.fill_rect(x + w - thick, y, thick, h, color)

    def line(self, x0, y0, x1, y1, color):
        dx = abs(x1 - x0)
        sx = 1 if x0 < x1 else -1
        dy = -abs(y1 - y0)
        sy = 1 if y0 < y1 else -1
        err = dx + dy
        while True:
            self.set(x0, y0, color)
            if x0 == x1 and y0 == y1:
                return
            e2 = 2 * err
            if e2 >= dy:
                err += dy
                x0 += sx
            if e2 <= dx:
                err += dx
                y0 += sy

    def thick_line(self, x0, y0, x1, y1, color):
        self.line(x0, y0, x1, y1, color)
        self.line(x0 + 1, y0, x1 + 1, y1, color)
        self.line(x0, y0 + 1, x1, y1 + 1, color)

    def disc(self, cx, cy, rad, color):
        for yy in range(cy - rad, cy + rad + 1):
            dy = yy - cy
            dx = int((rad * rad - dy * dy) ** 0.5)
            self.fill_rect(cx - dx, yy, dx * 2 + 1, 1, color)

    def ring(self, cx, cy, rad, thick, color):
        outer = rad * rad
        inner = (rad - thick) * (rad - thick)
        for yy in range(cy - rad, cy + rad + 1):
            for xx in range(cx - rad, cx + rad + 1):
                d2 = (xx - cx) * (xx - cx) + (yy - cy) * (yy - cy)
                if inner <= d2 <= outer:
                    self.set(xx, yy, color)

    def fill_poly(self, pts, color):
        ys = [p[1] for p in pts]
        n = len(pts)
        for y in range(min(ys), max(ys) + 1):
            xs = []
            for i in range(n):
                x1, y1 = pts[i]
                x2, y2 = pts[(i + 1) % n]
                if (y1 <= y < y2) or (y2 <= y < y1):
                    t = (y - y1) / (y2 - y1)
                    xs.append(x1 + t * (x2 - x1))
            xs.sort()
            for i in range(0, len(xs) - 1, 2):
                xa = int(xs[i])
                xb = int(xs[i + 1])
                self.fill_rect(xa, y, xb - xa + 1, 1, color)

    def blit(self, x, y, w, h, data, color):
        """Paste a grayscale coverage bitmap with alpha blending."""
        r, g, b = color
        buf = self.buf
        for row in range(h):
            yy = y + row
            if yy < 0 or yy >= self.h:
                continue
            dbase = row * w
            for col in range(w):
                xx = x + col
                if xx < 0 or xx >= self.w:
                    continue
                cov = data[dbase + col]
                if cov == 0:
                    continue
                i = (yy * self.w + xx) * 3
                if cov == 255:
                    buf[i] = r
                    buf[i + 1] = g
                    buf[i + 2] = b
                else:
                    inv = 255 - cov
                    buf[i] = (r * cov + buf[i] * inv + 127) // 255
                    buf[i + 1] = (g * cov + buf[i + 1] * inv + 127) // 255
                    buf[i + 2] = (b * cov + buf[i + 2] * inv + 127) // 255


# --- typeset text ----------------------------------------------------------
class Font:
    """A rasterized font: glyphs are (w, h, dx, dy, adv, bytes)."""

    def __init__(self, spec):
        self.ascent, self.descent, self.glyphs = spec
        self.height = self.ascent + self.descent

    def width(self, s):
        total = 0
        for ch in s:
            total += self.glyphs[ord(ch)][4]
        return total

    def draw(self, cv, x, y, s, color):
        """Draw at (x, y); y is the top of the ascender line."""
        pen = x
        for ch in s:
            w, h, dx, dy, adv, data = self.glyphs[ord(ch)]
            if w and h:
                cv.blit(pen + dx, y + dy, w, h, data, color)
            pen += adv
        return pen - x

    def draw_centered(self, cv, cx, y, s, color):
        self.draw(cv, cx - self.width(s) // 2, y, s, color)


def wrap(text, font, max_w):
    """Greedy word wrap by measured width. Returns a list of lines."""
    words = text.split(" ")
    lines = []
    cur = ""
    for word in words:
        trial = word if not cur else cur + " " + word
        if font.width(trial) <= max_w:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            # A single word too wide: hard-split it by characters.
            while font.width(word) > max_w:
                cut = 1
                while cut < len(word) and font.width(word[:cut + 1]) <= max_w:
                    cut += 1
                lines.append(word[:cut])
                word = word[cut:]
            cur = word
    if cur:
        lines.append(cur)
    return lines


# --- icons (flat pictograms, 56x56 box at bx, by) --------------------------
def icon_rocket(cv, bx, by):
    cv.fill_poly([(bx + 22, by + 12), (bx + 34, by + 12), (bx + 28, by + 2)],
                 INK)
    cv.fill_rect(bx + 22, by + 12, 12, 26, INK)
    cv.disc(bx + 28, by + 20, 3, WHITE)
    cv.fill_poly([(bx + 22, by + 30), (bx + 16, by + 42), (bx + 22, by + 38)],
                 RED)
    cv.fill_poly([(bx + 34, by + 30), (bx + 40, by + 42), (bx + 34, by + 38)],
                 RED)
    cv.fill_poly([(bx + 24, by + 38), (bx + 32, by + 38), (bx + 28, by + 50)],
                 (230, 120, 0))


def icon_chart(cv, bx, by):
    cv.vline(bx + 8, by + 8, 40, INK, 2)
    cv.hline(bx + 8, by + 46, 40, INK, 2)
    pts = [(bx + 12, by + 14), (bx + 21, by + 22), (bx + 29, by + 18),
           (bx + 38, by + 34), (bx + 47, by + 42)]
    for a, b in zip(pts, pts[1:]):
        cv.thick_line(a[0], a[1], b[0], b[1], RED)
    cv.fill_poly([(bx + 47, by + 42), (bx + 41, by + 40), (bx + 45, by + 47)],
                 RED)


def icon_podium(cv, bx, by):
    cv.fill_poly([(bx + 16, by + 50), (bx + 40, by + 50), (bx + 36, by + 28),
                  (bx + 20, by + 28)], INK)
    cv.fill_rect(bx + 14, by + 24, 28, 4, INK)
    cv.vline(bx + 28, by + 12, 12, INK, 2)
    cv.disc(bx + 28, by + 10, 4, RED)
    cv.fill_rect(bx + 24, by + 36, 8, 2, WHITE)
    cv.fill_rect(bx + 24, by + 41, 8, 2, WHITE)


def icon_rings(cv, bx, by):
    cv.ring(bx + 20, by + 28, 13, 4, (30, 80, 160))
    cv.ring(bx + 36, by + 28, 13, 4, RED)


ICONS = {
    "rocket": icon_rocket,
    "chart": icon_chart,
    "podium": icon_podium,
    "rings": icon_rings,
}

# Big stat figure per headline card, in story order.
STATS = ["8 KILLED", "-5.2%", "90 MIN", "EU-UK"]


# --- map -------------------------------------------------------------------
# Simplified continent outlines as (lon, lat) polygons.
CONTINENTS = [
    [(-168, 66), (-140, 70), (-125, 72), (-110, 68), (-95, 69), (-85, 66),
     (-75, 62), (-60, 58), (-55, 52), (-65, 45), (-75, 35), (-80, 25),
     (-90, 21), (-97, 16), (-105, 20), (-115, 30), (-125, 40), (-125, 49),
     (-135, 58), (-155, 58), (-165, 60)],
    [(-80, 10), (-75, 11), (-62, 10), (-52, 5), (-35, -8), (-38, -15),
     (-48, -27), (-58, -38), (-65, -45), (-70, -52), (-73, -40), (-73, -30),
     (-70, -20), (-77, -12), (-81, -6), (-80, 2)],
    [(-17, 15), (-10, 31), (10, 37), (20, 32), (32, 31), (35, 27),
     (43, 12), (51, 11), (48, 2), (40, -5), (35, -18), (32, -28),
     (20, -35), (15, -28), (12, -18), (9, -1), (9, 4), (-8, 4), (-13, 8)],
    [(-10, 36), (-9, 43), (-2, 49), (0, 53), (8, 57), (10, 59), (18, 56),
     (21, 55), (24, 58), (28, 60), (30, 70), (40, 68), (50, 69), (60, 69),
     (70, 72), (80, 73), (90, 75), (110, 74), (130, 72), (150, 70),
     (170, 67), (178, 65), (170, 60), (162, 56), (158, 52), (142, 50),
     (140, 40), (130, 33), (122, 30), (120, 23), (110, 20), (105, 10),
     (100, 8), (98, 12), (95, 16), (90, 22), (85, 20), (80, 15), (77, 8),
     (73, 20), (66, 25), (60, 25), (56, 27), (52, 26), (48, 30), (44, 29),
     (40, 36), (36, 36), (30, 36), (22, 37), (15, 38), (10, 44), (3, 43),
     (-2, 37), (-9, 37)],
    [(113, -22), (114, -30), (118, -35), (125, -33), (129, -32), (132, -32),
     (135, -35), (140, -38), (145, -38), (150, -37), (153, -32),
     (153, -27), (146, -19), (142, -15), (142, -11), (137, -12),
     (132, -12), (126, -14), (122, -17), (118, -20)],
    [(-5, 50), (-3, 53), (-5, 56), (-3, 58), (-1, 57), (1, 52), (1, 51),
     (-3, 50)],
    [(130, 31), (133, 34), (137, 35), (140, 36), (141, 39), (142, 42),
     (145, 44), (143, 42), (140, 38), (138, 35), (134, 33), (131, 32)],
    [(167, -45), (170, -43), (173, -39), (175, -37), (178, -38),
     (175, -41), (172, -44)],
]

MAP_X = 28
MAP_W = 216
MAP_Y = 766
MAP_H = 134


def project(lon, lat):
    x = MAP_X + (lon + 180) * MAP_W / 360.0
    y = MAP_Y + (75 - lat) * MAP_H / 130.0
    return (int(x), int(y))


# Numbered dots for the 16 featured stories (schematic positions, spread
# apart so the numbered discs do not overlap).
DOTS = [
    (1, 154, 792, "EUROPE"),
    (2, 94, 800, "AMERICAS"),
    (3, 86, 812, "AMERICAS"),
    (4, 131, 792, "EUROPE"),
    (5, 144, 808, "EUROPE"),
    (6, 167, 781, "EUROPE"),
    (7, 158, 813, "MIDEAST"),
    (8, 163, 828, "MIDEAST"),
    (9, 170, 802, "MIDEAST"),
    (10, 148, 777, "EUROPE"),
    (11, 134, 776, "EUROPE"),
    (12, 187, 823, "ASIA"),
    (13, 96, 826, "AMERICAS"),
    (14, 104, 790, "AMERICAS"),
    (15, 78, 824, "AMERICAS"),
    (16, 63, 804, "AMERICAS"),
]


# --- png (stdlib encoder) --------------------------------------------------
def write_png(path, cv):
    raw = bytearray()
    stride = W * 3
    for y in range(H):
        raw.append(0)
        raw += cv.buf[y * stride:(y + 1) * stride]

    def chunk(kind, data):
        c = struct.pack(">I", len(data)) + kind + data
        return c + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", W, H, 8, 2, 0, 0, 0)
    png = (b"\x89PNG\r\n\x1a\n"
           + chunk(b"IHDR", ihdr)
           + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
           + chunk(b"IEND", b""))
    with open(path, "wb") as f:
        f.write(png)
    return len(png)


# --- layout ----------------------------------------------------------------
def render(data):
    fonts = {k: Font(v) for k, v in fontdata.load().items()}
    display = fonts["display"]
    head = fonts["head"]
    deck = fonts["deck"]
    kick = fonts["kick"]
    sechead = fonts["sechead"]
    secdeck = fonts["secdeck"]
    listf = fonts["tiny"]
    foot = fonts["foot"]
    stat = fonts["stat"]
    tiny = fonts["tiny"]

    cv = Canvas(W, H, PAPER)
    day = data["title"].split(" ")[0]

    # Masthead kicker row.
    y = 16
    kick.draw(cv, MARGIN, y, "ONE DAY. ONE PICTURE. THE WORLD.", RED)
    right = "%d STORIES \u00b7 %d REGIONS \u00b7 ALL FROM THIS %s" % (
        data["stories_total"], data["regions"], day)
    kick.draw(cv, W - MARGIN - kick.width(right), y, right, INK)

    # Big date title in high-contrast display serif.
    title = data["title"]
    tw = display.width(title)
    assert tw <= CONTENT, "title too wide: %d" % tw
    display.draw(cv, (W - tw) // 2, 34, title, INK)

    # Double rule under the title.
    cv.hline(MARGIN, 124, CONTENT, INK, 3)
    cv.hline(MARGIN, 129, CONTENT, INK, 1)

    # UTC timeline.
    y = 136
    cv.fill_rect(MARGIN, y, 112, 58, DARKRED)
    kick.draw_centered(cv, MARGIN + 56, y + 10, "THE DAY", WHITE)
    kick.draw_centered(cv, MARGIN + 56, y + 28, "IN UTC", WHITE)
    seg_x = 150
    seg_w = (W - MARGIN - seg_x) // 6
    for i, (label, lines) in enumerate(data["timeline"]):
        sx = seg_x + i * seg_w
        if i:
            cv.vline(sx - 5, y + 2, 54, HAIR, 1)
        kick.draw(cv, sx + 4, y + 2, label, RED)
        ly = y + 18
        for line in lines:
            secdeck.draw(cv, sx + 4, ly, line, INK)
            ly += 13
    y = 202

    # Four headline cards across.
    card_y = y
    card_h = 240
    col_w = 234
    for i, story in enumerate(data["headlines"]):
        x = MARGIN + i * (col_w + 10)
        w = col_w if i < 3 else W - MARGIN - x
        region = story["region"]
        color = REGIONS[region]
        cv.fill_rect(x, card_y, w, 4, color)
        # Icon panel with the big stat figure.
        panel_y = card_y + 8
        cv.fill_rect(x, panel_y, w, 56, tint(color, 0.88))
        ICONS[story["icon"]](cv, x + 6, panel_y)
        stat.draw(cv, x + 68, panel_y + 10, STATS[i], color)
        # Kicker.
        kicker = "%d \u00b7 %s \u00b7 %s" % (i + 1, region, story["topic"])
        kick.draw(cv, x + 2, panel_y + 66, kicker, color)
        # Headline, wrapped by measured width.
        inner = w - 20
        title_lines = wrap(" ".join(story["title"]), head, inner)
        assert len(title_lines) <= 3, "headline too long: %r" % title_lines
        hy = panel_y + 86
        for line in title_lines:
            head.draw(cv, x + 2, hy, line, INK)
            hy += 25
        # Deck.
        deck_lines = wrap(" ".join(story["summary"]), deck, inner)
        assert len(deck_lines) <= 3, "deck too long: %r" % deck_lines
        dy = hy + 6
        for line in deck_lines:
            deck.draw(cv, x + 2, dy, line, INK)
            dy += 16
        # Source tag, pinned to the card bottom.
        tiny.draw(cv, x + 2, card_y + card_h - 16, story["status"], GRAY)
    y = card_y + card_h + 8

    # Twelve secondary cards: two rows of six.
    sec_w = 153
    sec_h = 140
    for row in range(2):
        for col in range(6):
            i = row * 6 + col
            story = data["secondary"][i]
            x = MARGIN + col * (sec_w + 10)
            cy = y + row * (sec_h + 8)
            region = story["region"]
            color = REGIONS[region]
            cv.fill_rect(x, cy, sec_w, 3, color)
            tag = "%d \u00b7 %s" % (i + 5, region)
            kick.draw(cv, x + 2, cy + 8, tag, color)
            inner = sec_w - 12
            title_lines = wrap(" ".join(story["title"]), sechead, inner)
            assert len(title_lines) <= 3, "sec headline: %r" % title_lines
            hy = cy + 26
            for line in title_lines:
                sechead.draw(cv, x + 2, hy, line, INK)
                hy += 19
            deck_lines = wrap(" ".join(story["summary"]), secdeck, inner)
            assert len(deck_lines) <= 3, "sec deck: %r" % deck_lines
            dy = hy + 4
            for line in deck_lines:
                secdeck.draw(cv, x + 2, dy, line, INK)
                dy += 13
            tiny.draw(cv, x + 2, cy + sec_h - 14, story["status"], GRAY)
    y = y + 2 * sec_h + 8 + 8

    # Bottom band: map left, one-line list right.
    band_y = y
    kick.draw(cv, MARGIN, band_y, "WHERE IT HAPPENED", RED)
    list_x = 256
    kick.draw(cv, list_x, band_y, "ALSO ON FRIDAY 20 NOVEMBER", RED)
    cv.vline(250, band_y + 2, 192, HAIR, 1)
    for poly in CONTINENTS:
        cv.fill_poly([project(lon, lat) for lon, lat in poly], LAND)
    for n, dx, dy, region in DOTS:
        cv.disc(dx, dy, 7, REGIONS[region])
        num = str(n)
        tiny.draw(cv, dx - tiny.width(num) // 2, dy - 5, num, WHITE)
    # Region legend under the map.
    legend = ["EUROPE", "MIDEAST", "ASIA", "AMERICAS", "AFRICA", "OCEANIA"]
    for i, name in enumerate(legend):
        lx = MARGIN + (i % 2) * 108
        ly = 904 + (i // 2) * 13
        cv.fill_rect(lx, ly + 2, 8, 8, REGIONS[name])
        tiny.draw(cv, lx + 12, ly, name, INK)
    # The list: three columns of ten, each item wrapped to fit.
    col_w = 238
    for col in range(3):
        cx = list_x + col * (col_w + 12)
        ly = band_y + 16
        for item in data["list"][col * 10:(col + 1) * 10]:
            text = item["line1"] + " " + item["line2"]
            num = str(item["n"])
            num_w = listf.width(num + " ")
            lines = wrap(text, listf, col_w - num_w)
            assert len(lines) <= 2, "list item: %r" % lines
            listf.draw(cv, cx, ly, num, REGIONS[item["region"]])
            for j, line in enumerate(lines):
                listf.draw(cv, cx + num_w, ly + j * 11, line, INK)
            ly += len(lines) * 11 + 1
        assert ly <= band_y + 202, "list column %d too tall: %d" % (col, ly)
    y = band_y + 200

    # DATE CHECK box.
    box_y = y + 6
    cv.outline(MARGIN, box_y, CONTENT, 36, RED, 2)
    kick.draw(cv, MARGIN + 10, box_y + 11, "DATE CHECK", RED)
    check = " ".join(data["date_check"])
    check_lines = wrap(check, secdeck, W - MARGIN - 10 - (MARGIN + 130))
    assert len(check_lines) <= 2, "date check: %r" % check_lines
    cy = box_y + 5
    for line in check_lines:
        secdeck.draw(cv, MARGIN + 130, cy, line, INK)
        cy += 13
    y = box_y + 36 + 6

    # Footer, italic serif, centered.
    footer = " ".join(data["footer"])
    foot_lines = wrap(footer, foot, CONTENT)
    assert len(foot_lines) <= 2, "footer: %r" % foot_lines
    fy = y
    for line in foot_lines:
        foot.draw_centered(cv, W // 2, fy, line, GRAY)
        fy += 12
    assert fy <= H - 4, "page overflow: %d" % fy
    return cv


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, "news.json"), encoding="utf-8") as f:
        data = json.load(f)
    cv = render(data)
    # Where the image goes: the kit's output dir when it names one, else
    # the sandbox's /output, else next to this script.
    outdir = os.environ.get("MAKEFUN_OUTPUT_DIR")
    if not outdir:
        outdir = "/output" if os.path.isdir("/output") else here
    os.makedirs(outdir, exist_ok=True)
    path = os.path.join(outdir, "entry.png")
    size = write_png(path, cv)
    print("wrote %s (%d bytes, %dx%d)" % (path, size, W, H))


if __name__ == "__main__":
    main()
