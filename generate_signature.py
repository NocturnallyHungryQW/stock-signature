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

ROW_HEIGHT = 42
TOP_BOTTOM_PADDING = 8
LEFT_PADDING = 16
RIGHT_PADDING = 16
COLUMN_GAP = 28

FONT_SIZE = 23

BACKGROUND = (17, 18, 22, 255)
TEXT_COLOR = (245, 245, 245, 255)
GAIN_COLOR = (66, 211, 146, 255)
LOSS_COLOR = (255, 100, 100, 255)
FLAT_COLOR = (190, 190, 190, 255)


# =========================
# FONT
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


# =========================
# TICKER FILE
# =========================

def read_tickers() -> list[str]:
    if not TICKERS_FILE.exists():
        raise FileNotFoundError("tickers.txt was not found.")

    tickers: list[str] = []

    for raw_line in TICKERS_FILE.read_text(encoding="utf-8").splitlines():
        symbol = raw_line.strip().upper()

        # Ignore blank lines and comment lines.
        if symbol and not symbol.startswith("#"):
            tickers.append(symbol)

    if not tickers:
        raise ValueError("tickers.txt must contain at least one ticker.")

    return tickers


# =========================
# QUOTE DATA
# =========================

def fetch_yahoo_quote(symbol: str) -> tuple[float, float]:
    """
    Fetch the latest regular-market price and daily percentage change.

    Uses Yahoo Finance's public chart endpoint.
    No login or API key is required.
    """

    url = (
        "https://query1.finance.yahoo.com/v8/finance/chart/"
        f"{symbol}?interval=1m&range=1d&includePrePost=false"
    )

    request = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 stock-signature/1.1",
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
    previous_close = (
        meta.get("chartPreviousClose")
        or meta.get("previousClose")
    )

    # Fallback to the most recent intraday close if needed.
    if price is None:
        closes = (
            result.get("indicators", {})
            .get("quote", [{}])[0]
            .get("close", [])
        )

        valid_closes = [
            value
            for value in closes
            if value is not None
        ]

        if valid_closes:
            price = valid_closes[-1]

    if price is None or previous_close in (None, 0):
        raise RuntimeError(
            "Price or previous close is unavailable."
        )

    price = float(price)
    previous_close = float(previous_close)

    percent_change = (
        (price - previous_close)
        / previous_close
        * 100
    )

    return price, percent_change


# =========================
# IMAGE GENERATION
# =========================

def render(
    rows: list[
        tuple[str, float | None, float | None]
    ]
) -> None:

    font = get_font(FONT_SIZE)

    prepared_rows: list[
        tuple[str, str, str, tuple[int, int, int, int]]
    ] = []

    # Build the exact text that will appear in every row.
    for symbol, price, change in rows:

        if price is None or change is None:
            price_text = "Unavailable"
            change_text = ""
            change_color = FLAT_COLOR

        else:
            price_text = f"${price:,.2f}"

            if change > 0:
                arrow = "▲"
                change_color = GAIN_COLOR

            elif change < 0:
                arrow = "▼"
                change_color = LOSS_COLOR

            else:
                arrow = "•"
                change_color = FLAT_COLOR

            change_text = f"{arrow} {change:+.2f}%"

        prepared_rows.append(
            (
                symbol,
                price_text,
                change_text,
                change_color,
            )
        )

    # Create a tiny temporary image only for measuring text.
    dummy_image = Image.new(
        "RGBA",
        (1, 1),
        (0, 0, 0, 0),
    )

    measure = ImageDraw.Draw(dummy_image)

    # Measure the widest ticker.
    ticker_width = max(
        measure.textbbox(
            (0, 0),
            ticker,
            font=font,
        )[2]
        for ticker, _, _, _ in prepared_rows
    )

    # Measure the widest price.
    price_width = max(
        measure.textbbox(
            (0, 0),
            price_text,
            font=font,
        )[2]
        for _, price_text, _, _ in prepared_rows
    )

    # Measure the widest percentage-change value.
    change_width = max(
        (
            measure.textbbox(
                (0, 0),
                change_text,
                font=font,
            )[2]
            if change_text
            else 0
        )
        for _, _, change_text, _ in prepared_rows
    )

    # Automatically calculate image width.
    image_width = (
        LEFT_PADDING
        + ticker_width
        + COLUMN_GAP
        + price_width
        + COLUMN_GAP
        + change_width
        + RIGHT_PADDING
    )

    # Automatically calculate image height.
    image_height = (
        TOP_BOTTOM_PADDING * 2
        + ROW_HEIGHT * len(prepared_rows)
    )

    image = Image.new(
        "RGBA",
        (image_width, image_height),
        BACKGROUND,
    )

    draw = ImageDraw.Draw(image)

    # Automatically calculate the three column positions.
    ticker_x = LEFT_PADDING

    price_x = (
        ticker_x
        + ticker_width
        + COLUMN_GAP
    )

    change_x = (
        price_x
        + price_width
        + COLUMN_GAP
    )

    # Draw one ticker per row.
    for index, (
        symbol,
        price_text,
        change_text,
        change_color,
    ) in enumerate(prepared_rows):

        y = (
            TOP_BOTTOM_PADDING
            + index * ROW_HEIGHT
            + 5
        )

        draw.text(
            (ticker_x, y),
            symbol,
            font=font,
            fill=TEXT_COLOR,
        )

        draw.text(
            (price_x, y),
            price_text,
            font=font,
            fill=TEXT_COLOR,
        )

        if change_text:
            draw.text(
                (change_x, y),
                change_text,
                font=font,
                fill=change_color,
            )

    image.save(
        OUTPUT_FILE,
        format="PNG",
        optimize=True,
    )


# =========================
# MAIN
# =========================

def main() -> int:

    rows: list[
        tuple[str, float | None, float | None]
    ] = []

    for symbol in read_tickers():

        try:
            price, change = fetch_yahoo_quote(symbol)

            rows.append(
                (
                    symbol,
                    price,
                    change,
                )
            )

            print(
                f"{symbol}: "
                f"${price:,.2f} "
                f"({change:+.2f}%)"
            )

        except Exception as exc:
            print(
                f"{symbol}: {exc}",
                file=sys.stderr,
            )

            rows.append(
                (
                    symbol,
                    None,
                    None,
                )
            )

    render(rows)

    print(
        f"Created {OUTPUT_FILE} "
        f"with {len(rows)} ticker(s)."
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
