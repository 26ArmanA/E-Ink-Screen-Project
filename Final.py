#much credit the Claude AI for code

import RPi.GPIO as GPIO
import time
import sys
import os
import re
import math
import random
import signal
import requests
import pygame
from groq import Groq
from datetime import datetime
from collections import defaultdict
from PIL import Image, ImageDraw, ImageFont
from inky.auto import auto

# ─── Shared Display Setup ────────────────────────────────────────────────────────

display = auto()
W, H = display.width, display.height
INKY_AVAILABLE = True
print(f"Inky detected: {W}x{H}")

def push_to_inky(img):
    """Send a PIL image to the physical Inky display."""
    display.set_image(img)
    display.show()

def clear_display():
    """Fills the Inky Impression 7.3" screen with white (off)."""
    blank = Image.new("RGB", (W, H), (255, 255, 255))
    push_to_inky(blank)


# ─── Pin Configuration ───────────────────────────────────────────────────────────
# COM pin → GND (Pin 6)
PIN_MODE_1 = 27  # Position 1 → GPIO27 (Pin 13)
PIN_MODE_2 = 22  # Position 2 → GPIO22 (Pin 15)
PIN_MODE_3 = 23  # Position 3 → GPIO23 (Pin 16)

PIN_MAP = {PIN_MODE_1: 1, PIN_MODE_2: 2, PIN_MODE_3: 3}

GPIO.setmode(GPIO.BCM)
for pin in PIN_MAP:
    GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  MODE 1 — Movie Quotes                                                      ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

DISPLAY_WIDTH  = W
DISPLAY_HEIGHT = H

INKY_BLACK  = (  0,   0,   0)
INKY_WHITE  = (255, 255, 255)
INKY_RED    = (200,   0,   0)
INKY_YELLOW = (220, 180,   0)
INKY_GREY   = (160, 160, 160)

BG_COLOUR     = INKY_WHITE
QUOTE_COLOUR  = INKY_BLACK
MOVIE_COLOUR  = (160,   0,   0)
ACCENT_COLOUR = INKY_RED
FOOTER_COLOUR = (100, 100, 100)

MARGIN          = 50
QUOTE_TOP       = 90
MAX_QUOTE_W     = DISPLAY_WIDTH - MARGIN * 2
REFRESH_SECONDS = 120
REQUEST_TIMEOUT = 8

BUILTIN_QUOTES = [
    ("Here's looking at you, kid.", "Casablanca (1942)"),
    ("May the Force be with you.", "Star Wars (1977)"),
    ("You can't handle the truth!", "A Few Good Men (1992)"),
    ("I'll be back.", "The Terminator (1984)"),
    ("There's no place like home.", "The Wizard of Oz (1939)"),
    ("To infinity and beyond!", "Toy Story (1995)"),
    ("Why so serious?", "The Dark Knight (2008)"),
    ("Just keep swimming.", "Finding Nemo (2003)"),
    ("You had me at hello.", "Jerry Maguire (1996)"),
    ("Life is like a box of chocolates.", "Forrest Gump (1994)"),
    ("I see dead people.", "The Sixth Sense (1999)"),
    ("Go ahead, make my day.", "Sudden Impact (1983)"),
    ("You talking to me?", "Taxi Driver (1976)"),
    ("I'm the king of the world!", "Titanic (1997)"),
    ("Keep your friends close, but your enemies closer.", "The Godfather Part II (1974)"),
    ("With great power comes great responsibility.", "Spider-Man (2002)"),
    ("There is no spoon.", "The Matrix (1999)"),
    ("Houston, we have a problem.", "Apollo 13 (1995)"),
    ("My precious.", "The Lord of the Rings (2002)"),
    ("Hasta la vista, baby.", "Terminator 2: Judgment Day (1991)"),
    ("Do. Or do not. There is no try.", "The Empire Strikes Back (1980)"),
    ("Carpe diem. Seize the day, boys.", "Dead Poets Society (1989)"),
    ("Bond. James Bond.", "Dr. No (1962)"),
    ("I am Groot.", "Guardians of the Galaxy (2014)"),
]

random.shuffle(BUILTIN_QUOTES)
_builtin_index = 0

def _next_builtin_quote():
    global _builtin_index
    q, m = BUILTIN_QUOTES[_builtin_index % len(BUILTIN_QUOTES)]
    _builtin_index += 1
    return (f'"{q}"', m)

def _fetch_online_quote():
    try:
        r = requests.get("https://api.quotable.io/random", timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        data   = r.json()
        quote  = data.get("content", "").strip()
        author = data.get("author", "").strip()
        if quote and author:
            return (f'"{quote}"', author)
    except Exception:
        pass
    return None

def _get_quote():
    online = _fetch_online_quote()
    return online if online else _next_builtin_quote()

def _wrap_text_pygame(text, font, max_width):
    words, lines, current = text.split(), [], ""
    for word in words:
        test = f"{current} {word}".strip()
        if font.size(test)[0] <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines

def _best_fit_font(text, max_width, max_height, size_max=40, size_min=18):
    for size in range(size_max, size_min - 1, -2):
        font  = pygame.font.SysFont("dejavuserif", size, italic=True) or pygame.font.Font(None, size)
        lines = _wrap_text_pygame(text, font, max_width)
        if len(lines) * font.get_linesize() <= max_height:
            return font, lines
    font = pygame.font.Font(None, size_min)
    return font, _wrap_text_pygame(text, font, max_width)

def _render_quotes(screen, fonts, quote, source, status=""):
    screen.fill(BG_COLOUR)
    w, h = screen.get_size()
    hdr = fonts["title"].render("  Famous Movie Quotes", True, MOVIE_COLOUR)
    screen.blit(hdr, (MARGIN, 18))
    pygame.draw.line(screen, ACCENT_COLOUR, (MARGIN, 58), (w - MARGIN, 58), 2)
    footer_h = 40
    source_h = fonts["movie"].get_linesize() + 16
    avail_h  = h - QUOTE_TOP - source_h - footer_h
    qfont, lines = _best_fit_font(quote, MAX_QUOTE_W, avail_h)
    line_h  = qfont.get_linesize()
    block_h = len(lines) * line_h
    start_y = QUOTE_TOP + max(0, (avail_h - block_h) // 2)
    for i, line in enumerate(lines):
        surf = qfont.render(line, True, QUOTE_COLOUR)
        screen.blit(surf, (MARGIN, start_y + i * line_h))
    src_surf = fonts["movie"].render(f"— {source}", True, MOVIE_COLOUR)
    screen.blit(src_surf, (MARGIN, start_y + block_h + 14))
    footer_y = h - footer_h
    pygame.draw.line(screen, ACCENT_COLOUR, (MARGIN, footer_y - 6), (w - MARGIN, footer_y - 6), 1)
    ts   = time.strftime("%H:%M:%S")
    ftxt = f"Updated {ts}  •  refreshes every {REFRESH_SECONDS}s"
    if status:
        ftxt = f"[{status}]  " + ftxt
    fsuf = fonts["footer"].render(ftxt, True, FOOTER_COLOUR)
    screen.blit(fsuf, (MARGIN, footer_y + 4))

def mode_1():
    """Mode 1 — Movie Quotes on Inky display."""
    print("Mode 1: Movie Quotes")
    pygame.init()
    screen = pygame.display.set_mode((DISPLAY_WIDTH, DISPLAY_HEIGHT))
    pygame.display.set_caption('Movie Quotes')

    def sf(name, size, bold=False, italic=False):
        return pygame.font.SysFont(name, size, bold=bold, italic=italic) or pygame.font.Font(None, size)

    fonts = {
        "title":  sf("dejavusans",     22, bold=True),
        "movie":  sf("dejavusans",     26, bold=True),
        "footer": sf("dejavusansmono", 17),
    }

    last_fetch = -REFRESH_SECONDS
    quote, source = "", ""

    # Run until the switch changes (current_mode will change)
    start_mode = current_mode[0]
    while current_mode[0] == start_mode:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return

        now = time.time()
        if now - last_fetch >= REFRESH_SECONDS:
            print("[Mode 1] Fetching quote...")
            try:
                quote, source = _get_quote()
                status = ""
            except Exception as e:
                quote, source, status = '"Could not load a quote."', "Unknown", str(e)

            last_fetch = now
            _render_quotes(screen, fonts, quote, source, status)
            pygame.display.flip()

            raw     = pygame.image.tostring(screen, "RGB")
            pil_img = Image.frombytes("RGB", (DISPLAY_WIDTH, DISPLAY_HEIGHT), raw)
            pil_img = pil_img.resize(display.resolution)
            push_to_inky(pil_img)

        time.sleep(0.1)

    pygame.quit()


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  MODE 2 — News Headlines                                                    ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

NEWS_API_KEY = os.environ.get("NEWS_API_KEY", "*******")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "*****")
NUM_TOPICS   = 5
FETCH_SIZE   = 50

_NEWS_BLACK  = (  0,   0,   0)
_NEWS_WHITE  = (255, 255, 255)
_NEWS_GREEN  = (  0, 170,  60)
_NEWS_BLUE   = ( 30,  80, 200)
_NEWS_RED    = (200,  30,  30)
_NEWS_YELLOW = (220, 200,   0)
BADGE_COLORS = [_NEWS_RED, _NEWS_BLUE, _NEWS_GREEN, _NEWS_YELLOW, (120, 60, 180)]
BADGE_TEXT   = [_NEWS_WHITE, _NEWS_WHITE, _NEWS_BLACK, _NEWS_BLACK, _NEWS_WHITE]

STOP_WORDS = {
    "the","a","an","and","or","but","in","on","at","to","for","of","with",
    "by","from","is","are","was","were","be","been","has","have","had",
    "it","its","this","that","these","those","he","she","they","we","i",
    "his","her","their","our","as","up","out","about","than","into","through",
    "after","over","new","says","say","said","will","can","not","no","more",
    "also","what","how","who","when","where","why","us","s","report","reports",
    "just","could","would","should","one","two","three","first","last","year",
    "years","day","days","week","may","might","now","still","back","get","gets",
    "make","makes","take",
}

def _load_font(size, bold=False):
    paths = [
        f"/usr/share/fonts/truetype/dejavu/DejaVuSans{'-Bold' if bold else ''}.ttf",
        f"/usr/share/fonts/truetype/liberation/LiberationSans-{'Bold' if bold else 'Regular'}.ttf",
        f"/usr/share/fonts/truetype/noto/NotoSans-{'Bold' if bold else 'Regular'}.ttf",
    ]
    for p in paths:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
    return ImageFont.load_default()

def _tsz(draw, text, font):
    bb = draw.textbbox((0, 0), text, font=font)
    return bb[2] - bb[0], bb[3] - bb[1]

def _wrap_pil(draw, text, font, max_width):
    words, lines, line = text.split(), [], ""
    for word in words:
        test = (line + " " + word).strip()
        if _tsz(draw, test, font)[0] <= max_width:
            line = test
        else:
            if line:
                lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines

def _fetch_headlines():
    r = requests.get(
        "https://newsapi.org/v2/top-headlines",
        params={"country": "us", "pageSize": FETCH_SIZE, "apiKey": NEWS_API_KEY},
        timeout=15,
    )
    r.raise_for_status()
    data = r.json()
    if data.get("status") != "ok":
        raise ValueError(f"NewsAPI error: {data.get('message')}")
    return [a for a in data.get("articles", []) if a.get("title") and a.get("description")]

def _extract_keywords(text, n=8):
    words = re.findall(r"[a-zA-Z]{4,}", text.lower())
    return [w for w in words if w not in STOP_WORDS][:n]

def _cluster_articles(articles, num_topics=5):
    keyed = []
    for a in articles:
        text = (a.get("title", "") + " " + a.get("description", "")).lower()
        keyed.append((set(_extract_keywords(text, n=10)), a))
    clusters = []
    for kws, article in keyed:
        best_idx, best_score = -1, 1
        for i, (ckws, _) in enumerate(clusters):
            score = len(kws & ckws)
            if score > best_score:
                best_score, best_idx = score, i
        if best_idx >= 0:
            ckws, cart = clusters[best_idx]
            clusters[best_idx] = (ckws | kws, cart + [article])
        else:
            clusters.append((kws, [article]))
    clusters.sort(key=lambda x: len(x[1]), reverse=True)
    return clusters[:num_topics]

def _summarise_topic(client, articles):
    headlines = "\n".join(f"  - {a['title']}" for a in articles[:6])
    prompt = (
        "You are a news editor writing for an e-ink display.\n"
        "Below are headlines about ONE news topic.\n"
        "Respond with exactly two lines and nothing else:\n"
        "LABEL: <3-5 word title case label, no punctuation>\n"
        "SUMMARY: <one full sentence with details, between 15-25 words>\n\n"
        f"Headlines:\n{headlines}"
    )
    resp = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        max_tokens=80,
        messages=[{"role": "user", "content": prompt}],
    )
    raw   = resp.choices[0].message.content.strip()
    lines = [l.strip() for l in raw.splitlines() if l.strip()]
    label, summary = "News", ""
    for line in lines:
        if line.startswith("LABEL:"):
            label = line.replace("LABEL:", "").strip()
        elif line.startswith("SUMMARY:"):
            summary = line.replace("SUMMARY:", "").strip()
    return label, summary

def _render_news(topics, updated_str):
    img  = Image.new("RGB", (W, H), _NEWS_WHITE)
    draw = ImageDraw.Draw(img)
    if not topics:
        draw.text((20, 20), "No topics available.", font=_load_font(32, bold=True), fill=_NEWS_BLACK)
        return img
    PAD    = 16
    f_head    = _load_font(int(H * 0.052), bold=True)
    f_ts      = _load_font(int(H * 0.034))
    f_label   = _load_font(int(H * 0.050), bold=True)
    f_summary = _load_font(int(H * 0.038))
    f_badge   = _load_font(int(H * 0.046), bold=True)
    HEAD_H = int(H * 0.115)
    draw.rectangle([(0, 0), (W, HEAD_H)], fill=_NEWS_BLACK)
    _, hh = _tsz(draw, "X", f_head)
    draw.text((PAD * 2, HEAD_H // 2 - hh // 2), "Top News Today", font=f_head, fill=_NEWS_WHITE)
    tw, th = _tsz(draw, updated_str, f_ts)
    draw.text((W - tw - PAD * 2, HEAD_H // 2 - th // 2), updated_str, font=f_ts, fill=_NEWS_WHITE)
    n, content_h = len(topics), H - HEAD_H
    row_h = content_h // n
    badge_size = max(28, min(int(row_h * 0.52), 56))
    for i, (label, summary) in enumerate(topics):
        ry0    = HEAD_H + i * row_h
        ry1    = ry0 + row_h
        row_cy = (ry0 + ry1) // 2
        if i > 0:
            draw.line([(PAD, ry0), (W - PAD, ry0)], fill=(180, 180, 180), width=1)
        badge_col  = BADGE_COLORS[i % len(BADGE_COLORS)]
        badge_tcol = BADGE_TEXT[i % len(BADGE_TEXT)]
        bx0, by0   = PAD, row_cy - badge_size // 2
        bx1, by1   = bx0 + badge_size, by0 + badge_size
        draw.rounded_rectangle([(bx0, by0), (bx1, by1)], radius=6, fill=badge_col, outline=_NEWS_BLACK, width=2)
        num_str = str(i + 1)
        nw, nh  = _tsz(draw, num_str, f_badge)
        draw.text((bx0 + badge_size // 2 - nw // 2, by0 + badge_size // 2 - nh // 2), num_str, font=f_badge, fill=badge_tcol)
        tx0   = bx1 + PAD
        txt_w = W - tx0 - PAD
        lw, lh = _tsz(draw, label, f_label)
        while lw > txt_w and len(label) > 4:
            label  = label[:-2] + "…"
            lw, lh = _tsz(draw, label, f_label)
        sum_lines        = _wrap_pil(draw, summary, f_summary, txt_w)
        _, slh           = _tsz(draw, "X", f_summary)
        SUM_LINE_SPACING = int(slh * 1.5)
        LABEL_GAP        = int(lh * 0.40)
        num_sum_lines    = min(len(sum_lines), 2)
        total_text_h     = lh + LABEL_GAP + SUM_LINE_SPACING * num_sum_lines
        text_y0          = row_cy - total_text_h // 2
        draw.text((tx0, text_y0), label, font=f_label, fill=_NEWS_BLACK)
        sy = text_y0 + lh + LABEL_GAP
        for line in sum_lines[:2]:
            draw.text((tx0, sy), line, font=f_summary, fill=(60, 60, 60))
            sy += SUM_LINE_SPACING
    return img

def mode_2():
    """Mode 2 — News Headlines."""
    print("Mode 2: News Headlines")
    try:
        articles = _fetch_headlines()
        print(f"  Got {len(articles)} articles")
        clusters = _cluster_articles(articles, num_topics=NUM_TOPICS)
        client   = Groq(api_key=GROQ_API_KEY)
        topics   = []
        for i, (kws, arts) in enumerate(clusters):
            print(f"  Summarising topic {i+1}/{len(clusters)}...")
            topics.append(_summarise_topic(client, arts))
        updated = datetime.now().strftime("%-I:%M %p · %b %-d")
        img     = _render_news(topics, updated)
    except Exception as e:
        print(f"  ERROR: {e}")
        img = Image.new("RGB", (W, H), (255, 255, 255))
        draw = ImageDraw.Draw(img)
        draw.text((20, 20), f"News error: {e}", font=_load_font(28, bold=True), fill=(200, 30, 30))
    push_to_inky(img)


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  MODE 3 — Air Quality Index                                                 ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

AIRNOW_API_KEY = os.environ.get("AIRNOW_API_KEY", "****")
SF_LAT         = 37.7749
SF_LON         = -122.4194
DISTANCE_MILES = 25
SLIDER_MAX     = 300

AQI_BANDS = [
    ( 50, "GOOD",               (  0, 180,  60), (  0,   0,   0), "Air quality is great — enjoy the outdoors."),
    (100, "MODERATE",           (220, 200,   0), (  0,   0,   0), "Acceptable for most — sensitive groups take care."),
    (150, "UNHEALTHY FOR SOME", (230, 120,   0), (  0,   0,   0), "Sensitive groups should limit outdoor activity."),
    (200, "UNHEALTHY",          (200,  30,  30), (255, 255, 255), "Everyone may feel health effects outdoors."),
    (300, "VERY UNHEALTHY",     ( 30,  80, 200), (255, 255, 255), "Health alert — avoid prolonged outdoor exertion."),
    (500, "HAZARDOUS",          (120,  30,  30), (220, 200,   0), "Emergency conditions — stay indoors."),
]

def _aqi_info(aqi):
    for ceiling, label, color, text_color, note in AQI_BANDS:
        if aqi <= ceiling:
            return label, color, text_color, note
    return AQI_BANDS[-1][1], AQI_BANDS[-1][2], AQI_BANDS[-1][3], AQI_BANDS[-1][4]

def _lerp_color(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))

def _gradient_color(frac):
    stops = [
        (0.00, (  0, 180,  60)),
        (0.33, (220, 200,   0)),
        (0.50, (230, 120,   0)),
        (0.67, (200,  30,  30)),
        (1.00, ( 30,  80, 200)),
    ]
    for i in range(len(stops) - 1):
        t0, c0 = stops[i]
        t1, c1 = stops[i + 1]
        if frac <= t1:
            return _lerp_color(c0, c1, (frac - t0) / (t1 - t0))
    return stops[-1][1]

def _draw_centered(draw, text, font, color, cx, cy):
    tw, th = _tsz(draw, text, font)
    draw.text((cx - tw // 2, cy - th // 2), text, font=font, fill=color)

def _fetch_aqi():
    r = requests.get(
        "https://www.airnowapi.org/aq/observation/latLong/current/",
        params={
            "format":    "application/json",
            "latitude":  SF_LAT,
            "longitude": SF_LON,
            "distance":  DISTANCE_MILES,
            "API_KEY":   AIRNOW_API_KEY,
        },
        timeout=15,
    )
    r.raise_for_status()
    data = r.json()
    if not isinstance(data, list) or not data:
        raise ValueError("No observations returned from AirNow.")
    return data

def _render_aqi(observations):
    best  = max(observations, key=lambda x: x.get("AQI", 0))
    aqi   = best.get("AQI", 0)
    label, band_color, band_text_color, note = _aqi_info(aqi)
    updated = datetime.now().strftime("%-I:%M %p · %b %-d")

    img  = Image.new("RGB", (W, H), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    PAD  = 24

    f_head     = _load_font(int(H * 0.052), bold=True)
    f_ts       = _load_font(int(H * 0.034))
    f_label    = _load_font(int(H * 0.072), bold=True)
    f_note     = _load_font(int(H * 0.040))
    f_ball_num = _load_font(int(H * 0.080), bold=True)
    f_bar_lbl  = _load_font(int(H * 0.032), bold=True)

    HEAD_H = int(H * 0.115)
    draw.rectangle([(0, 0), (W, HEAD_H)], fill=(0, 0, 0))
    _, hh = _tsz(draw, "X", f_head)
    draw.text((PAD * 2, HEAD_H // 2 - hh // 2), "San Francisco Air Quality", font=f_head, fill=(255, 255, 255))
    tw, th = _tsz(draw, updated, f_ts)
    draw.text((W - tw - PAD * 2, HEAD_H // 2 - th // 2), updated, font=f_ts, fill=(255, 255, 255))

    label_y = HEAD_H + int(H * 0.075)
    _draw_centered(draw, label, f_label, (0, 0, 0), W // 2, label_y)

    note_y = label_y + int(H * 0.078)
    _draw_centered(draw, note, f_note, (80, 80, 80), W // 2, note_y)

    bar_h  = int(H * 0.100)
    bar_x0 = PAD * 3
    bar_x1 = W - PAD * 3
    bar_w  = bar_x1 - bar_x0
    radius = bar_h // 2

    nw, nh = _tsz(draw, str(aqi), f_ball_num)
    ball_r = max(int(bar_h * 0.90), nw // 2 + 14, nh // 2 + 14)

    _, lblh      = _tsz(draw, "X", f_bar_lbl)
    below_bar_h  = 7 + 5 + int(H * 0.036) + 5 + lblh * 2 + 6
    stem_h       = int(bar_h * 0.28)
    block_h      = ball_r * 2 + stem_h + bar_h + below_bar_h
    remaining_top = note_y + int(H * 0.055)
    remaining_h   = H - remaining_top - PAD
    block_y0      = remaining_top + (remaining_h - block_h) // 2

    ball_cy  = block_y0 + ball_r
    bar_y0   = ball_cy + ball_r + stem_h
    bar_y1   = bar_y0 + bar_h

    pin_frac = min(1.0, max(0.0, aqi / SLIDER_MAX))
    pin_x    = bar_x0 + int(pin_frac * bar_w)

    col_w     = max(2, bar_w // 150)
    pill_img  = Image.new("RGB", (bar_w, bar_h), (255, 255, 255))
    pill_draw = ImageDraw.Draw(pill_img)
    for col in range(0, bar_w, col_w):
        pill_draw.rectangle([(col, 0), (min(col + col_w, bar_w), bar_h)], fill=_gradient_color(col / bar_w))
    mask_img  = Image.new("L", (bar_w, bar_h), 0)
    mask_draw = ImageDraw.Draw(mask_img)
    mask_draw.rounded_rectangle([(0, 0), (bar_w - 1, bar_h - 1)], radius=radius, fill=255)
    img.paste(pill_img, (bar_x0, bar_y0), mask=mask_img)
    draw.rounded_rectangle([(bar_x0, bar_y0), (bar_x1, bar_y1)], radius=radius, fill=None, outline=(0,0,0), width=3)

    f_range_num = _load_font(int(H * 0.036), bold=True)
    _, name_h   = _tsz(draw, "X", f_bar_lbl)
    _, num_h    = _tsz(draw, "X", f_range_num)
    TICK_H, NUM_GAP, NAME_GAP = 7, 5, 5
    num_y  = bar_y1 + TICK_H + NUM_GAP + num_h // 2
    name_y = num_y  + num_h  // 2 + NAME_GAP + name_h // 2

    for val in [0, 50, 100, 150, 200, 300]:
        tx = bar_x0 + int(min(1.0, val / SLIDER_MAX) * bar_w)
        draw.line([(tx, bar_y1), (tx, bar_y1 + TICK_H)], fill=(120, 120, 120), width=2)
        num_str = str(val)
        nw2, _ = _tsz(draw, num_str, f_range_num)
        cx_c   = max(bar_x0 + nw2 // 2, min(bar_x1 - nw2 // 2, tx))
        _draw_centered(draw, num_str, f_range_num, (80, 80, 80), cx_c, num_y)

    for start, end, name in [(0,50,"GOOD"),(51,100,"MODERATE"),(101,150,"UNHEALTHY\nFOR SOME"),(151,200,"UNHEALTHY"),(201,300,"VERY BAD")]:
        cx = bar_x0 + int(min(1.0, ((start + end) / 2) / SLIDER_MAX) * bar_w)
        for li, lt in enumerate(name.split("\n")):
            lw, _ = _tsz(draw, lt, f_bar_lbl)
            _draw_centered(draw, lt, f_bar_lbl, (110, 110, 110),
                           max(bar_x0 + lw // 2, min(bar_x1 - lw // 2, cx)),
                           name_y + li * (name_h + 2))

    stem_width = max(4, ball_r // 5)
    draw.polygon([
        (pin_x - stem_width//2 - 1, ball_cy + ball_r + 2),
        (pin_x + stem_width//2 + 1, ball_cy + ball_r + 2),
        (pin_x + stem_width//2 + 1, bar_y0),
        (pin_x - stem_width//2 - 1, bar_y0),
    ], fill=(180, 180, 180))
    draw.rectangle([(pin_x - stem_width//2, ball_cy + ball_r), (pin_x + stem_width//2, bar_y0)], fill=(80, 80, 80))

    shadow_off = max(3, ball_r // 10)
    draw.ellipse([(pin_x - ball_r + shadow_off, ball_cy - ball_r + shadow_off),
                  (pin_x + ball_r + shadow_off, ball_cy + ball_r + shadow_off)], fill=(180, 180, 180))
    draw.ellipse([(pin_x - ball_r, ball_cy - ball_r), (pin_x + ball_r, ball_cy + ball_r)],
                 fill=band_color, outline=(0,0,0), width=3)
    hi_r = max(3, ball_r // 6)
    draw.ellipse([(pin_x - ball_r + 6, ball_cy - ball_r + 6),
                  (pin_x - ball_r + 6 + hi_r*2, ball_cy - ball_r + 6 + hi_r*2)], fill=(255,255,255))
    _draw_centered(draw, str(aqi), f_ball_num, band_text_color, pin_x, ball_cy)
    return img

def mode_3():
    """Mode 3 — Air Quality Index."""
    print("Mode 3: Air Quality Index")
    try:
        observations = _fetch_aqi()
        best = max(observations, key=lambda x: x.get("AQI", 0))
        print(f"  AQI {best.get('AQI')} ({best.get('ParameterName')})")
        img = _render_aqi(observations)
    except Exception as e:
        print(f"  ERROR: {e}")
        img = Image.new("RGB", (W, H), (255, 255, 255))
        draw = ImageDraw.Draw(img)
        draw.text((20, 20), f"AQI error: {e}", font=_load_font(28, bold=True), fill=(200, 30, 30))
    push_to_inky(img)


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  Switch Logic                                                               ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

current_mode = [None]

def run_mode(mode):
    if mode == 0:
        mode_off()
    elif mode == 1:
        mode_1()
    elif mode == 2:
        mode_2()
    elif mode == 3:
        mode_3()

def mode_off():
    """All pins HIGH — switch is in the off/zero position."""
    print("Off")
    clear_display()

def read_mode():
    for pin, mode in PIN_MAP.items():
        if GPIO.input(pin) == GPIO.LOW:
            return mode
    return 0

def switch_changed(triggered_pin):
    time.sleep(0.02)
    new_mode = read_mode()
    if new_mode != current_mode[0]:
        current_mode[0] = new_mode
        print(f"\n--- {'Off' if new_mode == 0 else f'Switched to Mode {new_mode}'} ---")
        run_mode(new_mode)

def main():
    print("Rotary switch controller running. Press Ctrl+C to exit.")

    for pin in PIN_MAP:
        GPIO.add_event_detect(pin, GPIO.BOTH, callback=switch_changed, bouncetime=200)

    startup_mode = read_mode()
    current_mode[0] = startup_mode
    print(f"\n--- {'Off' if startup_mode == 0 else f'Starting in Mode {startup_mode}'} ---")
    run_mode(startup_mode)

    try:
        while True:
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\nExiting...")
    finally:
        GPIO.cleanup()

if __name__ == "__main__":
    main()
