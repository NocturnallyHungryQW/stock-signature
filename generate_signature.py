from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from urllib.request import Request, urlopen

from PIL import Image, ImageDraw, ImageFont

# =========================
# EASY SETTINGS
# =========================

TICKERS_FILE = Path("tickers.txt")
OUTPUT_FILE = Path("stock_signature.png")

IMAGE_WIDTH = 520
ROW_HEIGHT = 42
TOP_BOTTOM_PADDING = 8
LEFT_PADDING = 16

FONT_SIZE = 23
BACKGROUND = (17, 18, 22, 255)
TEXT_COLOR = (245, 245, 245, 255)
GAIN_COLOR = (66, 211, 146, 255)
LOSS_COLOR = (255, 100, 100, 255)
FLAT_COLOR = (190, 190, 190, 255)

TICKER_X = 16
PRICE_X = 155
CHANGE_X = 325

# =========================


def get_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Use a bold monospaced font so every row lines up cleanly."""
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationMono-Bold.ttf",
    ]
    for candidate in candidates:
        if os.path.exists(candidate):
            return ImageFont.truetype(candidate, size)
    return ImageFont.load_default()


def read_tickers() -> list[str]:
    if not TICKERS_FILE.exists():
        raise FileNotFoundError("tickers.txt was not found.")

    tickers: list[str] = []
    for raw_line in TICKERS_FILE.read_text(encoding="utf-8").splitlines():
        symbol = raw_line.strip().upper()
        if symbol and not symbol.startswith("#"):
            tickers.append(symbol)

    if not tickers:
        raise ValueError("tickers.txt must contain at least one ticker.")

    return tickers


def fetch_yahoo_quote(symbol: str) -> tuple[float, float]:
    """
    Fetch the latest regular-market price and daily percentage change.

    This uses Yahoo Finance's public chart endpoint. It requires no login
    or API key, but it is unofficial and may be delayed.
    """
    url = (
        "https://query1.finance.yahoo.com/v8/finance/chart/"
        f"{symbol}?interval=1m&range=1d&includePrePost=false"
    )

    request = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 stock-signature/2.0",
            "Accept": "application/json",
        },
    )

    with urlopen(request, timeout=20) as response:
        payload = json.load(response)

    chart = payload.get("chart", {})
    if chart.get("error"):
        raise RuntimeError(str(chart["error"]))

    results = chart.get("result") or []
    if not results:
        raise RuntimeError("No quote result returned.")

    result = results[0]
    meta = result.get("meta", {})

    price = meta.get("regularMarketPrice")
    previous_close = meta.get("chartPreviousClose") or meta.get("previousClose")

    if price is None:
        closes = (
            result.get("indicators", {})
            .get("quote", [{}])[0]
            .get("close", [])
        )
        valid_closes = [value for value in closes if value is not None]
        if valid_closes:
            price = valid_closes[-1]

    if price is None or previous_close in (None, 0):
        raise RuntimeError("Price or previous close is unavailable.")

    price = float(price)
    previous_close = float(previous_close)
    percent_change = ((price - previous_close) / previous_close) * 100

    return price, percent_change


def render(rows: list[tuple[str, float | None, float | None]]) -> None:
    font = get_font(FONT_SIZE)

    image_height = TOP_BOTTOM_PADDING * 2 + ROW_HEIGHT * len(rows)
    image = Image.new("RGBA", (IMAGE_WIDTH, image_height), BACKGROUND)
    draw = ImageDraw.Draw(image)

    for index, (symbol, price, change) in enumerate(rows):
        y = TOP_BOTTOM_PADDING + index * ROW_HEIGHT + 5

        draw.text((TICKER_X, y), symbol, font=font, fill=TEXT_COLOR)

        if price is None or change is None:
            draw.text((PRICE_X, y), "Unavailable", font=font, fill=FLAT_COLOR)
            continue

        if change > 0:
            arrow = "▲"
            change_color = GAIN_COLOR
        elif change < 0:
            arrow = "▼"
            change_color = LOSS_COLOR
        else:
            arrow = "•"
            change_color = FLAT_COLOR

        draw.text((PRICE_X, y), f"${price:,.2f}", font=font, fill=TEXT_COLOR)
        draw.text(
            (CHANGE_X, y),
            f"{arrow} {change:+.2f}%",
            font=font,
            fill=change_color,
        )

    image.save(OUTPUT_FILE, format="PNG", optimize=True)


def main() -> int:
    rows: list[tuple[str, float | None, float | None]] = []

    for symbol in read_tickers():
        try:
            price, change = fetch_yahoo_quote(symbol)
            rows.append((symbol, price, change))
            print(f"{symbol}: ${price:,.2f} ({change:+.2f}%)")
        except Exception as exc:
            print(f"{symbol}: {exc}", file=sys.stderr)
            rows.append((symbol, None, None))

    render(rows)
    print(f"Created {OUTPUT_FILE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
