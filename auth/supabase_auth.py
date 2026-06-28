"""
Single-user auth stub — no login, no Supabase Auth.

All auth calls return a fixed resident user. The SINGLE_USER_ID constant
is stored as a UUID so it populates user_id columns in every table exactly
as before. The value is stable across restarts (hardcoded), so existing DB
rows always match.

To migrate to multi-user later: replace this file with the original
supabase_auth.py. No other files need to change.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass

# Fixed UUID for the single resident user.
# Must be a valid UUID4 so it satisfies the DB column type.
SINGLE_USER_ID = uuid.UUID("00000000-0000-4000-a000-000000000001")


@dataclass
class AuthUser:
    id: str
    email: str


_RESIDENT_USER = AuthUser(
    id=str(SINGLE_USER_ID),
    email="farmer@local",
)


def get_current_user() -> AuthUser:
    """Always returns the resident single user."""
    return _RESIDENT_USER


def require_login() -> AuthUser:
    """No-op gate — always passes."""
    return _RESIDENT_USER


# Keep sign_in / sign_out present so any accidental import doesn't crash.
def sign_in(email: str, password: str) -> tuple[bool, str]:
    return True, "Single-user mode — no login required."


def sign_out() -> None:
    pass


def sign_up(email: str, password: str) -> tuple[bool, str]:
    return False, "Single-user mode — account creation is disabled."
