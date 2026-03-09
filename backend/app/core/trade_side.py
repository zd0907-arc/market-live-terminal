from typing import Any

# Support multiple upstream type vocabularies:
# - Chinese: 买盘/卖盘/中性盘
# - English: buy/sell/neutral
# - Single-letter: B/S/M
BUY_MARKERS = {"买盘", "buy", "B", "b"}
SELL_MARKERS = {"卖盘", "sell", "S", "s"}
NEUTRAL_MARKERS = {"中性盘", "neutral", "M", "m"}


def _normalize_scalar(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def is_buy_series(series):
    normalized = series.astype(str).str.strip()
    return normalized.isin(BUY_MARKERS)


def is_sell_series(series):
    normalized = series.astype(str).str.strip()
    return normalized.isin(SELL_MARKERS)


def normalize_trade_side(value: Any) -> str:
    marker = _normalize_scalar(value)
    if marker in BUY_MARKERS:
        return "buy"
    if marker in SELL_MARKERS:
        return "sell"
    return "neutral"

