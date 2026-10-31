# config/settings.py

"""
ForexNezoraBot
Application Settings

Contains project paths and directory initialization.
"""

from pathlib import Path
import os

# ---------------------------------------------------
# Project Root
# ---------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent.parent

# ---------------------------------------------------
# Directories
# ---------------------------------------------------

AUTH_DIR = BASE_DIR / "auth"
CONFIG_DIR = BASE_DIR / "config"
LOG_DIR = BASE_DIR / "logs"
DATA_DIR = BASE_DIR / "data"

MODELS_DIR = BASE_DIR / "models"
ML_DIR = BASE_DIR / "ml"

# ---------------------------------------------------
# Authentication
# ---------------------------------------------------

USERS_FILE = AUTH_DIR / "users.json"

# FIX: added so the passcode flow can auto-promote a specific Telegram
# account to the "owner" role on first successful verification. Set this
# in your .env to your own numeric Telegram ID.
OWNER_TELEGRAM_ID = int(os.getenv("OWNER_TELEGRAM_ID", "0") or 0)

# ---------------------------------------------------
# Logs
# ---------------------------------------------------

AUTH_LOG_FILE = LOG_DIR / "auth.log"
SECURITY_LOG_FILE = LOG_DIR / "security.log"

# ---------------------------------------------------
# ML Model Artifacts
# ---------------------------------------------------

MODEL_PATH = MODELS_DIR / "model.pkl"
SCALER_PATH = MODELS_DIR / "scaler.pkl"
FEATURES_PATH = MODELS_DIR / "features.pkl"
HISTORICAL_DATA_PATH = ML_DIR / "historical_data.csv"

# ---------------------------------------------------
# Automatically Create Directories
# ---------------------------------------------------

AUTH_DIR.mkdir(exist_ok=True)
CONFIG_DIR.mkdir(exist_ok=True)
LOG_DIR.mkdir(exist_ok=True)
DATA_DIR.mkdir(exist_ok=True)
MODELS_DIR.mkdir(exist_ok=True)
ML_DIR.mkdir(exist_ok=True)

# ---------------------------------------------------
# Automatically Create Files
# ---------------------------------------------------

if not USERS_FILE.exists():
    USERS_FILE.write_text("{}")

AUTH_LOG_FILE.touch(exist_ok=True)
SECURITY_LOG_FILE.touch(exist_ok=True)


# ==========================================
#  ForexNezoraBot Account Credentials
# ==========================================

API_KEY = os.getenv("API_KEY")
ACCOUNT_ID = os.getenv("ACCOUNT_ID")

TWELVEDATA_API_KEY = os.getenv("TWELVEDATA_API_KEY")

TOKEN = os.getenv("TOKEN")
TELEGRAM_USER = os.getenv("TELEGRAM_USER")

RISK_FACTOR = float(os.getenv("RISK_FACTOR", 0.01))

# Trading safety controls. Execution is limited to positively verified demo
# accounts. Automated order submission requires an explicit environment opt-in
# and the admin must also arm it from the Telegram control panel.
DEMO_ONLY = True  # Live accounts remain blocked in this release.
AUTO_TRADING_ALLOWED = (
    DEMO_ONLY
    and os.getenv("AUTO_TRADING_ALLOWED", "false").strip().lower()
    in {"1", "true", "yes", "on"}
)
MIN_ML_CONFIDENCE = float(os.getenv("MIN_ML_CONFIDENCE", "65"))
MAX_DAILY_DRAWDOWN = float(os.getenv("MAX_DAILY_DRAWDOWN", "0.05"))
MAX_TOTAL_DRAWDOWN = float(os.getenv("MAX_TOTAL_DRAWDOWN", "0.10"))
MAX_OPEN_TRADES = int(os.getenv("MAX_OPEN_TRADES", "3"))
MAX_RISK_PER_TRADE_PERCENT = float(os.getenv("MAX_RISK_PER_TRADE_PERCENT", "1.0"))
BROKER_SYMBOL_SUFFIX = os.getenv("BROKER_SYMBOL_SUFFIX", "m").strip()
