# EdonFXBot

Telegram trading bot with market-signal generation, risk checks, and a TickerAll execution adapter.

## Setup

1. Install Python 3.12 and create a virtual environment.
2. Install dependencies with `pip install -r requirements.txt`.
3. Copy `.env.example` to `.env` and add your Telegram, TwelveData, and TickerAll credentials. Keep `.env` private; it is ignored by Git.
4. Start the bot with `python main.py`.

## Automated trading

Automated execution is disarmed by default. `AUTO_TRADING_ALLOWED` defaults to `false`; execution also remains demo-only and checks the broker account, open positions, quote, spread, drawdown, confidence, and position size. To opt into demo automation, set `AUTO_TRADING_ALLOWED=true`, restart the bot, then an administrator can arm the schedule in `/menu`. The current scheduled watchlist is EUR/USD mapped to `EURUSDm` and checks every five minutes. An accepted order response is not confirmation of a fill; verify order status with TickerAll.

Do not store real credentials in the repository or enable live-account execution.

## Tests

Run `python -m pytest -q` from the project root.
