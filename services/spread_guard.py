"""Single spread policy. FX spread is in pips; XAU/crypto are price units."""
import math


class SpreadGuard:
    def __init__(self, max_spread_major=2.0, max_spread_gold=5.0, max_spread_crypto=30.0):
        self.max_spread_major = float(max_spread_major)
        self.max_spread_gold = float(max_spread_gold)
        self.max_spread_crypto = float(max_spread_crypto)

    def get_limit(self, symbol):
        symbol = str(symbol).upper()
        if "XAU" in symbol:
            return self.max_spread_gold
        if any(x in symbol for x in ("BTC", "ETH")):
            return self.max_spread_crypto
        return self.max_spread_major

    def safe(self, symbol, spread):
        try:
            spread = float(spread)
            return math.isfinite(spread) and 0 <= spread <= self.get_limit(symbol)
        except (TypeError, ValueError, OverflowError):
            return False
