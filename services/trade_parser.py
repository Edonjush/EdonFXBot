# services/trade_parser.py

import re
import logging

from constants.symbols import SYMBOLS
from config.settings import RISK_FACTOR

logger = logging.getLogger(__name__)

ORDER_TYPES = [
    "Buy Limit",
    "Sell Limit",
    "Buy Stop",
    "Sell Stop",
    "Buy",
    "Sell",
]

NUMBER_RE = re.compile(r"[-+]?\d*\.?\d+")


def _extract_number(text: str):
    match = NUMBER_RE.search(text.replace(",", ""))

    if not match:
        return None

    try:
        return float(match.group())
    except ValueError:
        return None


def _detect_order_type(line: str):
    line_lower = line.lower()

    for order_type in ORDER_TYPES:
        if order_type.lower() in line_lower:
            return order_type

    return None


def _detect_symbol(line: str, order_type: str):
    cleaned = re.sub(re.escape(order_type), "", line, flags=re.IGNORECASE).strip()

    tokens = re.findall(r"[A-Za-z]{3,10}", cleaned)

    for token in tokens:
        candidate = token.upper().replace("/", "")
        if candidate in SYMBOLS:
            return candidate

    return None


def _validate_trade_levels(trade: dict) -> bool:
    """
    Directional sanity check: SL/TP must sit on the correct side of
    entry for the order direction. Skipped when entry is unknown
    (e.g. a market order with no live price attached yet).
    """

    entry = trade.get("Entry")

    if not isinstance(entry, (int, float)):
        return True

    sl = trade["StopLoss"]
    tps = trade["TP"]

    is_buy = trade["OrderType"].startswith("Buy")

    if is_buy:
        if sl >= entry:
            return False
        if any(tp <= entry for tp in tps):
            return False
    else:
        if sl <= entry:
            return False
        if any(tp >= entry for tp in tps):
            return False

    return True


def ParseSignal(signal: str) -> dict:
    """
    Parses a raw trade signal into a structured trade dict.

    Expected loose format (labels are optional, only the numbers matter):

        Buy Limit EURUSD
        Entry: 1.2345          (for Buy/Sell market orders this can say "Market")
        SL: 1.2300
        TP: 1.2400
        TP: 1.2450             (additional TP lines are optional)

    Returns {} on any parsing failure. Never raises.
    """

    if not signal or not signal.strip():
        logger.warning("ParseSignal: empty signal")
        return {}

    lines = [line.strip() for line in signal.splitlines() if line.strip()]

    if len(lines) < 3:
        logger.warning("ParseSignal: signal too short (%d lines)", len(lines))
        return {}

    trade = {}

    # ---- ORDER TYPE ----
    order_type = _detect_order_type(lines[0])

    if order_type is None:
        logger.warning("ParseSignal: no order type found in %r", lines[0])
        return {}

    trade["OrderType"] = order_type

    # ---- SYMBOL ----
    symbol = _detect_symbol(lines[0], order_type)

    if symbol is None:
        logger.warning("ParseSignal: unrecognized symbol in %r", lines[0])
        return {}

    trade["Symbol"] = symbol

    # ---- ENTRY ----
    is_market_order = order_type in ("Buy", "Sell")
    entry_value = _extract_number(lines[1])

    if is_market_order:
        trade["Entry"] = entry_value if entry_value is not None else "Market"
    else:
        if entry_value is None:
            logger.warning("ParseSignal: missing entry price for pending order")
            return {}
        trade["Entry"] = entry_value

    # ---- STOP LOSS ----
    sl_value = _extract_number(lines[2])

    if sl_value is None:
        logger.warning("ParseSignal: could not parse stop loss from %r", lines[2])
        return {}

    trade["StopLoss"] = sl_value

    # ---- TAKE PROFIT(S) ----
    tp_values = [tp for tp in (_extract_number(line) for line in lines[3:]) if tp is not None]

    if not tp_values:
        logger.warning("ParseSignal: no take profit levels found")
        return {}

    trade["TP"] = tp_values

    # ---- SANITY CHECK ----
    if not _validate_trade_levels(trade):
        logger.warning("ParseSignal: trade levels failed sanity check: %s", trade)
        return {}

    trade["RiskFactor"] = RISK_FACTOR

    return trade
