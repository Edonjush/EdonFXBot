# auth/auth_manager.py

"""
ForexNezoraBot Authentication Manager

Responsible for:
- Loading and saving users
- User registration
- Verification
- Account lockout
- Login tracking
- User lookup
"""

from __future__ import annotations

import json
import threading
from datetime import datetime

from auth.models import User
from config.settings import USERS_FILE, OWNER_TELEGRAM_ID
from config.security import (
    DEFAULT_ROLE,
    DEFAULT_STATUS,
    MAX_LOGIN_ATTEMPTS,
    LOCK_DURATION,
)


class AuthManager:

    def __init__(self):
        self._lock = threading.RLock()
        self._users: dict[int, User] = {}
        self._load()

    def _load(self):
        with self._lock:
            if not USERS_FILE.exists():
                USERS_FILE.write_text("{}")
            try:
                with open(USERS_FILE, "r", encoding="utf-8") as f:
                    raw = json.load(f)
            except Exception:
                raw = {}
            self._users = {
                int(uid): User.from_dict(data)
                for uid, data in raw.items()
            }

    def _save(self):
        with self._lock:
            data = {
                str(uid): user.to_dict()
                for uid, user in self._users.items()
            }
            tmp = USERS_FILE.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
            tmp.replace(USERS_FILE)

    # ==================================================
    # User Lookup
    # ==================================================

    def exists(self, telegram_id: int) -> bool:
        return telegram_id in self._users

    def get_user(self, telegram_id: int):
        return self._users.get(telegram_id)

    def all_users(self):
        return list(self._users.values())

    # ==================================================
    # Registration
    # ==================================================

    def register(self, telegram_user, verified: bool = True):
        now = datetime.utcnow().isoformat()

        user = User(
            telegram_id=telegram_user.id,
            username=telegram_user.username,
            first_name=telegram_user.first_name,
            last_name=telegram_user.last_name,
            verified=verified,
            role=DEFAULT_ROLE,
            status=DEFAULT_STATUS,
            last_login=now if verified else None,
            last_activity=now
        )

        self._users[user.telegram_id] = user
        self._save()
        return user

    # ==================================================
    # Verification
    # ==================================================

    def is_verified(self, telegram_id):
        user = self.get_user(telegram_id)
        if not user:
            return False
        return user.verified

    def verify_user(self, telegram_id):
        user = self.get_user(telegram_id)
        if not user:
            return None

        now = datetime.utcnow().isoformat()
        user.verified = True
        user.attempts = 0
        user.locked_until = None
        user.last_login = now
        user.last_activity = now

        self._save()
        return user

    # ==================================================
    # Activity
    # ==================================================

    def update_activity(self, telegram_id):
        user = self.get_user(telegram_id)
        if user:
            user.last_activity = datetime.utcnow().isoformat()
            self._save()

    def update_login(self, telegram_id):
        user = self.get_user(telegram_id)
        if user:
            now = datetime.utcnow().isoformat()
            user.last_login = now
            user.last_activity = now
            self._save()

    # ==================================================
    # Lockout
    # ==================================================

    def record_failed_attempt(self, telegram_id):
        user = self.get_user(telegram_id)
        if not user:
            return

        user.attempts += 1

        if user.attempts >= MAX_LOGIN_ATTEMPTS:
            unlock = datetime.utcnow() + LOCK_DURATION
            user.locked_until = unlock.isoformat()

        self._save()

    def reset_attempts(self, telegram_id):
        user = self.get_user(telegram_id)
        if not user:
            return
        user.attempts = 0
        user.locked_until = None
        self._save()

    def is_locked(self, telegram_id):
        user = self.get_user(telegram_id)
        if not user:
            return False
        if not user.locked_until:
            return False

        unlock = datetime.fromisoformat(user.locked_until)

        if datetime.utcnow() >= unlock:
            user.locked_until = None
            user.attempts = 0
            self._save()
            return False

        return True

    # ==================================================
    # Roles
    # ==================================================

    def set_role(self, telegram_id, role):
        user = self.get_user(telegram_id)
        if user:
            user.role = role
            self._save()

    def is_admin(self, telegram_id):
        # FIX: previously this only checked the persisted role in
        # users.json, which was only ever set to "owner" at the exact
        # moment a user typed the correct passcode. Anyone who was already
        # verified before OWNER_TELEGRAM_ID / this promotion logic existed
        # (or who authenticated through some other path) stayed stuck on
        # the default "user" role forever, even if their Telegram ID
        # matched OWNER_TELEGRAM_ID in .env -- which is exactly what
        # happened. OWNER_TELEGRAM_ID is now treated as always-admin,
        # independent of whatever role happens to be saved on disk.
        if OWNER_TELEGRAM_ID and telegram_id == OWNER_TELEGRAM_ID:
            return True

        user = self.get_user(telegram_id)
        return bool(user and user.role in ("admin", "owner"))

    def is_owner(self, telegram_id):
        if OWNER_TELEGRAM_ID and telegram_id == OWNER_TELEGRAM_ID:
            return True

        user = self.get_user(telegram_id)
        return bool(user and user.role == "owner")

    # ==================================================
    # Remove User
    # ==================================================

    def remove_user(self, telegram_id):
        if telegram_id in self._users:
            del self._users[telegram_id]
            self._save()
