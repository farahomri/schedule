import streamlit as st
from config import Config
from utils.session_manager import SessionManager

class AuthService:
    """Handle authentication"""
    
    @staticmethod
    def login(username: str, password: str) -> bool:
        """Authenticate user"""
        if username in Config.CREDENTIALS and Config.CREDENTIALS[username] == password:
            SessionManager.set('logged_in', True)
            SessionManager.set('username', username)
            return True
        return False
    
    @staticmethod
    def logout():
        """Logout user"""
        SessionManager.set('logged_in', False)
        SessionManager.set('username', None)
    
    @staticmethod
    def require_login():
        """Show login page if not authenticated"""
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
                
                with st.expander("ℹ️ Default Credentials"):
                    st.info("""
                    **Admin:** admin / draex2024
                    **Manager:** manager / manager123
                    **User:** user / user123
                    """)
            
            return False
        return True