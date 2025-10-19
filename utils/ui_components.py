import streamlit as st
from datetime import datetime
from config import Config

class UIComponents:
    """Reusable UI components"""
    
    @staticmethod
    def status_badge(status: str) -> str:
        """Return an HTML badge with appropriate color"""
        color = Config.STATUS_COLORS.get(status, "#d3d3d3")
        return f'<span style="background:{color};color:#222;padding:0.2em 0.6em;border-radius:0.6em;font-weight:700;">{status}</span>'
    
    @staticmethod
    def page_header(title: str, subtitle: str = None):
        """Display a styled page header"""
        st.markdown(f"""
            <h1 style='text-align: center; color: #1f77b4;'>{title}</h1>
            {f"<p style='text-align: center; color: #666;'>{subtitle}</p>" if subtitle else ""}
        """, unsafe_allow_html=True)
    
    @staticmethod
    def metric_cards(metrics: dict):
        """Display a row of metric cards"""
        cols = st.columns(len(metrics))
        for col, (label, value) in zip(cols, metrics.items()):
            with col:
                st.metric(label, value)
    
    @staticmethod
    def info_message(message: str, type: str = "info"):
        """Display styled message"""
        icons = {"info": "ℹ️", "success": "✅", "warning": "⚠️", "error": "❌"}
        colors = {"info": "#3498db", "success": "#2ecc71", "warning": "#f39c12", "error": "#e74c3c"}
        icon = icons.get(type, "ℹ️")
        color = colors.get(type, "#3498db")
        
        st.markdown(f"""
            <div style='background:{color}15;padding:1em;border-radius:0.5em;border-left:4px solid {color}'>
                {icon} {message}
            </div>
        """, unsafe_allow_html=True)
    
    @staticmethod
    def format_work_sessions(work_sessions_json: str) -> str:
        """Format work sessions for display"""
        import json
        if not work_sessions_json or work_sessions_json == '[]':
            return "No sessions yet"
        
        sessions = json.loads(work_sessions_json)
        formatted = []
        for i, session in enumerate(sessions, 1):
            start = datetime.fromisoformat(session['start']).strftime('%H:%M:%S')
            stop = datetime.fromisoformat(session['stop']).strftime('%H:%M:%S') if session['stop'] else "Ongoing"
            formatted.append(f"Session {i}: {start} - {stop}")
        return "\n".join(formatted)