# utils/parser.py

def ParseSignal(text: str):

    try:

        lines = text.strip().splitlines()

        if len(lines) < 4:
            return None

        # First line
        first = lines[0].split()

        if len(first) != 2:
            return None

        trade_type = first[0].upper()
        symbol = first[1].upper()

        if trade_type not in ["BUY", "SELL"]:
            return None

        entry = float(lines[1])
        sl = float(lines[2])
        tp = float(lines[3])

        return {
            "type": trade_type,
            "symbol": symbol,
            "entry": entry,
            "sl": sl,
            "tp": tp
        }

    except Exception:
        return None