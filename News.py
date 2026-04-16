#Heavy claude usage

import os
import re
import math
import requests
from groq import Groq
from datetime import datetime
from collections import defaultdict
from PIL import Image, ImageDraw, ImageFont

# ─── Config ──────────────────────────────────────────────────────────────────────

NEWS_API_KEY = os.environ.get("NEWS_API_KEY", "***")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "***")

NUM_TOPICS    = 5
FETCH_SIZE    = 50    # articles to pull (max 100 free tier)

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

# ─── Spectra 6 palette ───────────────────────────────────────────────────────────

BLACK  = (  0,   0,   0)
WHITE  = (255, 255, 255)
GREEN  = (  0, 170,  60)
BLUE   = ( 30,  80, 200)
RED    = (200,  30,  30)
YELLOW = (220, 200,   0)

# Cycle of accent colors for the topic number badges
BADGE_COLORS = [RED, BLUE, GREEN, YELLOW, (120, 60, 180)]
BADGE_TEXT   = [WHITE, WHITE, BLACK, BLACK, WHITE]

# ─── Font helpers ─────────────────────────────────────────────────────────────────

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

def wrap_text(draw, text, font, max_width):
    """Word-wrap text into lines that fit within max_width pixels."""
    words = text.split()
    lines, line = [], ""
    for word in words:
        test = (line + " " + word).strip()
        if tsz(draw, test, font)[0] <= max_width:
            line = test
        else:
            if line:
                lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines

# ─── NewsAPI fetch ────────────────────────────────────────────────────────────────

def fetch_headlines():
    """Pull top US headlines. Returns list of article dicts."""
    r = requests.get(
        "https://newsapi.org/v2/top-headlines",
        params={
            "country":  "us",
            "pageSize": FETCH_SIZE,
            "apiKey":   NEWS_API_KEY,
        },
        timeout=15,
    )
    r.raise_for_status()
    data = r.json()
    if data.get("status") != "ok":
        raise ValueError(f"NewsAPI error: {data.get('message', 'unknown')}")
    articles = data.get("articles", [])
    # Filter out articles with no title or description
    return [a for a in articles if a.get("title") and a.get("description")]

# ─── Topic clustering ─────────────────────────────────────────────────────────────

# Common English stop words to ignore when finding topic keywords
STOP_WORDS = {
    "the","a","an","and","or","but","in","on","at","to","for","of","with",
    "by","from","is","are","was","were","be","been","has","have","had",
    "it","its","this","that","these","those","he","she","they","we","i",
    "his","her","their","our","as","up","out","about","than","into","through",
    "after","over","new","says","say","said","will","can","not","no","more",
    "also","after","what","how","who","when","where","why","us","s","after",
    "amid","after","after","report","reports","just","could","would","should",
    "one","two","three","first","last","year","years","day","days","week",
    "may","might","now","still","back","get","gets","make","makes","take",
}

def extract_keywords(text, n=8):
    """Pull the n most meaningful words from a string."""
    words = re.findall(r"[a-zA-Z]{4,}", text.lower())
    return [w for w in words if w not in STOP_WORDS][:n]

def cluster_articles(articles, num_topics=5):
    """
    Greedy keyword-overlap clustering.
    Returns list of (topic_keywords, [article, ...]) tuples,
    sorted by cluster size descending.
    """
    # Build keyword sets per article
    keyed = []
    for a in articles:
        text = (a.get("title", "") + " " + a.get("description", "")).lower()
        kws  = set(extract_keywords(text, n=10))
        keyed.append((kws, a))

    clusters = []   # list of (set_of_shared_kws, [articles])

    for kws, article in keyed:
        best_idx   = -1
        best_score = 1   # need at least 2 shared keywords to merge

        for i, (ckws, _) in enumerate(clusters):
            score = len(kws & ckws)
            if score > best_score:
                best_score = score
                best_idx   = i

        if best_idx >= 0:
            ckws, cart = clusters[best_idx]
            clusters[best_idx] = (ckws | kws, cart + [article])
        else:
            clusters.append((kws, [article]))

    # Sort by number of articles (most covered first)
    clusters.sort(key=lambda x: len(x[1]), reverse=True)
    return clusters[:num_topics]

def topic_label(keywords, articles):
    """
    Derive a short topic label from the most common meaningful words
    across article titles in this cluster.
    """
    freq = defaultdict(int)
    for a in articles:
        for w in extract_keywords(a.get("title", ""), n=6):
            freq[w] += 1
    top = sorted(freq, key=freq.get, reverse=True)[:3]
    return " · ".join(w.capitalize() for w in top) if top else "News"

# ─── Claude summarisation ─────────────────────────────────────────────────────────

def summarise_topic(client, articles):
    """Call Groq for a single cluster. Returns (label, summary)."""
    headlines = "\n".join(f"  - {a['title']}" for a in articles[:6])
    prompt = (
        "You are a news editor writing for an e-ink display.\n"
        "Below are headlines about ONE news topic.\n"
        "Respond with exactly two lines and nothing else:\n"
        "LABEL: <3-5 word title case label, no punctuation>\n"
        "SUMMARY: <one full sentence with details, between 15-25 words, don't lose the true meaning of the articles or important details>\n\n"
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


def summarise_topics(clusters):
    """Call Groq once per cluster. Returns list of (label, summary) tuples."""
    client = Groq(api_key=GROQ_API_KEY)
    topics = []
    for i, (kws, articles) in enumerate(clusters):
        print(f"  Summarising topic {i+1}/{len(clusters)}…")
        label, summary = summarise_topic(client, articles)
        topics.append((label, summary))
    return topics

# ─── Render ──────────────────────────────────────────────────────────────────────

def render(topics, updated_str):
    img  = Image.new("RGB", (W, H), WHITE)
    draw = ImageDraw.Draw(img)

    if not topics:
        draw.text((20, 20), "No topics available.", font=load_font(32, bold=True), fill=BLACK)
        return img

    PAD    = 16
    BORDER = 2

    # Fonts
    f_head    = load_font(int(H * 0.052), bold=True)
    f_ts      = load_font(int(H * 0.034))
    f_label   = load_font(int(H * 0.050), bold=True)
    f_summary = load_font(int(H * 0.038))
    f_badge   = load_font(int(H * 0.046), bold=True)

    # ── Header bar ────────────────────────────────────────────────────────────────
    HEAD_H = int(H * 0.115)
    draw.rectangle([(0, 0), (W, HEAD_H)], fill=BLACK)

    _, hh = tsz(draw, "X", f_head)
    draw.text((PAD * 2, HEAD_H // 2 - hh // 2),
              "Top News Today", font=f_head, fill=WHITE)

    tw, th = tsz(draw, updated_str, f_ts)
    draw.text((W - tw - PAD * 2, HEAD_H // 2 - th // 2),
              updated_str, font=f_ts, fill=WHITE)

    # ── Topic rows ────────────────────────────────────────────────────────────────
    n          = len(topics)
    content_h  = H - HEAD_H
    row_h      = content_h // n

    # Badge dimensions (square, left-aligned)
    badge_size = int(row_h * 0.52)
    badge_size = max(28, min(badge_size, 56))

    for i, (label, summary) in enumerate(topics):
        ry0    = HEAD_H + i * row_h
        ry1    = ry0 + row_h
        row_cy = (ry0 + ry1) // 2

        # Separator line (skip first)
        if i > 0:
            draw.line([(PAD, ry0), (W - PAD, ry0)], fill=(180, 180, 180), width=1)

        # ── Number badge ──────────────────────────────────────────────────────────
        badge_col  = BADGE_COLORS[i % len(BADGE_COLORS)]
        badge_tcol = BADGE_TEXT[i % len(BADGE_TEXT)]
        bx0 = PAD
        by0 = row_cy - badge_size // 2
        bx1 = bx0 + badge_size
        by1 = by0 + badge_size

        draw.rounded_rectangle([(bx0, by0), (bx1, by1)],
                                radius=6, fill=badge_col, outline=BLACK, width=2)
        num_str = str(i + 1)
        nw, nh  = tsz(draw, num_str, f_badge)
        draw.text((bx0 + badge_size // 2 - nw // 2,
                   by0 + badge_size // 2 - nh // 2),
                  num_str, font=f_badge, fill=badge_tcol)

        # ── Text area to the right of badge ───────────────────────────────────────
        tx0     = bx1 + PAD
        txt_w   = W - tx0 - PAD

        # Label line
        lw, lh  = tsz(draw, label, f_label)
        # Truncate label if too wide
        while lw > txt_w and len(label) > 4:
            label = label[:-2] + "…"
            lw, lh = tsz(draw, label, f_label)

        # Summary wrapped
        sum_lines = wrap_text(draw, summary, f_summary, txt_w)
        _, slh    = tsz(draw, "X", f_summary)
        SUM_LINE_SPACING = int(slh * 1.5)   # extra breathing room between wrapped lines
        LABEL_GAP        = int(lh * 0.40)   # gap between label and first summary line

        # Vertical layout: centre the label+summary block in the row
        num_sum_lines = min(len(sum_lines), 2)
        total_text_h  = lh + LABEL_GAP + SUM_LINE_SPACING * num_sum_lines
        text_y0       = row_cy - total_text_h // 2

        draw.text((tx0, text_y0), label, font=f_label, fill=BLACK)

        sy = text_y0 + lh + LABEL_GAP
        for line in sum_lines[:2]:   # max 2 summary lines to fit row
            draw.text((tx0, sy), line, font=f_summary, fill=(60, 60, 60))
            sy += SUM_LINE_SPACING

    return img


def render_error(message):
    img  = Image.new("RGB", (W, H), WHITE)
    draw = ImageDraw.Draw(img)
    f_h  = load_font(int(H * 0.07), bold=True)
    f_b  = load_font(int(H * 0.048))
    draw.rectangle([(0, 0), (W, int(H * 0.2))], fill=RED)
    tw, th = tsz(draw, "ERROR", f_h)
    draw.text((W // 2 - tw // 2, int(H * 0.1) - th // 2),
              "ERROR", font=f_h, fill=WHITE)
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
    y = int(H * 0.26)
    for ln in lines[:6]:
        lw, lh = tsz(draw, ln, f_b)
        draw.text((W // 2 - lw // 2, y), ln, font=f_b, fill=BLACK)
        y += lh + 4
    return img


# ─── Entry point ─────────────────────────────────────────────────────────────────

def main():
    for key, name, url in [
        (NEWS_API_KEY, "NEWS_API_KEY", "newsapi.org/register"),
        (GROQ_API_KEY, "GROQ_API_KEY", "console.groq.com"),
    ]:
        if "YOUR_" in key:
            print(f"  {name} not set — get a free key at {url}")

    print("Fetching headlines…")
    try:
        articles = fetch_headlines()
        print(f"  Got {len(articles)} articles")

        print("Clustering into topics…")
        clusters = cluster_articles(articles, num_topics=NUM_TOPICS)
        print(f"  Found {len(clusters)} clusters "
              f"(sizes: {[len(c[1]) for c in clusters]})")

        print("Generating summaries with Groq…")
        topics = summarise_topics(clusters)
        print(f"  Got {len(topics)} summaries")
        for label, summary in topics:
            print(f"    • {label}: {summary}")

        updated = datetime.now().strftime("%-I:%M %p · %b %-d")
        img = render(topics, updated)

    except Exception as e:
        print(f"  ERROR: {e}")
        img = render_error(str(e))

    if INKY_AVAILABLE:
        print("Pushing to Inky (~20 seconds)…")
        inky_display.set_image(img)
        inky_display.show()
        print("Done.")
    else:
        out = "news_preview.png"
        img.save(out)
        print(f"Preview saved → {out}")


if __name__ == "__main__":
    main()
