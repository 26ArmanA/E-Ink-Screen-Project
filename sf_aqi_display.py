"""
San Francisco AQI — Pimoroni Inky Impression Spectra 6
=======================================================
Fetches live AQI from the EPA AirNow API and renders a bold,
color-coded display onto the Inky Impression Spectra 6 e-ink screen.

The Spectra 6 palette: BLACK, WHITE, GREEN, BLUE, RED, YELLOW
We map these directly to the EPA AQI color scale:
  Good (0-50)             → GREEN
  Moderate (51-100)       → YELLOW
  Unhealthy/Some (101-150)→ YELLOW + border accents
  Unhealthy (151-200)     → RED
  Very Unhealthy (201-300)→ BLUE  (closest available to purple)
  Hazardous (301+)        → RED   (darkest danger)

Install requirements:
  source ~/.virtualenvs/pimoroni/bin/activate
  pip install requests pillow

The inky library is installed by Pimoroni's installer script:
  git clone https://github.com/pimoroni/inky && cd inky && ./install.sh

Set your AirNow API key (free at https://docs.airnowapi.org/account/request/):
  export AIRNOW_API_KEY="your-key-here"
  python sf_aqi_inky.py

Recommended: run every 30 minutes via cron (e-ink is slow to refresh):
  */30 * * * * source ~/.virtualenvs/pimoroni/bin/activate && \
    AIRNOW_API_KEY=your-key /home/pi/.virtualenvs/pimoroni/bin/python \
    /home/pi/sf_aqi_inky.py >> /home/pi/aqi_inky.log 2>&1
"""

import os
import sys
import math
import requests
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont

# ─── Config ─────────────────────────────────────────────────────────────────────

AIRNOW_API_KEY = os.environ.get("AIRNOW_API_KEY", "04E5AF6F-DFFE-4F36-89E2-0FE3F1011F6E")
SF_LAT         = 37.7749
SF_LON         = -122.4194
DISTANCE_MILES = 25

# ─── Inky Setup ──────────────────────────────────────────────────────────────────

try:
    from inky.auto import auto
    inky_display = auto()
    W = inky_display.width
    H = inky_display.height
    INKY_AVAILABLE = True
    print(f"Inky detected: {W}x{H}")
except Exception as e:
    print(f"[WARN] Inky not found ({e}), running in preview mode (800x480 PNG)")
    INKY_AVAILABLE = False
    W, H = 800, 480

# ─── Spectra 6 Palette ───────────────────────────────────────────────────────────
# These are the exact 6 colors the Spectra 6 display can render.
# The inky library dithers PIL images to this palette automatically.

BLACK  = (0,   0,   0)
WHITE  = (255, 255, 255)
GREEN  = (0,   170,  0)   # Spectra 6 green
BLUE   = (30,   80, 200)   # Spectra 6 blue
RED    = (200,  30,  30)   # Spectra 6 red
YELLOW = (220, 200,   0)   # Spectra 6 yellow

# ─── AQI Band → Palette Color Mapping ────────────────────────────────────────────

AQI_BANDS = [
    (50,  "Good",                 GREEN,  BLACK,  "Air quality is great."),
    (100, "Moderate",             YELLOW, BLACK,  "Acceptable air quality."),
    (150, "Unhealthy for Some",   YELLOW, RED,    "Sensitive groups at risk."),
    (200, "Unhealthy",            RED,    WHITE,  "Everyone may feel effects."),
    (300, "Very Unhealthy",       BLUE,   WHITE,  "Health alert for all."),
    (500, "Hazardous",            RED,    YELLOW, "Emergency conditions."),
]

def aqi_info(aqi):
    for ceiling, label, bg, fg, note in AQI_BANDS:
        if aqi <= ceiling:
            return label, bg, fg, note
    return "Hazardous", RED, YELLOW, "Emergency conditions."


# ─── Font Loading ─────────────────────────────────────────────────────────────────

def load_font(size, bold=False):
    """Try system fonts in order; fall back to PIL default."""
    candidates = [
        f"/usr/share/fonts/truetype/dejavu/DejaVuSans{'-Bold' if bold else ''}.ttf",
        f"/usr/share/fonts/truetype/liberation/LiberationSans-{'Bold' if bold else 'Regular'}.ttf",
        f"/usr/share/fonts/truetype/freefont/FreeSans{'Bold' if bold else ''}.ttf",
        f"/usr/share/fonts/truetype/noto/NotoSans-{'Bold' if bold else 'Regular'}.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                pass
    return ImageFont.load_default()


# ─── AirNow API ──────────────────────────────────────────────────────────────────

def fetch_aqi():
    url = "https://www.airnowapi.org/aq/observation/latLong/current/"
    params = {
        "format":    "application/json",
        "latitude":  SF_LAT,
        "longitude": SF_LON,
        "distance":  DISTANCE_MILES,
        "API_KEY":   AIRNOW_API_KEY,
    }
    r = requests.get(url, params=params, timeout=15)
    r.raise_for_status()
    data = r.json()
    if not isinstance(data, list) or len(data) == 0:
        raise ValueError("No observations returned from AirNow.")
    return data


# ─── Drawing Helpers ─────────────────────────────────────────────────────────────

def draw_centered_text(draw, text, font, color, cx, cy):
    bbox = draw.textbbox((0, 0), text, font=font)
    tw   = bbox[2] - bbox[0]
    th   = bbox[3] - bbox[1]
    draw.text((cx - tw // 2, cy - th // 2), text, font=font, fill=color)
    return tw, th


def draw_arc_gauge(img, draw, cx, cy, radius, aqi, max_aqi=300,
                   bg_color=WHITE, accent_color=BLACK):
    """
    Draw a semicircular gauge (flat side down) using line segments.
    E-ink dithers these to the nearest palette color.
    """
    t = min(1.0, aqi / max_aqi)

    # Background arc (unfilled portion) — dim color
    steps = 180
    for i in range(steps):
        angle = math.radians(180 + i)   # left to right, flat bottom
        x1 = int(cx + math.cos(angle) * (radius - 16))
        y1 = int(cy + math.sin(angle) * (radius - 16))
        x2 = int(cx + math.cos(angle) * radius)
        y2 = int(cy + math.sin(angle) * radius)
        # Determine segment color based on position in AQI scale
        frac = i / steps
        if frac < t:
            # Filled portion — use accent color
            seg_col = accent_color
        else:
            # Unfilled — subtle track
            seg_col = tuple(max(0, c - 60) for c in bg_color) if bg_color != BLACK else (80, 80, 80)
        draw.line([(x1, y1), (x2, y2)], fill=seg_col, width=5)

    # Needle
    needle_angle = math.radians(180 + t * 180)
    nx = int(cx + math.cos(needle_angle) * (radius - 22))
    ny = int(cy + math.sin(needle_angle) * (radius - 22))
    draw.line([(cx, cy), (nx, ny)], fill=accent_color, width=4)
    draw.ellipse([(cx - 6, cy - 6), (cx + 6, cy + 6)], fill=accent_color)


def draw_rounded_rect(draw, x0, y0, x1, y1, radius, fill, outline=None, width=2):
    draw.rounded_rectangle([(x0, y0), (x1, y1)], radius=radius, fill=fill, outline=outline, width=width)


def draw_scale_bar(draw, x, y, bar_w, bar_h):
    """
    Horizontal AQI color scale bar with tick marks and labels.
    Shows Good→Moderate→Unhealthy→Hazardous using palette colors.
    """
    segments = [
        (50,  GREEN),
        (100, YELLOW),
        (150, YELLOW),
        (200, RED),
        (300, BLUE),
        (500, RED),
    ]
    max_aqi  = 300
    font_xs  = load_font(11)

    prev_x = x
    for ceiling, color in segments:
        seg_end = min(ceiling, max_aqi)
        seg_w   = int((seg_end / max_aqi) * bar_w)
        end_x   = x + seg_w
        draw.rectangle([(prev_x, y), (end_x, y + bar_h)], fill=color)
        prev_x = end_x

    # Tick marks and labels
    for val, lbl in [(0, "0"), (100, "100"), (200, "200"), (300, "300")]:
        tx = x + int((val / max_aqi) * bar_w)
        draw.line([(tx, y + bar_h), (tx, y + bar_h + 5)], fill=BLACK, width=1)
        bbox = draw.textbbox((0, 0), lbl, font=font_xs)
        lw   = bbox[2] - bbox[0]
        draw.text((tx - lw // 2, y + bar_h + 7), lbl, font=font_xs, fill=BLACK)


# ─── Main Render ─────────────────────────────────────────────────────────────────

def render(observations):
    best     = max(observations, key=lambda x: x.get("AQI", 0))
    aqi      = best.get("AQI", 0)
    label, bg_color, fg_color, note = aqi_info(aqi)
    pollutant = best.get("ParameterName", "AQI")
    updated  = datetime.now().strftime("%b %-d, %I:%M %p")

    img  = Image.new("RGB", (W, H), bg_color)
    draw = ImageDraw.Draw(img)

    # ── Fonts ─────────────────────────────────────────────────────────────────────
    font_aqi     = load_font(160, bold=True)   # Giant AQI number
    font_label   = load_font(28,  bold=True)   # Category label
    font_city    = load_font(22,  bold=True)   # "San Francisco"
    font_note    = load_font(18)               # Advisory text
    font_sub     = load_font(15)               # Pollutant breakdowns
    font_ts      = load_font(13)               # Timestamp

    # ── Layout constants ──────────────────────────────────────────────────────────
    PAD   = 18
    CX    = W // 2
    # Left panel: gauge + number
    # Right panel: breakdowns
    split = int(W * 0.62)

    # ── Background fill (already done via Image.new) ──────────────────────────────
    # Draw a white right panel if bg is colored
    if bg_color != WHITE:
        draw_rounded_rect(draw, split + PAD, PAD, W - PAD, H - PAD,
                          radius=12, fill=WHITE, outline=fg_color, width=2)

    # ── Header bar ────────────────────────────────────────────────────────────────
    header_h = 42
    draw.rectangle([(0, 0), (W, header_h)], fill=BLACK)
    draw.text((PAD, 10), "San Francisco Air Quality", font=font_city, fill=WHITE)
    # Timestamp right-aligned
    bbox = draw.textbbox((0, 0), updated, font=font_ts)
    draw.text((W - bbox[2] - PAD, 14), updated, font=font_ts, fill=WHITE)

    # ── Gauge ─────────────────────────────────────────────────────────────────────
    gauge_cx = split // 2
    gauge_cy = int(H * 0.54)
    gauge_r  = min(split // 2 - PAD, int(H * 0.38))
    draw_arc_gauge(img, draw, gauge_cx, gauge_cy, gauge_r, aqi,
                   bg_color=bg_color, accent_color=fg_color)

    # Scale labels under gauge
    draw_centered_text(draw, "0",   load_font(12), fg_color,
                       gauge_cx - gauge_r + 10, gauge_cy + 14)
    draw_centered_text(draw, "300", load_font(12), fg_color,
                       gauge_cx + gauge_r - 10, gauge_cy + 14)

    # ── Giant AQI number ──────────────────────────────────────────────────────────
    aqi_str = str(aqi)
    draw_centered_text(draw, aqi_str, font_aqi, fg_color,
                       gauge_cx, gauge_cy - gauge_r // 4)

    # "AQI" unit label
    draw_centered_text(draw, "AQI", load_font(20), fg_color,
                       gauge_cx, gauge_cy - gauge_r // 4 + 88)

    # ── Category pill ─────────────────────────────────────────────────────────────
    pill_y  = gauge_cy + gauge_r // 2 + 12
    pill_h  = 34
    # Measure text
    bbox    = draw.textbbox((0, 0), label, font=font_label)
    pill_w  = bbox[2] - bbox[0] + 36
    px0     = gauge_cx - pill_w // 2
    px1     = gauge_cx + pill_w // 2
    draw_rounded_rect(draw, px0, pill_y, px1, pill_y + pill_h,
                      radius=pill_h // 2, fill=fg_color, outline=None)
    # Pill text — invert color
    pill_text_col = bg_color if bg_color != fg_color else BLACK
    draw_centered_text(draw, label, font_label, pill_text_col,
                       gauge_cx, pill_y + pill_h // 2)

    # Advisory note under pill
    draw_centered_text(draw, note, font_note, fg_color,
                       gauge_cx, pill_y + pill_h + 18)

    # ── Scale bar at bottom left ──────────────────────────────────────────────────
    bar_x = PAD
    bar_y = H - 32
    bar_w = split - PAD * 2
    draw_scale_bar(draw, bar_x, bar_y, bar_w, bar_h=10)

    # ── Right panel: pollutant breakdowns ─────────────────────────────────────────
    rx        = split + PAD * 2
    panel_w   = W - split - PAD * 3
    row_y     = header_h + PAD + 8
    row_step  = (H - header_h - PAD * 2 - 10) // max(len(observations), 1)

    for i, obs in enumerate(observations[:6]):
        p_aqi  = obs.get("AQI", 0)
        p_name = obs.get("ParameterName", "")
        p_cat  = obs.get("Category", {}).get("Name", "")
        _, p_bg, p_fg, _ = aqi_info(p_aqi)

        ry = row_y + i * row_step

        # Colored AQI swatch
        swatch_size = 28
        draw_rounded_rect(draw, rx, ry, rx + swatch_size, ry + swatch_size,
                          radius=4, fill=p_bg, outline=BLACK, width=1)
        # Swatch number (small)
        s_num = str(p_aqi)
        bbox  = draw.textbbox((0, 0), s_num, font=load_font(10, bold=True))
        sw    = bbox[2] - bbox[0]
        sh    = bbox[3] - bbox[1]
        draw.text((rx + swatch_size // 2 - sw // 2,
                   ry + swatch_size // 2 - sh // 2),
                  s_num, font=load_font(10, bold=True), fill=p_fg)

        # Pollutant name + value
        tx = rx + swatch_size + 8
        draw.text((tx, ry),
                  p_name, font=load_font(15, bold=True), fill=BLACK)
        draw.text((tx, ry + 17),
                  p_cat,  font=font_sub,                 fill=(80, 80, 80))

        # Separator line
        if i < len(observations) - 1:
            sep_y = ry + row_step - 6
            draw.line([(rx, sep_y), (W - PAD, sep_y)], fill=(200, 200, 200), width=1)

    # ── Divider between panels ────────────────────────────────────────────────────
    draw.line([(split, header_h + 6), (split, H - 6)], fill=BLACK, width=1)

    return img


def render_error(message):
    """Minimal error screen for the e-ink display."""
    img  = Image.new("RGB", (W, H), WHITE)
    draw = ImageDraw.Draw(img)
    draw.rectangle([(0, 0), (W, 44)], fill=RED)
    draw.text((18, 12), "AQI Fetch Error", font=load_font(22, bold=True), fill=WHITE)
    # Word-wrap the message
    font = load_font(16)
    words, line, lines = message.split(), "", []
    for word in words:
        test = (line + " " + word).strip()
        if draw.textbbox((0, 0), test, font=font)[2] > W - 36:
            lines.append(line)
            line = word
        else:
            line = test
    if line:
        lines.append(line)
    for i, ln in enumerate(lines[:8]):
        draw.text((18, 60 + i * 24), ln, font=font, fill=BLACK)
    hint = "Set AIRNOW_API_KEY and retry."
    draw.text((18, H - 30), hint, font=load_font(13), fill=(100, 100, 100))
    return img


# ─── Entry Point ─────────────────────────────────────────────────────────────────

def main():
    if AIRNOW_API_KEY == "YOUR_AIRNOW_API_KEY_HERE":
        print("=" * 60)
        print("  No AirNow API key set!")
        print("  Get a FREE key: https://docs.airnowapi.org/account/request/")
        print("  Then: export AIRNOW_API_KEY=your-key")
        print("=" * 60)

    print(f"[{datetime.now().strftime('%H:%M:%S')}] Fetching AQI for San Francisco…")

    try:
        observations = fetch_aqi()
        best = max(observations, key=lambda x: x.get("AQI", 0))
        print(f"  AQI: {best.get('AQI')} ({best.get('ParameterName')}) — "
              f"{best.get('Category', {}).get('Name', '')}")
        img = render(observations)
    except Exception as e:
        print(f"  ERROR: {e}")
        img = render_error(str(e))

    if INKY_AVAILABLE:
        print("Sending to Inky display (this takes ~12 seconds)…")
        inky_display.set_image(img)
        inky_display.show()
        print("Done.")
    else:
        out = "sf_aqi_preview.png"
        img.save(out)
        print(f"Preview saved → {out}")
        print("(Run on a Pi with Inky attached to push to e-ink.)")


if __name__ == "__main__":
    main()