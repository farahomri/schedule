import streamlit as st

# ✅ NO IMPORTS FROM services.persistence_service HERE!

class SessionManager:
    """Manage session state"""
    
    @staticmethod
    def initialize():
        """Initialize session state"""
        if 'initialized' not in st.session_state:
            st.session_state.initialized = True
            st.session_state.logged_in = False
            st.session_state.username = None
            
            # Auto-load schedule if exists
            SessionManager._auto_load_schedule()
    
    @staticmethod
    def _auto_load_schedule():
        """Auto-load schedule on startup"""
        # ✅ LAZY IMPORT - Only import when this method is called
        from services.persistence_service import PersistenceService
        
        if SessionManager.get('initial_schedule_df') is None:
            schedule_df, unscheduled_df, working_technicians = PersistenceService.load_schedule()
            
            if schedule_df is not None:
                SessionManager.set('initial_schedule_df', schedule_df)
                SessionManager.set('_schedule_auto_loaded', True)
            
            if unscheduled_df is not None:
                SessionManager.set('unscheduled_orders_df', unscheduled_df)
            
            if working_technicians is not None:
                SessionManager.set('working_technicians', working_technicians)
    
    @staticmethod
    def get(key: str, default=None):
        """Get value from session state"""
        return st.session_state.get(key, default)
    
    @staticmethod
    def set(key: str, value):
        """Set value in session state"""
        st.session_state[key] = value
    
    @staticmethod
    def is_logged_in() -> bool:
        """Check if user is logged in"""
        return st.session_state.get('logged_in', False)
    
    @staticmethod
    def clear_schedule():
        """Clear schedule from session"""
        # ✅ LAZY IMPORT - Only import when this method is called
        from services.persistence_service import PersistenceService
        
        SessionManager.set('initial_schedule_df', None)
        SessionManager.set('unscheduled_orders_df', None)
        SessionManager.set('working_technicians', None)
        SessionManager.set('merged_orders', None)
        SessionManager.set('_initial_schedule_processed', False)
        
        PersistenceService.clear_schedule()