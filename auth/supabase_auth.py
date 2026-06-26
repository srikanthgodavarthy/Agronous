"""
Supabase Auth integration.

Wraps the supabase-py client's `auth` namespace for sign up, sign in, sign
out, and session retrieval. Session tokens are cached in Streamlit's
`st.session_state` (server-side, per-browser-session memory) -- not in
browser local storage -- so a page refresh within the same Streamlit session
keeps the user logged in, while closing the tab clears it (acceptable for
v1; a "remember me" via st.query_params + refresh-token persistence can be
added later without touching the rest of the app).
"""
from __future__ import annotations

import os
from dataclasses import dataclass

import streamlit as st
from supabase import Client, create_client


@dataclass
class AuthUser:
    id: str
    email: str


def _get_secret(key: str) -> str:
    val = os.environ.get(key)
    if val:
        return val
    try:
        return st.secrets[key]
    except Exception as exc:
        raise RuntimeError(f"Missing required secret: {key}") from exc


@st.cache_resource(show_spinner=False)
def get_supabase_client() -> Client:
    url = _get_secret("SUPABASE_URL")
    key = _get_secret("SUPABASE_ANON_KEY")
    return create_client(url, key)


def sign_up(email: str, password: str) -> tuple[bool, str]:
    """Returns (success, message)."""
    try:
        client = get_supabase_client()
        client.auth.sign_up({"email": email, "password": password})
        return True, "Account created. Please check your email to confirm, then sign in."
    except Exception as exc:
        return False, _friendly_error(exc)


def sign_in(email: str, password: str) -> tuple[bool, str]:
    try:
        client = get_supabase_client()
        response = client.auth.sign_in_with_password({"email": email, "password": password})
        if response.user is None or response.session is None:
            return False, "Invalid email or password."
        st.session_state["auth_user"] = AuthUser(id=response.user.id, email=response.user.email or email)
        st.session_state["auth_access_token"] = response.session.access_token
        st.session_state["auth_refresh_token"] = response.session.refresh_token
        return True, "Signed in successfully."
    except Exception as exc:
        return False, _friendly_error(exc)


def sign_out() -> None:
    try:
        client = get_supabase_client()
        client.auth.sign_out()
    except Exception:
        pass
    for key in ("auth_user", "auth_access_token", "auth_refresh_token", "active_season_id", "active_farm_id"):
        st.session_state.pop(key, None)


def get_current_user() -> AuthUser | None:
    return st.session_state.get("auth_user")


def require_login() -> AuthUser:
    """Use at the top of any page that requires authentication."""
    user = get_current_user()
    if user is None:
        st.warning("Please sign in to continue.")
        st.stop()
    return user


def _friendly_error(exc: Exception) -> str:
    msg = str(exc)
    if "Invalid login credentials" in msg:
        return "Invalid email or password."
    if "User already registered" in msg:
        return "An account with this email already exists. Please sign in instead."
    if "Password should be at least" in msg:
        return "Password is too short. Please use at least 6 characters."
    return f"Something went wrong: {msg}"
