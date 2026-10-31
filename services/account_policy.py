"""Account-environment classification kept independent of the MetaAPI SDK."""


def is_demo_account(info, server=""):
    info = info if isinstance(info, dict) else {}
    for key in ("isDemo", "is_demo", "demo"):
        value = info.get(key)
        if isinstance(value, bool):
            return value
    server_name = str(server or info.get("server", "")).strip().lower()
    return any(marker in server_name for marker in ("demo", "trial", "practice"))
