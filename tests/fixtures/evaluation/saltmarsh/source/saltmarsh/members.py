"""A member, and the one-time code they sign in with (REQ-0001)."""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta

CODE_MINUTES = 10


@dataclass
class Code:
    digits: str
    expires: datetime
    used: bool = False


def new_code(now: datetime) -> Code:
    return Code(digits=f"{secrets.randbelow(10**6):06d}", expires=now + timedelta(minutes=CODE_MINUTES))


def accepts(code: Code, digits: str, now: datetime) -> bool:
    ok = not code.used and now <= code.expires and secrets.compare_digest(code.digits, digits)
    if ok:
        code.used = True
    return ok
