#Heavy claude usage

import sys
import time
import random
import signal
import requests
import pygame
from PIL import Image

# ── Display constants ──────────────────────────────────────────────────────────
DISPLAY_WIDTH  = 800
DISPLAY_HEIGHT = 480

# Inky Impressions 7-colour palette
INKY_BLACK  = (  0,   0,   0)
INKY_WHITE  = (255, 255, 255)
INKY_RED    = (200,   0,   0)
INKY_YELLOW = (220, 180,   0)
INKY_GREY   = (160, 160, 160)

BG_COLOUR     = INKY_WHITE
QUOTE_COLOUR  = INKY_BLACK
MOVIE_COLOUR  = (160,   0,   0)   # Dark red — readable on white
ACCENT_COLOUR = INKY_RED
FOOTER_COLOUR = (100, 100, 100)   # Dark grey

MARGIN          = 50
QUOTE_TOP       = 90
MAX_QUOTE_W     = DISPLAY_WIDTH - MARGIN * 2
REFRESH_SECONDS = 120
REQUEST_TIMEOUT = 8

# ── Built-in quote bank (always available, no internet needed) ─────────────────
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
    ("You is kind, you is smart, you is important.", "The Help (2011)"),
    ("Nobody puts Baby in a corner.", "Dirty Dancing (1987)"),
    ("I am your father.", "The Empire Strikes Back (1980)"),
    ("E.T. phone home.", "E.T. the Extra-Terrestrial (1982)"),
    ("Frankly, my dear, I don't give a damn.", "Gone with the Wind (1939)"),
    ("A martini. Shaken, not stirred.", "Goldfinger (1964)"),
    ("I'm going to make him an offer he can't refuse.", "The Godfather (1972)"),
    ("Get busy living, or get busy dying.", "The Shawshank Redemption (1994)"),
    ("Do. Or do not. There is no try.", "The Empire Strikes Back (1980)"),
    ("Carpe diem. Seize the day, boys.", "Dead Poets Society (1989)"),
    ("All those moments will be lost in time, like tears in rain.", "Blade Runner (1982)"),
    ("You either die a hero, or live long enough to see yourself become the villain.",
     "The Dark Knight (2008)"),
    ("After all, tomorrow is another day!", "Gone with the Wind (1939)"),
    ("Roads? Where we're going we don't need roads.", "Back to the Future (1985)"),
    ("Bond. James Bond.", "Dr. No (1962)"),
    ("I feel the need — the need for speed!", "Top Gun (1986)"),
    ("The stuff that dreams are made of.", "The Maltese Falcon (1941)"),
    ("It ain't about how hard you hit. It's about how hard you can get hit and keep moving forward.",
     "Rocky Balboa (2006)"),
    ("Elementary, my dear Watson.", "The Adventures of Sherlock Holmes (1939)"),
    ("I'm not bad. I'm just drawn that way.", "Who Framed Roger Rabbit (1988)"),
    ("It's alive! It's alive!", "Frankenstein (1931)"),
    ("They may take our lives, but they'll never take our freedom!", "Braveheart (1995)"),
    ("To boldly go where no man has gone before.", "Star Trek (1979)"),
    ("I am Groot.", "Guardians of the Galaxy (2014)"),
]

# Shuffle so repeats are spread out
random.shuffle(BUILTIN_QUOTES)
_builtin_index = 0


def next_builtin_quote() -> tuple[str, str]:
    global _builtin_index
    q, m = BUILTIN_QUOTES[_builtin_index % len(BUILTIN_QUOTES)]
    _builtin_index += 1
    return (f'"{q}"', m)


def fetch_online_quote() -> tuple[str, str] | None:
    """Try a free no-auth quotes API. Returns None on any failure."""
    try:
        r = requests.get(
            "https://api.quotable.io/random",
            timeout=REQUEST_TIMEOUT,
        )
        r.raise_for_status()
        data   = r.json()
        quote  = data.get("content", "").strip()
        author = data.get("author", "").strip()
        if quote and author:
            return (f'"{quote}"', author)
    except Exception:
        pass
    return None


def get_quote() -> tuple[str, str]:
    """Return (quote_text, source). Always succeeds."""
    online = fetch_online_quote()
    if online:
        return online
    return next_builtin_quote()


# ── Text helpers ───────────────────────────────────────────────────────────────

def wrap_text(text: str, font: pygame.font.Font, max_width: int) -> list[str]:
    words   = text.split()
    lines   = []
    current = ""
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


def best_fit_font(text: str, max_width: int, max_height: int,
                  size_max: int = 40, size_min: int = 18):
    """Return (font, wrapped_lines) at the largest size that still fits."""
    for size in range(size_max, size_min - 1, -2):
        font  = pygame.font.SysFont("dejavuserif", size, italic=True) \
                or pygame.font.Font(None, size)
        lines = wrap_text(text, font, max_width)
        if len(lines) * font.get_linesize() <= max_height:
            return font, lines
    font = pygame.font.Font(None, size_min)
    return font, wrap_text(text, font, max_width)


# ── Rendering ──────────────────────────────────────────────────────────────────

def render(screen: pygame.Surface, fonts: dict,
           quote: str, source: str, status: str = "") -> None:
    screen.fill(BG_COLOUR)
    w, h = screen.get_size()

    # Header
    hdr = fonts["title"].render("  Famous Movie Quotes", True, MOVIE_COLOUR)
    screen.blit(hdr, (MARGIN, 18))
    pygame.draw.line(screen, ACCENT_COLOUR, (MARGIN, 58), (w - MARGIN, 58), 2)

    # Vertical space budget
    footer_h  = 40
    source_h  = fonts["movie"].get_linesize() + 16
    avail_h   = h - QUOTE_TOP - source_h - footer_h

    qfont, lines = best_fit_font(quote, MAX_QUOTE_W, avail_h)
    line_h       = qfont.get_linesize()
    block_h      = len(lines) * line_h
    start_y      = QUOTE_TOP + max(0, (avail_h - block_h) // 2)

    for i, line in enumerate(lines):
        surf = qfont.render(line, True, QUOTE_COLOUR)
        screen.blit(surf, (MARGIN, start_y + i * line_h))

    # Source line
    src_surf = fonts["movie"].render(f"— {source}", True, MOVIE_COLOUR)
    screen.blit(src_surf, (MARGIN, start_y + block_h + 14))

    # Footer
    footer_y = h - footer_h
    pygame.draw.line(screen, ACCENT_COLOUR,
                     (MARGIN, footer_y - 6), (w - MARGIN, footer_y - 6), 1)
    ts  = time.strftime("%H:%M:%S")
    ftxt = f"Updated {ts}  •  refreshes every {REFRESH_SECONDS}s"
    if status:
        ftxt = f"[{status}]  " + ftxt
    fsuf = fonts["footer"].render(ftxt, True, FOOTER_COLOUR)
    screen.blit(fsuf, (MARGIN, footer_y + 4))


# ── Hardware push ──────────────────────────────────────────────────────────────

def push_to_inky(screen: pygame.Surface) -> None:
    """Send the pygame surface to the physical Inky display."""
    try:
        from inky.auto import auto

        inky    = auto(ask_user=False, verbose=True)
        raw     = pygame.image.tostring(screen, "RGB")
        pil_img = Image.frombytes("RGB", (DISPLAY_WIDTH, DISPLAY_HEIGHT), raw)
        pil_img = pil_img.resize(inky.resolution)
        inky.set_image(pil_img)
        inky.show()   # blocks ~30 s while e-ink refreshes — completely normal
        print("[INFO] Inky display updated.")
    except ImportError:
        print("[WARN] 'inky' library not found — skipping hardware push.")
    except KeyboardInterrupt:
        # Ctrl-C arrived during the 30-second e-ink busy-wait. Re-raise so
        # main() can do a clean shutdown instead of printing a traceback.
        raise
    except Exception as e:
        print(f"[WARN] Inky push failed: {e}")


# ── Graceful Ctrl-C ────────────────────────────────────────────────────────────

_running = True

def _sigint(sig, frame):
    global _running
    print("\n[INFO] Interrupt received — shutting down cleanly…")
    _running = False

signal.signal(signal.SIGINT, _sigint)


# ── Main loop ──────────────────────────────────────────────────────────────────

def main() -> None:
    global _running

    pygame.init()
    screen = pygame.display.set_mode((DISPLAY_WIDTH, DISPLAY_HEIGHT))
    pygame.display.set_caption('Movie Quotes — Inky Impressions 7.3"')

    def sf(name, size, bold=False, italic=False):
        return pygame.font.SysFont(name, size, bold=bold, italic=italic) \
               or pygame.font.Font(None, size)

    fonts = {
        "title":  sf("dejavusans",      22, bold=True),
        "movie":  sf("dejavusans",      26, bold=True),
        "footer": sf("dejavusansmono",  17),
    }

    clock      = pygame.time.Clock()
    last_fetch = -REFRESH_SECONDS   # trigger immediate fetch on startup
    quote, source = "", ""

    print(f"[INFO] Started. Resolution {DISPLAY_WIDTH}x{DISPLAY_HEIGHT},"
          f" refresh every {REFRESH_SECONDS}s. Ctrl+C to quit.")

    while _running:
        # Window close / key press
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                _running = False
            elif event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_q, pygame.K_ESCAPE):
                    _running = False

        if not _running:
            break

        now = time.time()
        if now - last_fetch >= REFRESH_SECONDS:
            print("[INFO] Fetching quote…")
            try:
                quote, source = get_quote()
                status = ""
            except Exception as e:
                quote  = '"Could not load a quote right now."'
                source = "Unknown"
                status = f"error: {e}"

            print(f"[INFO]  → {source}")
            last_fetch = now

            render(screen, fonts, quote, source, status)
            pygame.display.flip()

            try:
                push_to_inky(screen)
            except KeyboardInterrupt:
                _running = False

        clock.tick(10)

    pygame.quit()
    print("[INFO] Exited cleanly.")
    sys.exit(0)


if __name__ == "__main__":
    main()
