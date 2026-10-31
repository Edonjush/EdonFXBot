"""Instrument-aware volatility checks. ATR is normalized by price; spread is
checked only by SpreadGuard, which owns spread units and limits.
"""
import math

# Maximum M5 ATR as a fraction of the latest close. These are conservative
# guardrails, not optimized strategy parameters; validate against OOS data.
MAX_ATR_PCT = {
    "FOREX": 0.0015,   # 0.15%
    "GOLD": 0.0035,    # 0.35%
    "CRYPTO": 0.0100,  # 1.00%
}


def volatility_safe(atr, close=None, symbol="EURUSD", spread=None):
    """Return False on missing/non-finite inputs or excessive normalized ATR.

    `spread` remains an optional compatibility argument but is deliberately
    not evaluated here; SpreadGuard is the single authority for spread units.
    """
    try:
        atr = float(atr)
        close = float(close)
        symbol = str(symbol).upper()
        if not math.isfinite(atr) or not math.isfinite(close) or atr <= 0 or close <= 0:
            return False
        category = "GOLD" if "XAU" in symbol else (
            "CRYPTO" if any(x in symbol for x in ("BTC", "ETH")) else "FOREX"
        )
        return (atr / close) <= MAX_ATR_PCT[category]
    except (TypeError, ValueError, OverflowError):
        return False
