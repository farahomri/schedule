import streamlit as st
from typing import Any, Optional

class SessionManager:
    """Manage Streamlit session state"""
    
    @staticmethod
    def initialize():
        """Initialize session state with default values"""
        defaults = {
            'authenticated': False,
            'username': None,
            'initial_schedule_df': None,
            'unscheduled_orders_df': None,
            'merged_orders': None,
            'working_technicians': None,
            '_initial_schedule_processed': False,
        }
        
        for key, value in defaults.items():
            if key not in st.session_state:
                st.session_state[key] = value
        
        # ✅ AUTO-LOAD SCHEDULE ON STARTUP
        SessionManager._auto_load_schedule()
    
    @staticmethod
    def _auto_load_schedule():
        """Automatically load schedule if it exists and session is empty"""
        from services.persistence_service import PersistenceService
        
        # Only load if session doesn't have a schedule yet
        if st.session_state.get('initial_schedule_df') is None:
            if PersistenceService.schedule_exists():
                schedule_df, unscheduled_df = PersistenceService.load_schedule()
                
                if schedule_df is not None:
                    st.session_state['initial_schedule_df'] = schedule_df
                    st.session_state['unscheduled_orders_df'] = unscheduled_df if unscheduled_df is not None else pd.DataFrame()
                    st.session_state['_schedule_auto_loaded'] = True
                    print("✅ Schedule auto-loaded from file")
    
    @staticmethod
    def get(key: str, default: Any = None) -> Any:
        """Get value from session state"""
        return st.session_state.get(key, default)
    
    @staticmethod
    def set(key: str, value: Any):
        """Set value in session state"""
        st.session_state[key] = value
        
        # ✅ AUTO-SAVE SCHEDULE WHEN IT CHANGES
        if key == 'initial_schedule_df':
            SessionManager._auto_save_schedule()
    
    @staticmethod
    def _auto_save_schedule():
        """Automatically save schedule when it changes"""
        from services.persistence_service import PersistenceService
        
        schedule_df = st.session_state.get('initial_schedule_df')
        unscheduled_df = st.session_state.get('unscheduled_orders_df')
        
        if schedule_df is not None:
            PersistenceService.save_schedule(schedule_df, unscheduled_df)
    
    @staticmethod
    def clear_schedule():
        """Clear schedule from session and disk"""
        from services.persistence_service import PersistenceService
        
        st.session_state['initial_schedule_df'] = None
        st.session_state['unscheduled_orders_df'] = None
        st.session_state['merged_orders'] = None
        st.session_state['working_technicians'] = None
        st.session_state['_initial_schedule_processed'] = False
        
        # Delete files
        PersistenceService.clear_schedule()
    @staticmethod
    def is_logged_in():
        """Check if user is logged in"""
        return st.session_state.get('logged_in', False)