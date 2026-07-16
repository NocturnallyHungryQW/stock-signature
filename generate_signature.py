from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

from PIL import Image, ImageDraw, ImageFont

OUTPUT = Path("stock_signature.png")
TICKERS_FILE = Path("tickers.txt")

# Appearance
BACKGROUND = (18, 18, 20, 255)
TEXT = (245, 245, 245, 255)
POSITIVE = (55, 205, 120, 255)
NEGATIVE = (245, 85, 85, 255)
FLAT = (185, 185, 185, 255)

ROW_HEIGHT = 48
PADDING_X = 16
PADDING_Y = 8
FONT_SIZE = 24
WIDTH = 500


def font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def load_tickers() -> list[str]:
    if not TICKERS_FILE.exists():
        raise FileNotFoundError("tickers.txt is missing")
    tickers = []
    for line in TICKERS_FILE.read_text(encoding="utf-8").splitlines():
        symbol = line.strip().upper()
        if symbol and not symbol.startswith("#"):
            tickers.append(symbol)
    if not tickers:
        raise ValueError("Add at least one ticker to tickers.txt")
    return tickers


def fetch_quote(symbol: str) -> tuple[float, float]:
    # Unofficial Yahoo Finance chart endpoint. No login or API key is required.
    url = (
        "https://query1.finance.yahoo.com/v8/finance/chart/"
        f"{symbol}?interval=1m&range=1d&includePrePost=false"
    )
    request = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json",
        },
    )
    with urlopen(request, timeout=20) as response:
        payload = json.load(response)

    result = payload["chart"]["result"][0]
    meta = result["meta"]

    price = meta.get("regularMarketPrice")
    previous_close = meta.get("chartPreviousClose") or meta.get("previousClose")

    if price is None:
        closes = result.get("indicators", {}).get("quote", [{}])[0].get("close", [])
        valid = [value for value in closes if value is not None]
        if valid:
            price = valid[-1]

    if price is None or previous_close in (None, 0):
        raise ValueError(f"Quote data unavailable for {symbol}")

    percent = ((float(price) - float(previous_close)) / float(previous_close)) * 100
    return float(price), percent


def draw_signature(rows: list[tuple[str, float | None, float | None]]) -> None:
    height = PADDING_Y * 2 + ROW_HEIGHT * len(rows)
    image = Image.new("RGBA", (WIDTH, height), BACKGROUND)
    draw = ImageDraw.Draw(image)
    main_font = font(FONT_SIZE)

    ticker_x = PADDING_X
    price_x = 150
    change_x = 310

    for index, (symbol, price, percent) in enumerate(rows):
        y = PADDING_Y + index * ROW_HEIGHT
        text_y = y + 8

        draw.text((ticker_x, text_y), symbol, font=main_font, fill=TEXT)

        if price is None or percent is None:
            draw.text((price_x, text_y), "Unavailable", font=main_font, fill=FLAT)
            continue

        arrow = "▲" if percent > 0 else "▼" if percent < 0 else "•"
        change_color = POSITIVE if percent > 0 else NEGATIVE if percent < 0 else FLAT

        draw.text((price_x, text_y), f"${price:,.2f}", font=main_font, fill=TEXT)
        draw.text(
            (change_x, text_y),
            f"{arrow} {percent:+.2f}%",
            font=main_font,
            fill=change_color,
        )

    image.save(OUTPUT, optimize=True)


def main() -> int:
    tickers = load_tickers()
    rows = []

    for symbol in tickers:
        try:
            price, percent = fetch_quote(symbol)
            rows.append((symbol, price, percent))
        except Exception as exc:
            print(f"{symbol}: {exc}", file=sys.stderr)
            rows.append((symbol, None, None))

    draw_signature(rows)
    print(f"Updated {OUTPUT} at {datetime.now(timezone.utc).isoformat()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
