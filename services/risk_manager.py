"""Fail-closed broker-spec position sizing and account-level risk checks."""
import math


class RiskManager:
    def __init__(self, max_risk_per_trade=0.01, max_daily_drawdown=0.05,
                 max_total_drawdown=0.10, max_open_trades=3):
        self.max_risk_per_trade = float(max_risk_per_trade)
        self.max_daily_drawdown = float(max_daily_drawdown)
        self.max_total_drawdown = float(max_total_drawdown)
        self.max_open_trades = int(max_open_trades)

    def calculate_lot_size(self, *args, **kwargs):
        """Legacy sizing is intentionally disabled; use broker specifications."""
        return 0.0

    def calculate_volume_from_spec(self, balance, risk_percent, entry, stop_loss, spec):
        try:
            balance, risk_percent = float(balance), float(risk_percent)
            entry, stop_loss = float(entry), float(stop_loss)
            tick_size = float(spec["tickSize"])
            tick_value = float(spec["tickValueAccount"])
            volume_min = float(spec["volumeMin"])
            volume_max = float(spec["volumeMax"])
            volume_step = float(spec["volumeStep"])
            values = (balance, risk_percent, entry, stop_loss, tick_size, tick_value,
                      volume_min, volume_max, volume_step)
            if not all(math.isfinite(v) for v in values):
                return 0.0
            if (balance <= 0 or not 0 < risk_percent <= 2.0 or entry <= 0 or stop_loss <= 0
                    or entry == stop_loss or tick_size <= 0 or tick_value <= 0
                    or volume_min <= 0 or volume_max < volume_min or volume_step <= 0):
                return 0.0
            risk_amount = balance * risk_percent / 100.0
            loss_per_lot = (abs(entry - stop_loss) / tick_size) * tick_value
            if not math.isfinite(loss_per_lot) or loss_per_lot <= 0:
                return 0.0
            raw_volume = min(risk_amount / loss_per_lot, volume_max)
            steps = math.floor(raw_volume / volume_step + 1e-10)
            volume = round(steps * volume_step, 8)
            if volume < volume_min or volume * loss_per_lot > risk_amount + 1e-8:
                return 0.0
            return volume
        except (KeyError, TypeError, ValueError, OverflowError):
            return 0.0

    def trade_allowed(self, current_drawdown, daily_drawdown, open_trades):
        try:
            total = float(current_drawdown)
            daily = float(daily_drawdown)
            count = int(open_trades)
            if not all(math.isfinite(x) for x in (total, daily)) or min(total, daily, count) < 0:
                return False, "Invalid account risk metrics"
            if total >= self.max_total_drawdown * 100:
                return False, "Max total drawdown exceeded"
            if daily >= self.max_daily_drawdown * 100:
                return False, "Max daily drawdown exceeded"
            if count >= self.max_open_trades:
                return False, "Too many open trades"
            return True, "Trade allowed"
        except (TypeError, ValueError, OverflowError):
            return False, "Invalid account risk metrics"

    def minimum_stoploss(self, atr):
        return round(float(atr) * 1.5, 8)

    def take_profit_distance(self, atr, rr=2):
        return round(float(atr) * 1.5 * float(rr), 8)
