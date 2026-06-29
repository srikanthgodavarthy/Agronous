"""
Single-user auth stub — no login, no Supabase Auth.

All auth calls return a fixed resident user. The SINGLE_USER_ID constant
is stored as a UUID so it populates user_id columns in every table exactly
as before. The value is stable across restarts (hardcoded), so existing DB
rows always match.

To migrate to multi-user later: replace this file with the original
supabase_auth.py. No other files need to change.

Note: dropping Supabase Auth does NOT drop the Supabase *client* -- Storage
(observations bucket) still goes through it, just with a plain anon-key
client rather than an authenticated session. get_supabase_client() below is
that client, used only by pages/7_Observations.py for photo uploads.
"""
from __future__ import annotations

import os
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


_supabase_client = None


def _get_supabase_credentials() -> tuple[str, str]:
    """
    Resolve SUPABASE_URL / SUPABASE_ANON_KEY the same way db.base resolves
    DATABASE_URL: prefer env vars, fall back to st.secrets when running
    inside Streamlit. Raises RuntimeError with a clear message if neither
    source has them, so a misconfigured environment fails with an
    actionable error rather than a confusing attribute error deep in the
    supabase client.
    """
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_ANON_KEY")
    if url and key:
        return url, key
    try:
        import streamlit as st  # local import: keep this module importable w/o streamlit

        url = url or st.secrets.get("SUPABASE_URL")
        key = key or st.secrets.get("SUPABASE_ANON_KEY")
    except Exception:
        pass
    if not url or not key:
        raise RuntimeError(
            "SUPABASE_URL / SUPABASE_ANON_KEY not found in environment or st.secrets. "
            "Set them to enable Storage uploads (see env.example)."
        )
    return url, key


def get_supabase_client():
    """
    Plain (unauthenticated) Supabase client for Storage access in
    single-user mode -- there's no user session to attach since
    Supabase Auth is disabled, but the anon key is sufficient for
    Storage operations on a bucket configured with an appropriate
    policy (see README: Storage -> New Bucket 'observations').

    Lazily constructed and cached so importing this module, or calling
    get_current_user()/require_login(), never requires Supabase
    credentials to be present.
    """
    global _supabase_client
    if _supabase_client is None:
        from supabase import create_client

        url, key = _get_supabase_credentials()
        _supabase_client = create_client(url, key)
    return _supabase_client
