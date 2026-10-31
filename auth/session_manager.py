# auth/session_manager.py

from datetime import datetime, timedelta


class SessionManager:

    def __init__(self, timeout=1800):
        self.timeout = timeout
        self.sessions = {}

    def create(self, user_id):

        self.sessions[user_id] = datetime.utcnow()

    def refresh(self, user_id):

        if user_id in self.sessions:
            self.sessions[user_id] = datetime.utcnow()

    def remove(self, user_id):

        self.sessions.pop(user_id, None)

    def active(self, user_id):

        if user_id not in self.sessions:
            return False

        last = self.sessions[user_id]

        if datetime.utcnow() - last > timedelta(seconds=self.timeout):
            self.remove(user_id)
            return False

        return True

    def clear(self):
        self.sessions.clear()