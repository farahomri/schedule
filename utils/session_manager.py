import streamlit as st


class SessionManager:

    @staticmethod
    def get(key: str, default=None):
        return st.session_state.get(key, default)

    @staticmethod
    def set(key: str, value):
        st.session_state[key] = value

    @staticmethod
    def is_logged_in() -> bool:
        return st.session_state.get('logged_in', False)
