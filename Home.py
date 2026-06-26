"""
Cultivation - Farm Cultivation Management
Main entry point: handles authentication, then routes into the multipage app.
"""
from __future__ import annotations

import streamlit as st

from auth.supabase_auth import get_current_user, sign_in, sign_out, sign_up

st.set_page_config(
    page_title="Cultivation",
    page_icon="🌱",
    layout="wide",
    initial_sidebar_state="expanded",
)


def render_login_screen() -> None:
    st.markdown(
        """
        <div style="text-align:center; padding-top: 2rem;">
            <h1>🌱 Cultivation</h1>
            <p style="color:#5b6b5d; font-size:1.05rem;">
                Know what to do today, what's due this week, and whether you're making a profit.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    _, center, _ = st.columns([1, 1.2, 1])
    with center:
        tab_login, tab_signup = st.tabs(["Sign In", "Create Account"])

        with tab_login:
            with st.form("login_form"):
                email = st.text_input("Email", key="login_email")
                password = st.text_input("Password", type="password", key="login_password")
                submitted = st.form_submit_button("Sign In", use_container_width=True, type="primary")
                if submitted:
                    if not email or not password:
                        st.error("Please enter both email and password.")
                    else:
                        with st.spinner("Signing in..."):
                            success, message = sign_in(email, password)
                        if success:
                            st.success(message)
                            st.rerun()
                        else:
                            st.error(message)

        with tab_signup:
            with st.form("signup_form"):
                email = st.text_input("Email", key="signup_email")
                password = st.text_input(
                    "Password", type="password", key="signup_password", help="At least 6 characters."
                )
                confirm = st.text_input("Confirm Password", type="password", key="signup_confirm")
                submitted = st.form_submit_button("Create Account", use_container_width=True, type="primary")
                if submitted:
                    if not email or not password:
                        st.error("Please enter both email and password.")
                    elif password != confirm:
                        st.error("Passwords do not match.")
                    else:
                        with st.spinner("Creating your account..."):
                            success, message = sign_up(email, password)
                        if success:
                            st.success(message)
                        else:
                            st.error(message)


def render_app_home() -> None:
    user = get_current_user()

    with st.sidebar:
        st.markdown(f"**Signed in as**  \n{user.email}")
        if st.button("Sign Out", use_container_width=True):
            sign_out()
            st.rerun()
        st.divider()

    from app.ui_helpers import require_active_season
    from app import dashboard_view

    ctx = require_active_season()
    dashboard_view.render(ctx)


def main() -> None:
    user = get_current_user()
    if user is None:
        render_login_screen()
    else:
        render_app_home()


if __name__ == "__main__":
    main()
