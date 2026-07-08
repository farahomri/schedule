import bcrypt
import streamlit as st

from db.database import get_session
from repositories.user_repository import UserRepository
from utils.session_manager import SessionManager


class AuthService:

    @staticmethod
    def login(username: str, password: str) -> bool:
        with get_session() as session:
            user = UserRepository.get_by_username(session, username)
            if not user or not user.is_active:
                return False
            stored_hash = user.password_hash
            display_name = user.username
            role = user.role

        if not bcrypt.checkpw(password.encode(), stored_hash.encode()):
            return False

        SessionManager.set('logged_in', True)
        SessionManager.set('username', display_name)
        SessionManager.set('role', role)
        return True

    @staticmethod
    def get_current_role() -> str | None:
        return SessionManager.get('role')

    @staticmethod
    def require_role(*allowed_roles: str) -> bool:
        """Return True if the current user's role is allowed. Show access denied and return False otherwise."""
        role = SessionManager.get('role')
        if role in allowed_roles:
            return True
        st.error("🚫 Access denied. You do not have permission to view this page.")
        return False

    @staticmethod
    def logout():
        for key in list(st.session_state.keys()):
            del st.session_state[key]

    @staticmethod
    def require_login():
        """Show login page if not authenticated."""
        if not SessionManager.is_logged_in():
            st.markdown("""
                <h1 style='text-align: center; color: #1f77b4;'>🔐 Draexlmaier Login</h1>
            """, unsafe_allow_html=True)

            col1, col2, col3 = st.columns([1, 2, 1])

            with col2:
                with st.form("login_form"):
                    st.markdown("### Enter your credentials")
                    username = st.text_input("👤 Username", placeholder="Enter username")
                    password = st.text_input("🔒 Password", type="password", placeholder="Enter password")

                    col_a, col_b, col_c = st.columns([1, 2, 1])
                    with col_b:
                        submit = st.form_submit_button("🚀 Login", use_container_width=True)

                    if submit:
                        if AuthService.login(username, password):
                            st.success("✅ Login successful!")
                            st.rerun()
                        else:
                            st.error("❌ Invalid username or password")

                with st.expander("ℹ️ Login Help"):
                    st.info("Contact your administrator for login credentials.")

            return False
        return True
