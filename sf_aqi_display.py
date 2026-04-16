#Heavy claude usage

import os
import math
import requests
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont

# ─── Config ──────────────────────────────────────────────────────────────────────

AIRNOW_API_KEY = os.environ.get("AIRNOW_API_KEY", "***")
SF_LAT         = 37.7749
SF_LON         = -122.4194
DISTANCE_MILES = 25

# ─── Inky setup ──────────────────────────────────────────────────────────────────

try:
    from inky.auto import auto
    inky_display = auto()
    W, H = inky_display.width, inky_display.height
    INKY_AVAILABLE = True
    print(f"Inky detected: {W}x{H}")
except Exception as e:
    print(f"[WARN] Inky not found ({e}) — preview mode, saving PNG")
    INKY_AVAILABLE = False
    W, H = 800, 480

# ─── Palette ─────────────────────────────────────────────────────────────────────

BLACK  = (  0,   0,   0)
WHITE  = (255, 255, 255)
GREEN  = (  0, 170,  60)
BLUE   = ( 30,  80, 200)
RED    = (200,  30,  30)
YELLOW = (220, 200,   0)

# ─── AQI scale ───────────────────────────────────────────────────────────────────

SLIDER_MAX = 300   # right edge of the bar

AQI_BANDS = [
    ( 50, "GOOD",               (  0, 180,  60), BLACK, "Air quality is great — enjoy the outdoors."),
    (100, "MODERATE",           (220, 200,   0), BLACK, "Acceptable for most — sensitive groups take care."),
    (150, "UNHEALTHY FOR SOME", (230, 120,   0), BLACK, "Sensitive groups should limit outdoor activity."),
    (200, "UNHEALTHY",          (200,  30,  30), WHITE, "Everyone may feel health effects outdoors."),
    (300, "VERY UNHEALTHY",     ( 30,  80, 200), WHITE, "Health alert — avoid prolonged outdoor exertion."),
    (500, "HAZARDOUS",          (120,  30,  30), YELLOW,"Emergency conditions — stay indoors."),
]

def aqi_info(aqi):
    for ceiling, label, color, text_color, note in AQI_BANDS:
        if aqi <= ceiling:
            return label, color, text_color, note
    return AQI_BANDS[-1][1], AQI_BANDS[-1][2], AQI_BANDS[-1][3], AQI_BANDS[-1][4]

# ─── Fonts ───────────────────────────────────────────────────────────────────────

def load_font(size, bold=False):
    paths = [
        f"/usr/share/fonts/truetype/dejavu/DejaVuSans{'-Bold' if bold else ''}.ttf",
        f"/usr/share/fonts/truetype/liberation/LiberationSans-{'Bold' if bold else 'Regular'}.ttf",
        f"/usr/share/fonts/truetype/freefont/FreeSans{'Bold' if bold else ''}.ttf",
        f"/usr/share/fonts/truetype/noto/NotoSans-{'Bold' if bold else 'Regular'}.ttf",
    ]
    for p in paths:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
    return ImageFont.load_default()

def tsz(draw, text, font):
    bb = draw.textbbox((0, 0), text, font=font)
    return bb[2] - bb[0], bb[3] - bb[1]

def draw_centered(draw, text, font, color, cx, cy):
    w, h = tsz(draw, text, font)
    draw.text((cx - w // 2, cy - h // 2), text, font=font, fill=color)

# ─── Gradient helpers ─────────────────────────────────────────────────────────────

def lerp_color(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))

def gradient_color(frac):
    """
    0.0 = green (good), 1.0 = deep red (hazardous).
    Stops mirror the AQI band colours.
    """
    stops = [
        (0.00, (  0, 180,  60)),   # green   — Good
        (0.33, (220, 200,   0)),   # yellow  — Moderate
        (0.50, (230, 120,   0)),   # orange  — Unhealthy for Some
        (0.67, (200,  30,  30)),   # red     — Unhealthy
        (1.00, ( 30,  80, 200)),   # blue    — Very Unhealthy / Hazardous
    ]
    for i in range(len(stops) - 1):
        t0, c0 = stops[i]
        t1, c1 = stops[i + 1]
        if frac <= t1:
            local = (frac - t0) / (t1 - t0)
            return lerp_color(c0, c1, local)
    return stops[-1][1]

# ─── AirNow fetch ─────────────────────────────────────────────────────────────────

def fetch_aqi():
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

# ─── Render ──────────────────────────────────────────────────────────────────────

def render(observations):
    best  = max(observations, key=lambda x: x.get("AQI", 0))
    aqi   = best.get("AQI", 0)
    label, band_color, band_text_color, note = aqi_info(aqi)
    updated = datetime.now().strftime("%-I:%M %p · %b %-d")

    img  = Image.new("RGB", (W, H), WHITE)
    draw = ImageDraw.Draw(img)

    PAD = 24

    # ── Fonts ─────────────────────────────────────────────────────────────────────
    f_head     = load_font(int(H * 0.052), bold=True)
    f_ts       = load_font(int(H * 0.034))
    f_label    = load_font(int(H * 0.072), bold=True)   # "UNHEALTHY FOR SOME"
    f_note     = load_font(int(H * 0.040))               # advisory sentence
    f_ball_num = load_font(int(H * 0.080), bold=True)   # AQI number inside ball
    f_bar_lbl  = load_font(int(H * 0.032), bold=True)   # labels below bar

    # ── Header ────────────────────────────────────────────────────────────────────
    HEAD_H = int(H * 0.115)
    draw.rectangle([(0, 0), (W, HEAD_H)], fill=BLACK)
    _, hh = tsz(draw, "X", f_head)
    draw.text((PAD * 2, HEAD_H // 2 - hh // 2),
              "San Francisco Air Quality", font=f_head, fill=WHITE)
    tw, th = tsz(draw, updated, f_ts)
    draw.text((W - tw - PAD * 2, HEAD_H // 2 - th // 2),
              updated, font=f_ts, fill=WHITE)

    # ── Category label ────────────────────────────────────────────────────────────
    label_y = HEAD_H + int(H * 0.075)
    draw_centered(draw, label, f_label, BLACK, W // 2, label_y)

    # ── Advisory note ─────────────────────────────────────────────────────────────
    note_y = label_y + int(H * 0.078)
    draw_centered(draw, note, f_note, (80, 80, 80), W // 2, note_y)

    # ── Slider geometry ───────────────────────────────────────────────────────────
    bar_h   = int(H * 0.100)
    bar_x0  = PAD * 3
    bar_x1  = W - PAD * 3
    bar_w   = bar_x1 - bar_x0
    radius  = bar_h // 2

    # Pin ball radius — large enough to hold the 3-digit number comfortably
    nw, nh  = tsz(draw, str(aqi), f_ball_num)
    ball_r  = max(int(bar_h * 0.90), nw // 2 + 14, nh // 2 + 14)

    # Below-bar area: tick(7) + band name (up to 2 lines) + number row
    _, lblh     = tsz(draw, "X", f_bar_lbl)
    below_bar_h = 7 + 5 + int(H * 0.036) + 5 + lblh * 2 + 6  # tick+num_gap+num+name_gap+2*name+pad

    # Total block height: ball_diameter + stem + bar + labels
    stem_h  = int(bar_h * 0.28)
    block_h = ball_r * 2 + stem_h + bar_h + below_bar_h

    # Vertically centre the entire slider block in remaining space
    remaining_top = note_y + int(H * 0.055)
    remaining_h   = H - remaining_top - PAD
    block_y0      = remaining_top + (remaining_h - block_h) // 2

    ball_cy  = block_y0 + ball_r
    bar_y0   = ball_cy + ball_r + stem_h
    bar_y1   = bar_y0 + bar_h

    # Pin x position
    pin_frac = min(1.0, max(0.0, aqi / SLIDER_MAX))
    pin_x    = bar_x0 + int(pin_frac * bar_w)

    # ── Draw gradient bar via pill-masked layer ───────────────────────────────────
    col_w    = max(2, bar_w // 150)
    pill_img  = Image.new("RGB", (bar_w, bar_h), WHITE)
    pill_draw = ImageDraw.Draw(pill_img)
    for col in range(0, bar_w, col_w):
        frac  = col / bar_w
        color = gradient_color(frac)
        pill_draw.rectangle([(col, 0), (min(col + col_w, bar_w), bar_h)], fill=color)

    mask_img  = Image.new("L", (bar_w, bar_h), 0)
    mask_draw = ImageDraw.Draw(mask_img)
    mask_draw.rounded_rectangle([(0, 0), (bar_w - 1, bar_h - 1)],
                                 radius=radius, fill=255)
    img.paste(pill_img, (bar_x0, bar_y0), mask=mask_img)

    # Bar outline
    draw.rounded_rectangle([(bar_x0, bar_y0), (bar_x1, bar_y1)],
                            radius=radius, fill=None, outline=BLACK, width=3)

    # ── Labels + range numbers below bar ─────────────────────────────────────────
    #
    # Each band: name centred in its region, boundary numbers at each tick mark.
    #
    band_ranges = [
        (  0,  50, "GOOD"),
        ( 51, 100, "MODERATE"),
        (101, 150, "UNHEALTHY\nFOR SOME"),
        (151, 200, "UNHEALTHY"),
        (201, 300, "VERY BAD"),
    ]
    boundaries = [0, 50, 100, 150, 200, 300]

    f_range_num = load_font(int(H * 0.036), bold=True)   # slightly bigger & bold
    _, name_h   = tsz(draw, "X", f_bar_lbl)
    _, num_h    = tsz(draw, "X", f_range_num)

    TICK_H   = 7
    NUM_GAP  = 5    # gap: tick bottom → number row
    NAME_GAP = 5    # gap: number row bottom → name row

    # Row centres
    num_y  = bar_y1 + TICK_H + NUM_GAP + num_h // 2
    name_y = num_y  + num_h  // 2 + NAME_GAP + name_h // 2

    # Tick marks at each boundary
    for val in boundaries:
        frac = min(1.0, val / SLIDER_MAX)
        tx   = bar_x0 + int(frac * bar_w)
        draw.line([(tx, bar_y1), (tx, bar_y1 + TICK_H)], fill=(120, 120, 120), width=2)

    # Boundary numbers — top row, directly under each tick
    for val in boundaries:
        frac    = min(1.0, val / SLIDER_MAX)
        tx      = bar_x0 + int(frac * bar_w)
        num_str = str(val)
        nw, _   = tsz(draw, num_str, f_range_num)
        cx_c    = max(bar_x0 + nw // 2, min(bar_x1 - nw // 2, tx))
        draw_centered(draw, num_str, f_range_num, (80, 80, 80), cx_c, num_y)

    # Band names — bottom row, centred within each band's region
    for start, end, name in band_ranges:
        mid_frac = min(1.0, ((start + end) / 2) / SLIDER_MAX)
        cx       = bar_x0 + int(mid_frac * bar_w)
        for line_i, line_txt in enumerate(name.split("\n")):
            lw, _ = tsz(draw, line_txt, f_bar_lbl)
            cx_c  = max(bar_x0 + lw // 2, min(bar_x1 - lw // 2, cx))
            draw_centered(draw, line_txt, f_bar_lbl, (110, 110, 110),
                          cx_c, name_y + line_i * (name_h + 2))

    # ── Needle stem from ball bottom to bar top ───────────────────────────────────
    stem_top    = ball_cy + ball_r
    stem_bottom = bar_y0
    stem_width  = max(4, ball_r // 5)

    # Shadow
    draw.polygon([
        (pin_x - stem_width // 2 - 1, stem_top + 2),
        (pin_x + stem_width // 2 + 1, stem_top + 2),
        (pin_x + stem_width // 2 + 1, stem_bottom),
        (pin_x - stem_width // 2 - 1, stem_bottom),
    ], fill=(180, 180, 180))
    # Stem body
    draw.rectangle([
        (pin_x - stem_width // 2, stem_top),
        (pin_x + stem_width // 2, stem_bottom),
    ], fill=(80, 80, 80))

    # ── Pin ball ─────────────────────────────────────────────────────────────────
    # Drop shadow
    shadow_off = max(3, ball_r // 10)
    draw.ellipse([
        (pin_x - ball_r + shadow_off, ball_cy - ball_r + shadow_off),
        (pin_x + ball_r + shadow_off, ball_cy + ball_r + shadow_off),
    ], fill=(180, 180, 180))

    # Ball filled with the band colour
    draw.ellipse([
        (pin_x - ball_r, ball_cy - ball_r),
        (pin_x + ball_r, ball_cy + ball_r),
    ], fill=band_color, outline=BLACK, width=3)

    # Small inner highlight ring
    hi_r = max(3, ball_r // 6)
    draw.ellipse([
        (pin_x - ball_r + 6, ball_cy - ball_r + 6),
        (pin_x - ball_r + 6 + hi_r * 2, ball_cy - ball_r + 6 + hi_r * 2),
    ], fill=WHITE)

    # AQI number centred inside ball
    draw_centered(draw, str(aqi), f_ball_num, band_text_color, pin_x, ball_cy)

    return img


def render_error(message):
    img  = Image.new("RGB", (W, H), WHITE)
    draw = ImageDraw.Draw(img)
    f_h  = load_font(int(H * 0.08), bold=True)
    f_b  = load_font(int(H * 0.05))
    f_sm = load_font(int(H * 0.038))
    draw.rectangle([(0, 0), (W, int(H * 0.22))], fill=RED)
    w, h = tsz(draw, "FETCH ERROR", f_h)
    draw.text((W // 2 - w // 2, int(H * 0.11) - h // 2),
              "FETCH ERROR", font=f_h, fill=WHITE)
    words, line, lines = message.split(), "", []
    for word in words:
        test = (line + " " + word).strip()
        if tsz(draw, test, f_b)[0] > W - 40:
            if line:
                lines.append(line)
            line = word
        else:
            line = test
    if line:
        lines.append(line)
    y = int(H * 0.28)
    for ln in lines[:5]:
        lw, lh = tsz(draw, ln, f_b)
        draw.text((W // 2 - lw // 2, y), ln, font=f_b, fill=BLACK)
        y += lh + 6
    hint = "Set AIRNOW_API_KEY and re-run"
    hw, _ = tsz(draw, hint, f_sm)
    draw.text((W // 2 - hw // 2, H - int(H * 0.1)), hint, font=f_sm, fill=BLACK)
    return img


# ─── Entry point ─────────────────────────────────────────────────────────────────

def main():
    if "YOUR_" in AIRNOW_API_KEY:
        print("=" * 58)
        print("  No AirNow API key set!")
        print("  Free key: https://docs.airnowapi.org/account/request/")
        print("  Then:  export AIRNOW_API_KEY=your-key")
        print("=" * 58)

    print("Fetching AQI for San Francisco…")
    try:
        observations = fetch_aqi()
        best = max(observations, key=lambda x: x.get("AQI", 0))
        print(f"  AQI {best.get('AQI')} "
              f"({best.get('ParameterName')}) — "
              f"{best.get('Category', {}).get('Name', '')}")
        img = render(observations)
    except Exception as e:
        print(f"  ERROR: {e}")
        img = render_error(str(e))

    if INKY_AVAILABLE:
        print("Pushing to Inky (~20 seconds)…")
        inky_display.set_image(img)
        inky_display.show()
        print("Done.")
    else:
        out = "sf_aqi_preview.png"
        img.save(out)
        print(f"Preview saved → {out}")


if __name__ == "__main__":
    main()
