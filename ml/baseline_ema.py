import sys
import numpy as np
import pandas as pd
import ta

PIP = 0.0001
COSTS = (0.0, 1.0, 1.5, 2.0, 3.0)
DEFAULT_COST = 1.5
TRAIN_FRAC, VALID_FRAC = 0.60, 0.20
ATR_RISK_MULT = 1.25


def load(path):
    df = pd.read_csv(path)
    df["datetime"] = pd.to_datetime(df["datetime"], errors="coerce")
    for c in ("open", "high", "low", "close"):
        df[c] = pd.to_numeric(df[c], errors="coerce")

    valid = (
        (df["high"] >= df[["open", "close", "low"]].max(axis=1))
        & (df["low"] <= df[["open", "close", "high"]].min(axis=1))
    )
    malformed = (~valid).fillna(True)

    return (
        df.dropna(subset=["datetime", "open", "high", "low", "close"])
        .loc[~malformed.loc[df.index]]
        .sort_values("datetime")
        .drop_duplicates("datetime")
        .reset_index(drop=True)
    )



def add_signals(df):
    df = df.copy()
    c = df["close"]

    fast = ta.trend.ema_indicator(c, window=9)
    slow = ta.trend.ema_indicator(c, window=21)
    rsi = ta.momentum.rsi(c, window=14)
    macd = ta.trend.MACD(c)

    df["atr"] = ta.volatility.average_true_range(
        df["high"], df["low"], c, window=14
    )

    buy = (
        (fast > slow)
        & (fast.shift(1) <= slow.shift(1))
        & (rsi > 50)
        & (macd.macd() > macd.macd_signal())
    )

    sell = (
        ((fast < slow) & (fast.shift(1) >= slow.shift(1)))
        | (rsi < 40)
    )

    # Preserve the original rule priority: SELL overrides BUY.
    event = np.zeros(len(df), dtype=int)
    event[buy.to_numpy()] = 1
    event[sell.to_numpy()] = -1

    df["signal_event"] = event

    # Retain this column for diagnostics only.
    df["position"] = (
        pd.Series(event, index=df.index)
        .replace(0, np.nan)
        .ffill()
        .fillna(0)
        .astype(int)
    )

    return df




def run_region(df, s, e, cost_pips, region):
    op = df["open"].to_numpy()
    cl = df["close"].to_numpy()
    at = df["atr"].to_numpy()
    events = df["signal_event"].to_numpy()
    dt = df["datetime"].to_numpy()

    trades = []
    cur = None
    direction = 0  # Every region starts flat.

    def finish(t, exit_i, px):
        gross = t["dir"] * (px - t["entry_px"]) / PIP
        net = gross - cost_pips
        risk = ATR_RISK_MULT * t["atr"]

        trades.append({
            "region": region,
            "direction": "BUY" if t["dir"] > 0 else "SELL",
            "entry_time": dt[t["entry_i"]],
            "exit_time": dt[exit_i],
            "entry_px": t["entry_px"],
            "exit_px": px,
            "gross_pips": gross,
            "net_pips": net,
            "atr_r": net * PIP / risk if risk > 0 else np.nan,
            "bars_held": exit_i - t["entry_i"],
        })

    # A signal at candle i is acted on at candle i+1's open.
    for i in range(s, e - 1):
        new_direction = int(events[i])

        if new_direction == 0 or new_direction == direction:
            continue

        execution_i = i + 1
        execution_price = op[execution_i]

        if cur is not None:
            finish(cur, execution_i, execution_price)

        cur = {
            "dir": new_direction,
            "entry_i": execution_i,
            "entry_px": execution_price,
            "atr": at[i],
        }
        direction = new_direction

    # Close any remaining position at the region's final close.
    if cur is not None:
        finish(cur, e - 1, cl[e - 1])

    return pd.DataFrame(trades)



def stats(t, df, s, e):
    base = {
        "trades": 0,
        "win_rate": 0.0,
        "expectancy_pips": 0.0,
        "profit_factor": 0.0,
        "total_pips": 0.0,
        "max_dd_pips": 0.0,
        "longest_loss_streak": 0,
        "expectancy_atr_r": 0.0,
    }

    base["buy_hold_pips"] = (
        df["close"].iloc[e - 1] - df["close"].iloc[s]
    ) / PIP

    if t.empty:
        return base

    x = t["net_pips"].to_numpy()
    gp = x[x > 0].sum()
    gl = -x[x < 0].sum()
    eq = np.cumsum(x)

    streak = best = 0
    for v in x:
        streak = streak + 1 if v < 0 else 0
        best = max(best, streak)

    base.update({
        "trades": len(x),
        "win_rate": float((x > 0).mean()),
        "expectancy_pips": float(x.mean()),
        "profit_factor": float(gp / gl) if gl > 0 else float("inf"),
        "total_pips": float(x.sum()),
        "max_dd_pips": float(
            (eq - np.maximum.accumulate(np.r_[0.0, eq])[1:]).min()
        ),
        "longest_loss_streak": best,
        "expectancy_atr_r": float(t["atr_r"].mean()),
    })
    return base


def main():
    if len(sys.argv) < 2:
        print(
            "Usage: python baseline_ema.py history.csv [cost_pips]"
        )
        sys.exit(1)

    cost_main = float(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_COST

    df = add_signals(load(sys.argv[1]))
    n = len(df)

    train_end = int(n * TRAIN_FRAC)
    valid_end = train_end + int(n * VALID_FRAC)

    regions = {
        "TRAIN": (0, train_end),
        "VALID": (train_end, valid_end),
        "OOS": (valid_end, n),
    }

    print(
        f"bars={n:,} train_end={train_end:,} "
        f"valid_end={valid_end:,}"
    )

    rows, logs = [], []

    for name, (s, e) in regions.items():
        for cp in sorted(set(COSTS) | {cost_main}):
            t = run_region(df, s, e, cp, name)
            rows.append({
                "region": name,
                "cost_pips": cp,
                **stats(t, df, s, e),
            })

            if cp == cost_main:
                logs.append(t)

    out = pd.DataFrame(rows)
    out.to_csv("ml/baseline_summary.csv", index=False)
    pd.concat(logs, ignore_index=True).to_csv(
        "ml/baseline_trades.csv", index=False
    )

    with pd.option_context(
        "display.width", 250,
        "display.float_format", "{:.3f}".format,
    ):
        print("\nExpectancy (net pips per trade) by round-trip cost:")
        print(
            out.pivot_table(
                index="region",
                columns="cost_pips",
                values="expectancy_pips",
            ).reindex(["TRAIN", "VALID", "OOS"])
        )

        print(f"\nAt {cost_main} pips round-trip:")
        print(
            out[out.cost_pips == cost_main]
            .set_index("region")
            .loc[
                ["TRAIN", "VALID", "OOS"],
                [
                    "trades", "win_rate", "expectancy_pips",
                    "profit_factor", "total_pips", "max_dd_pips",
                    "expectancy_atr_r", "buy_hold_pips",
                ],
            ]
        )

    print("\nSaved: ml/baseline_summary.csv, ml/baseline_trades.csv")


if __name__ == "__main__":
    main()