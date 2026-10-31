"""Normalize TwelveData/user symbols to the configured broker symbol suffix."""
from config.settings import BROKER_SYMBOL_SUFFIX


def to_broker_symbol(symbol):
    value = str(symbol).strip().replace("/", "").replace(" ", "")
    if not value:
        raise ValueError("Symbol cannot be empty")
    base = value.upper()
    suffix = str(BROKER_SYMBOL_SUFFIX).strip()
    if suffix and base.endswith(suffix.upper()):
        return base[:-len(suffix)] + suffix
    return base + suffix
