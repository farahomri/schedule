import streamlit as st

class SessionManager:
    """Centralized session state management"""
    
    @staticmethod
    def initialize():
        """Initialize all session state variables"""
        defaults = {
            'logged_in': False,
            'username': None,
            'initial_schedule_df': None,
            'updated_schedule_df': None,
            'unscheduled_orders_df': None,
            'merged_orders': None,
            'working_technicians': None,
            'technicians_data': None,
            'show_technicians': False,
            'show_reclamations': False,
            'show_orders': False,
            '_initial_schedule_processed': False
        }
        
        for key, value in defaults.items():
            if key not in st.session_state:
                st.session_state[key] = value
    
    @staticmethod
    def get(key, default=None):
        """Get session state value"""
        return st.session_state.get(key, default)
    
    @staticmethod
    def set(key, value):
        """Set session state value"""
        st.session_state[key] = value
    
    @staticmethod
    def clear_schedule():
        """Clear schedule-related session state"""
        keys_to_clear = [
            'initial_schedule_df',
            'updated_schedule_df',
            'unscheduled_orders_df',
            'merged_orders',
            '_initial_schedule_processed'
        ]
        for key in keys_to_clear:
            st.session_state[key] = None
    
    @staticmethod
    def is_logged_in():
        """Check if user is logged in"""
        return st.session_state.get('logged_in', False)