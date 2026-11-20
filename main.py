#!/usr/bin/env python3
"""make.fun entry: sum up Thursday 19 November 2026 world news in one image.

Draws a one-page newspaper summary and writes a deterministic 1024x1024 PNG
to $MAKEFUN_OUTPUT_DIR/entry.png (default /output). Standard library only,
no network, no timestamps, no randomness: two runs produce identical bytes.

Layout: navy masthead with title + gold date line, two-line subline, one
full-width lead story, a 2x2 grid of four stories, one full-width climate
story, and a navy sources band. Text uses an embedded 6x8 bitmap font drawn
from scratch (see the FONT table).
"""

import json
import math
import os
import struct
import zlib

W, H = 1024, 1024

PAPER = (246, 241, 231)
INK = (26, 26, 26)
NAVY = (20, 38, 63)
GOLD = (201, 162, 39)
CARD = (255, 255, 255)
BORDER = (216, 208, 189)
GREY = (110, 110, 110)
WHITE = (255, 255, 255)
RED = (176, 58, 46)
BLUE = (46, 109, 164)
ORANGE = (230, 126, 34)
LIGHT_ORANGE = (245, 176, 65)

# 6x8 bitmap font. Each glyph is 8 rows of 6 bits, top row first.
# The lowercase 'g' is single-storey with a three-row descender tail that
# sweeps left into a wide foot; '9' keeps a straight right stem. The two
# cannot be confused (verified against a glyph test sheet).
FONT = {
    "A": ("011100", "100010", "100010", "111110", "100010", "100010", "100010", "000000"),
    "B": ("111100", "100010", "100010", "111100", "100010", "100010", "111100", "000000"),
    "C": ("011100", "100010", "100000", "100000", "100000", "100010", "011100", "000000"),
    "D": ("111100", "100010", "100010", "100010", "100010", "100010", "111100", "000000"),
    "E": ("111110", "100000", "100000", "111100", "100000", "100000", "111110", "000000"),
    "F": ("111110", "100000", "100000", "111100", "100000", "100000", "100000", "000000"),
    "G": ("011100", "100010", "100000", "101110", "100010", "100010", "011110", "000000"),
    "H": ("100010", "100010", "100010", "111110", "100010", "100010", "100010", "000000"),
    "I": ("011100", "001000", "001000", "001000", "001000", "001000", "011100", "000000"),
    "J": ("001110", "000100", "000100", "000100", "000100", "100100", "011000", "000000"),
    "K": ("100010", "100100", "101000", "110000", "101000", "100100", "100010", "000000"),
    "L": ("100000", "100000", "100000", "100000", "100000", "100000", "111110", "000000"),
    "M": ("100010", "110110", "101010", "101010", "100010", "100010", "100010", "000000"),
    "N": ("100010", "110010", "101010", "100110", "100010", "100010", "100010", "000000"),
    "O": ("011100", "100010", "100010", "100010", "100010", "100010", "011100", "000000"),
    "P": ("111100", "100010", "100010", "111100", "100000", "100000", "100000", "000000"),
    "Q": ("011100", "100010", "100010", "100010", "101010", "100100", "011010", "000000"),
    "R": ("111100", "100010", "100010", "111100", "101000", "100100", "100010", "000000"),
    "S": ("011110", "100000", "100000", "011100", "000010", "000010", "111100", "000000"),
    "T": ("111110", "001000", "001000", "001000", "001000", "001000", "001000", "000000"),
    "U": ("100010", "100010", "100010", "100010", "100010", "100010", "011100", "000000"),
    "V": ("100010", "100010", "100010", "100010", "100010", "010100", "001000", "000000"),
    "W": ("100010", "100010", "100010", "101010", "101010", "101010", "010100", "000000"),
    "X": ("100010", "100010", "010100", "001000", "010100", "100010", "100010", "000000"),
    "Y": ("100010", "100010", "010100", "001000", "001000", "001000", "001000", "000000"),
    "Z": ("111110", "000010", "000100", "001000", "010000", "100000", "111110", "000000"),
    "a": ("000000", "000000", "011100", "000010", "011110", "100010", "011110", "000000"),
    "b": ("100000", "100000", "111100", "100010", "100010", "100010", "111100", "000000"),
    "c": ("000000", "000000", "011100", "100010", "100000", "100010", "011100", "000000"),
    "d": ("000010", "000010", "011110", "100010", "100010", "100010", "011110", "000000"),
    "e": ("000000", "000000", "011100", "100010", "111110", "100000", "011100", "000000"),
    "f": ("001100", "010010", "010000", "111100", "010000", "010000", "010000", "000000"),
    "g": ("000000", "011100", "100010", "100010", "011100", "000010", "000100", "111000"),
    "h": ("100000", "100000", "111100", "100010", "100010", "100010", "100010", "000000"),
    "i": ("001000", "000000", "011000", "001000", "001000", "001000", "011100", "000000"),
    "j": ("000100", "000000", "001100", "000100", "000100", "100100", "011000", "000000"),
    "k": ("100000", "100000", "100100", "101000", "110000", "101000", "100100", "000000"),
    "l": ("011000", "001000", "001000", "001000", "001000", "001000", "011100", "000000"),
    "m": ("000000", "000000", "110100", "101010", "101010", "101010", "101010", "000000"),
    "n": ("000000", "000000", "111100", "100010", "100010", "100010", "100010", "000000"),
    "o": ("000000", "000000", "011100", "100010", "100010", "100010", "011100", "000000"),
    "p": ("000000", "000000", "111100", "100010", "100010", "111100", "100000", "100000"),
    "q": ("000000", "011100", "100010", "100010", "011100", "000010", "000010", "000010"),
    "r": ("000000", "000000", "101100", "110010", "100000", "100000", "100000", "000000"),
    "s": ("000000", "000000", "011110", "100000", "011100", "000010", "111100", "000000"),
    "t": ("010000", "010000", "111000", "010000", "010000", "010010", "001100", "000000"),
    "u": ("000000", "000000", "100010", "100010", "100010", "100110", "011010", "000000"),
    "v": ("000000", "000000", "100010", "100010", "100010", "010100", "001000", "000000"),
    "w": ("000000", "000000", "100010", "101010", "101010", "101010", "010100", "000000"),
    "x": ("000000", "000000", "100010", "010100", "001000", "010100", "100010", "000000"),
    "y": ("000000", "100010", "100010", "100010", "011110", "000010", "000100", "011000"),
    "z": ("000000", "000000", "111110", "000100", "001000", "010000", "111110", "000000"),
    "0": ("011100", "100010", "100110", "101010", "110010", "100010", "011100", "000000"),
    "1": ("001000", "011000", "001000", "001000", "001000", "001000", "011100", "000000"),
    "2": ("011100", "100010", "000010", "001100", "010000", "100000", "111110", "000000"),
    "3": ("111110", "000100", "001000", "000100", "000010", "100010", "011100", "000000"),
    "4": ("000100", "001100", "010100", "100100", "111110", "000100", "000100", "000000"),
    "5": ("111110", "100000", "111100", "000010", "000010", "100010", "011100", "000000"),
    "6": ("001100", "010000", "100000", "111100", "100010", "100010", "011100", "000000"),
    "7": ("111110", "000010", "000100", "001000", "010000", "010000", "010000", "000000"),
    "8": ("011100", "100010", "100010", "011100", "100010", "100010", "011100", "000000"),
    "9": ("011100", "100010", "100010", "011110", "000010", "000010", "011100", "000000"),
    " ": ("000000", "000000", "000000", "000000", "000000", "000000", "000000", "000000"),
    ".": ("000000", "000000", "000000", "000000", "000000", "011000", "011000", "000000"),
    ",": ("000000", "000000", "000000", "000000", "011000", "001000", "010000", "000000"),
    ":": ("000000", "011000", "011000", "000000", "011000", "011000", "000000", "000000"),
    ";": ("000000", "011000", "011000", "000000", "011000", "001000", "010000", "000000"),
    "!": ("001000", "001000", "001000", "001000", "001000", "000000", "001000", "000000"),
    "?": ("011100", "100010", "000010", "001100", "001000", "000000", "001000", "000000"),
    "'": ("001000", "001000", "010000", "000000", "000000", "000000", "000000", "000000"),
    "-": ("000000", "000000", "000000", "011100", "000000", "000000", "000000", "000000"),
    "(": ("000100", "001000", "010000", "010000", "010000", "001000", "000100", "000000"),
    ")": ("010000", "001000", "000100", "000100", "000100", "001000", "010000", "000000"),
    "%": ("110010", "110100", "000100", "001000", "010000", "010110", "100110", "000000"),
    "$": ("001000", "011110", "101000", "011100", "001010", "111100", "001000", "000000"),
    "&": ("011000", "100100", "101000", "010000", "101010", "100100", "011010", "000000"),
    "/": ("000010", "000100", "000100", "001000", "010000", "010000", "100000", "000000"),
    "+": ("000000", "001000", "001000", "011100", "001000", "001000", "000000", "000000"),
    "=": ("000000", "000000", "111110", "000000", "111110", "000000", "000000", "000000"),
    "#": ("010100", "010100", "111110", "010100", "111110", "010100", "010100", "000000"),
    "@": ("011100", "100010", "101110", "101010", "101100", "100000", "011100", "000000"),
    "*": ("000000", "101010", "011100", "111110", "011100", "101010", "000000", "000000"),
    "_": ("000000", "000000", "000000", "000000", "000000", "000000", "111110", "000000"),
    '"': ("010100", "010100", "000000", "000000", "000000", "000000", "000000", "000000"),
    "<": ("000100", "001000", "010000", "100000", "010000", "001000", "000100", "000000"),
    ">": ("010000", "001000", "000100", "000010", "000100", "001000", "010000", "000000"),
}


def text_width(scale, s):
    """Pixel width of s rendered at scale (7 units per char, minus trailing gap)."""
    if not s:
        return 0
    return len(s) * 7 * scale - scale


def wrap(text, max_width, scale):
    """Greedy word wrap. Returns a list of lines that fit max_width pixels."""
    words = text.split(" ")
    lines = []
    cur = ""
    for word in words:
        trial = word if not cur else cur + " " + word
        if text_width(scale, trial) <= max_width:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


class Canvas:
    def __init__(self, w, h, bg):
        self.w, self.h = w, h
        self.px = bytearray(bytes(bg) * (w * h))

    def set_pixel(self, x, y, color):
        if 0 <= x < self.w and 0 <= y < self.h:
            i = (y * self.w + x) * 3
            self.px[i], self.px[i + 1], self.px[i + 2] = color

    def fill_rect(self, x, y, w, h, color):
        x0, y0 = max(0, x), max(0, y)
        x1, y1 = min(self.w, x + w), min(self.h, y + h)
        if x1 <= x0 or y1 <= y0:
            return
        row = bytes(color) * (x1 - x0)
        for yy in range(y0, y1):
            i = (yy * self.w + x0) * 3
            self.px[i:i + len(row)] = row

    def rect(self, x, y, w, h, color, thick=1):
        self.fill_rect(x, y, w, thick, color)
        self.fill_rect(x, y + h - thick, w, thick, color)
        self.fill_rect(x, y, thick, h, color)
        self.fill_rect(x + w - thick, y, thick, h, color)

    def line(self, x0, y0, x1, y1, color, thick=1):
        dx, dy = abs(x1 - x0), abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx - dy
        half = thick // 2
        while True:
            self.fill_rect(x0 - half, y0 - half, thick, thick, color)
            if x0 == x1 and y0 == y1:
                break
            e2 = 2 * err
            if e2 > -dy:
                err -= dy
                x0 += sx
            if e2 < dx:
                err += dx
                y0 += sy

    def filled_circle(self, cx, cy, r, color):
        for dy in range(-r, r + 1):
            dx = int(math.sqrt(max(0, r * r - dy * dy)))
            self.fill_rect(cx - dx, cy + dy, 2 * dx + 1, 1, color)

    def circle(self, cx, cy, r, color, thick=1):
        x, y, d = r, 0, 1 - r
        while x >= y:
            for px, py in ((cx + x, cy + y), (cx + y, cy + x), (cx - y, cy + x),
                           (cx - x, cy + y), (cx - x, cy - y), (cx - y, cy - x),
                           (cx + y, cy - x), (cx + x, cy - y)):
                self.fill_rect(px - thick // 2, py - thick // 2, thick, thick, color)
            y += 1
            if d <= 0:
                d += 2 * y + 1
            else:
                x -= 1
                d += 2 * (y - x) + 1

    def arc(self, cx, cy, rx, ry, a0, a1, color, thick=1):
        steps = max(8, int(abs(a1 - a0) / 3))
        prev = None
        for i in range(steps + 1):
            a = math.radians(a0 + (a1 - a0) * i / steps)
            x = int(round(cx + rx * math.cos(a)))
            y = int(round(cy + ry * math.sin(a)))
            if prev is not None:
                self.line(prev[0], prev[1], x, y, color, thick)
            prev = (x, y)

    def fill_polygon(self, pts, color):
        ys = [p[1] for p in pts]
        for y in range(min(ys), max(ys) + 1):
            xs = []
            n = len(pts)
            for i in range(n):
                x1, y1 = pts[i]
                x2, y2 = pts[(i + 1) % n]
                if (y1 <= y < y2) or (y2 <= y < y1):
                    xs.append(x1 + (y - y1) * (x2 - x1) / (y2 - y1))
            xs.sort()
            for i in range(0, len(xs) - 1, 2):
                xa, xb = int(math.ceil(xs[i])), int(xs[i + 1])
                if xb >= xa:
                    self.fill_rect(xa, y, xb - xa + 1, 1, color)

    def draw_text(self, x, y, scale, s, color, bold=False):
        """Draw text at top-left (x, y). Bold re-draws offset by 1 px."""
        for ox in ((0, 1) if bold else (0,)):
            cx = x + ox
            for ch in s:
                rows = FONT.get(ch, FONT[" "])
                for r, bits in enumerate(rows):
                    for c, bit in enumerate(bits):
                        if bit == "1":
                            self.fill_rect(cx + c * scale, y + r * scale,
                                           scale, scale, color)
                cx += 7 * scale

    def draw_centered(self, y, scale, s, color, bold=False):
        x = (self.w - text_width(scale, s)) // 2
        self.draw_text(x, y, scale, s, color, bold)

    def draw_right(self, x_right, y, scale, s, color, bold=False):
        x = x_right - text_width(scale, s)
        self.draw_text(x, y, scale, s, color, bold)


# ---- pictogram icons (each draws inside the box x, y, size) ----

def icon_flags(cv, x, y, s, color):
    cols = (RED, BLUE, GOLD)
    for i in range(3):
        px = x + int(s * (0.22 + 0.26 * i))
        cv.line(px, y + int(s * 0.10), px, y + int(s * 0.90), INK,
                max(2, s // 36))
        cv.fill_rect(px, y + int(s * 0.10), int(s * 0.20), int(s * 0.22), cols[i])
    cv.fill_rect(x + int(s * 0.10), y + int(s * 0.90), int(s * 0.80), max(2, s // 36), INK)


def icon_courthouse(cv, x, y, s, color):
    cv.fill_polygon([(x + int(s * 0.08), y + int(s * 0.36)),
                     (x + int(s * 0.50), y + int(s * 0.08)),
                     (x + int(s * 0.92), y + int(s * 0.36))], color)
    cv.fill_rect(x + int(s * 0.06), y + int(s * 0.38), int(s * 0.88), int(s * 0.07), color)
    for f in (0.18, 0.44, 0.70):
        cv.fill_rect(x + int(s * f), y + int(s * 0.48), int(s * 0.10), int(s * 0.32), color)
    cv.fill_rect(x + int(s * 0.06), y + int(s * 0.82), int(s * 0.88), int(s * 0.07), color)
    cv.fill_rect(x + int(s * 0.02), y + int(s * 0.90), int(s * 0.96), int(s * 0.05), color)


def icon_bridge(cv, x, y, s, color):
    deck = y + int(s * 0.62)
    cv.fill_rect(x + int(s * 0.04), deck, int(s * 0.92), max(3, s // 28), color)
    for f in (0.22, 0.72):
        cv.fill_rect(x + int(s * f), y + int(s * 0.18), int(s * 0.07),
                     int(s * 0.44), color)
    cv.arc(x + int(s * 0.50), deck, int(s * 0.25), int(s * 0.34), 180, 360,
           color, max(2, s // 30))
    for f in (0.30, 0.42, 0.58, 0.70):
        cv.line(x + int(s * 0.25), y + int(s * 0.18), x + int(s * f), deck,
                color, max(1, s // 48))
        cv.line(x + int(s * 0.75), y + int(s * 0.18), x + int(s * f), deck,
                color, max(1, s // 48))
    for i, f in enumerate((0.72, 0.82)):
        cv.line(x + int(s * (0.14 + 0.10 * i)), y + int(s * f),
                x + int(s * (0.86 - 0.10 * i)), y + int(s * f), BLUE, max(2, s // 36))


def icon_chart(cv, x, y, s, color):
    cv.line(x + int(s * 0.12), y + int(s * 0.12), x + int(s * 0.12),
            y + int(s * 0.88), INK, max(2, s // 36))
    cv.line(x + int(s * 0.12), y + int(s * 0.88), x + int(s * 0.90),
            y + int(s * 0.88), INK, max(2, s // 36))
    pts = [(0.18, 0.28), (0.36, 0.46), (0.50, 0.38), (0.68, 0.62), (0.86, 0.72)]
    px = [(x + int(s * a), y + int(s * b)) for a, b in pts]
    for i in range(len(px) - 1):
        cv.line(px[i][0], px[i][1], px[i + 1][0], px[i + 1][1], color,
                max(3, s // 24))
    ex, ey = px[-1]
    cv.fill_polygon([(ex, ey + int(s * 0.10)), (ex - int(s * 0.10), ey - int(s * 0.02)),
                     (ex + int(s * 0.04), ey - int(s * 0.08))], color)


def icon_flame(cv, x, y, s, color):
    outer = [(0.50, 0.04), (0.62, 0.22), (0.80, 0.38), (0.86, 0.60),
             (0.78, 0.82), (0.50, 0.96), (0.22, 0.82), (0.14, 0.58),
             (0.24, 0.36), (0.38, 0.24)]
    cv.fill_polygon([(x + int(s * a), y + int(s * b)) for a, b in outer], ORANGE)
    inner = [(0.50, 0.38), (0.60, 0.52), (0.66, 0.66), (0.60, 0.80),
             (0.50, 0.86), (0.40, 0.80), (0.34, 0.66), (0.40, 0.52)]
    cv.fill_polygon([(x + int(s * a), y + int(s * b)) for a, b in inner], LIGHT_ORANGE)


def icon_leaf(cv, x, y, s, color):
    leaf = [(0.50, 0.04), (0.72, 0.14), (0.88, 0.36), (0.86, 0.62),
            (0.66, 0.84), (0.50, 0.92), (0.34, 0.84), (0.14, 0.62),
            (0.12, 0.36), (0.28, 0.14)]
    cv.fill_polygon([(x + int(s * a), y + int(s * b)) for a, b in leaf], color)
    cv.line(x + int(s * 0.50), y + int(s * 0.10), x + int(s * 0.50),
            y + int(s * 0.88), PAPER, max(2, s // 36))
    cv.line(x + int(s * 0.50), y + int(s * 0.30), x + int(s * 0.72),
            y + int(s * 0.16), PAPER, max(1, s // 48))
    cv.line(x + int(s * 0.50), y + int(s * 0.30), x + int(s * 0.28),
            y + int(s * 0.16), PAPER, max(1, s // 48))
    cv.line(x + int(s * 0.50), y + int(s * 0.55), x + int(s * 0.74),
            y + int(s * 0.42), PAPER, max(1, s // 48))
    cv.line(x + int(s * 0.50), y + int(s * 0.55), x + int(s * 0.26),
            y + int(s * 0.42), PAPER, max(1, s // 48))


ICONS = {
    "flags": icon_flags,
    "courthouse": icon_courthouse,
    "bridge": icon_bridge,
    "chart": icon_chart,
    "flame": icon_flame,
    "leaf": icon_leaf,
}


# ---- layout ----

def draw_card(cv, x, y, w, h, story):
    color = tuple(story["color"])
    cv.fill_rect(x, y, w, h, CARD)
    cv.rect(x, y, w, h, BORDER, 2)
    cv.fill_rect(x, y, w, 6, color)


def draw_lead(cv, x, y, w, h, story):
    color = tuple(story["color"])
    draw_card(cv, x, y, w, h, story)
    ICONS[story["icon"]](cv, x + 20, y + 32, 120, color)
    tx = x + 160
    cv.draw_text(tx, y + 26, 2, story["tag"], color, bold=True)
    cv.draw_right(x + w - 20, y + 26, 2, story["source"], GREY)
    lines = wrap(story["headline"], w - 180, 4)
    ly = y + 52
    for line in lines:
        cv.draw_text(tx, ly, 4, line, INK, bold=True)
        ly += 34
    body = wrap(story["body"], w - 180, 2)
    ly += 6
    for line in body:
        cv.draw_text(tx, ly, 2, line, INK)
        ly += 17


def draw_grid_card(cv, x, y, w, h, story):
    color = tuple(story["color"])
    draw_card(cv, x, y, w, h, story)
    ICONS[story["icon"]](cv, x + 16, y + 16, 48, color)
    cv.draw_text(x + 76, y + 26, 2, story["tag"], color, bold=True)
    cv.draw_right(x + w - 16, y + 26, 2, story["source"], GREY)
    lines = wrap(story["headline"], w - 32, 3)
    ly = y + 74
    for line in lines:
        cv.draw_text(x + 16, ly, 3, line, INK, bold=True)
        ly += 26
    body = wrap(story["body"], w - 32, 2)
    ly += 6
    for line in body:
        cv.draw_text(x + 16, ly, 2, line, INK)
        ly += 17


def draw_wide(cv, x, y, w, h, story):
    color = tuple(story["color"])
    draw_card(cv, x, y, w, h, story)
    ICONS[story["icon"]](cv, x + 20, y + 20, 88, color)
    tx = x + 128
    cv.draw_text(tx, y + 18, 2, story["tag"], color, bold=True)
    cv.draw_right(x + w - 20, y + 18, 2, story["source"], GREY)
    lines = wrap(story["headline"], w - 148, 3)
    ly = y + 42
    for line in lines:
        cv.draw_text(tx, ly, 3, line, INK, bold=True)
        ly += 26
    body = wrap(story["body"], w - 148, 2)
    ly += 4
    for line in body:
        cv.draw_text(tx, ly, 2, line, INK)
        ly += 17


def render(news):
    cv = Canvas(W, H, PAPER)
    # Masthead
    cv.fill_rect(0, 0, W, 150, NAVY)
    cv.draw_centered(28, 8, news["title"], WHITE, bold=True)
    date = news["date_line"]
    cv.draw_centered(104, 3, date, GOLD, bold=True)
    dw = text_width(3, date)
    rule_y = 116
    cv.fill_rect(120, rule_y, (W - dw) // 2 - 160, 3, GOLD)
    cv.fill_rect(W - 120 - ((W - dw) // 2 - 160), rule_y, (W - dw) // 2 - 160, 3, GOLD)
    cv.fill_rect(0, 150, W, 4, GOLD)
    # Subline
    ly = 168
    for line in news["sublines"]:
        cv.draw_centered(ly, 2, line, INK)
        ly += 22
    # Lead story
    draw_lead(cv, 24, 216, 976, 184, news["lead"])
    # 2x2 grid
    gx = (24, 524)
    gy = (412, 628)
    for i, story in enumerate(news["stories"]):
        draw_grid_card(cv, gx[i % 2], gy[i // 2], 476, 204, story)
    # Wide climate story
    draw_wide(cv, 24, 844, 976, 128, news["wide"])
    # Sources band
    cv.fill_rect(0, 980, W, 44, NAVY)
    cv.draw_centered(994, 2, news["footer"], WHITE)
    return cv


# ---- deterministic PNG encoder ----

def _chunk(typ, data):
    return (struct.pack(">I", len(data)) + typ + data +
            struct.pack(">I", zlib.crc32(typ + data) & 0xFFFFFFFF))


def encode_png(w, h, px):
    raw = bytearray()
    row = w * 3
    for yy in range(h):
        raw.append(0)  # filter 0 on every row
        raw += px[yy * row:(yy + 1) * row]
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", ihdr) +
            _chunk(b"IDAT", zlib.compress(bytes(raw), 9)) + _chunk(b"IEND", b""))


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, "news.json"), encoding="utf-8") as f:
        news = json.load(f)
    cv = render(news)
    out_dir = os.environ.get("MAKEFUN_OUTPUT_DIR", "/output")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "entry.png")
    with open(path, "wb") as f:
        f.write(encode_png(W, H, cv.px))
    print("wrote", path)


if __name__ == "__main__":
    main()
