# auth/models.py

from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional


@dataclass(slots=True)
class User:
    telegram_id: int

    username: Optional[str]
    first_name: str
    last_name: Optional[str] = None

    verified: bool = False
    role: str = "user"
    status: str = "active"

    attempts: int = 0
    locked_until: Optional[str] = None

    joined: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    last_login: Optional[str] = None
    last_activity: Optional[str] = None

    invite_code: Optional[str] = None

    notes: str = ""

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict):
        return cls(**data)