import streamlit as st

from services.auth_service import AuthService
from pages.schedule_page import SchedulePage
from pages.initial_scheduling_page import InitialSchedulingPage
from pages.technicians_page import TechniciansPage
from pages.orders_page import OrdersPage

st.set_page_config(
    page_title="Draexlmaier Scheduling System",
    page_icon="📅",
    layout="wide",
    initial_sidebar_state="expanded",
)


def main():
    if not AuthService.require_login():
        return

    st.sidebar.title("🗂️ Draexlmaier")
    st.sidebar.markdown(f"**👤** {st.session_state.get('username', '')}")
    st.sidebar.markdown(f"**🔑** {st.session_state.get('role', '').capitalize()}")
    st.sidebar.markdown("---")

    pages = {
        "📅 Schedule Management": SchedulePage.render,
        "📊 Initial Scheduling": InitialSchedulingPage.render,
        "👷 Manage Technicians": TechniciansPage.render,
        "📦 Manage Orders": OrdersPage.render,
    }

    choice = st.sidebar.radio("📍 Navigate to", list(pages.keys()))

    st.sidebar.markdown("---")
    if st.sidebar.button("🚪 Logout", use_container_width=True):
        AuthService.logout()
        st.rerun()

    pages[choice]()


if __name__ == "__main__":
    main()
