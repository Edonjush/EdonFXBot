# config/security.py

"""
ForexNezoraBot
Security Configuration

Central location for all security settings.
"""

import os
from datetime import timedelta

# =====================================================
# Authentication
# =====================================================

BOT_PASSCODE = os.getenv("BOT_PASSCODE", "CHANGE_ME")

MAX_LOGIN_ATTEMPTS = 3

LOCK_DURATION = timedelta(minutes=5)

# =====================================================
# Session Management
# =====================================================

SESSION_TIMEOUT = timedelta(minutes=30)

REMEMBER_DEVICE = True

# =====================================================
# User Defaults
# =====================================================

DEFAULT_ROLE = "user"

DEFAULT_STATUS = "active"

OWNER_ROLE = "owner"

ADMIN_ROLE = "admin"

PREMIUM_ROLE = "premium"

# =====================================================
# Logging
# =====================================================

ENABLE_AUTH_LOG = True

ENABLE_SECURITY_LOG = True

# =====================================================
# Password Policy
# =====================================================

PASSCODE_MIN_LENGTH = 6

PASSCODE_MAX_LENGTH = 64

# =====================================================
# Future Expansion
# =====================================================

ENABLE_INVITE_CODES = False

ENABLE_SUBSCRIPTIONS = False

ENABLE_LICENSE_KEYS = False

ENABLE_WEB_LOGIN = False

# =====================================================
# Security Flags
# =====================================================

ALLOW_MULTIPLE_SESSIONS = True

AUTO_UNLOCK = True

TRACK_LAST_ACTIVITY = True

TRACK_LOGIN_HISTORY = True