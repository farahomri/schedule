import pandas as pd
import streamlit as st

class Validators:
    """Input validation utilities"""
    
    @staticmethod
    def validate_file_upload(file, expected_extensions: list) -> bool:
        """Validate uploaded file"""
        if file is None:
            return False
        
        file_ext = file.name.split('.')[-1].lower()
        if file_ext not in expected_extensions:
            st.error(f"Please upload a file with extension: {', '.join(expected_extensions)}")
            return False
        return True
    
    @staticmethod
    def validate_dataframe_columns(df: pd.DataFrame, required_columns: list, context: str = "") -> bool:
        """Validate dataframe has required columns"""
        missing = set(required_columns) - set(df.columns)
        if missing:
            st.error(f"{context} Missing columns: {', '.join(missing)}")
            return False
        return True
    
    @staticmethod
    def validate_numeric(value, min_val=None, max_val=None, field_name="Value") -> tuple:
        """Validate numeric input"""
        try:
            num_value = float(value)
            if min_val is not None and num_value < min_val:
                return False, f"{field_name} must be >= {min_val}"
            if max_val is not None and num_value > max_val:
                return False, f"{field_name} must be <= {max_val}"
            return True, num_value
        except (ValueError, TypeError):
            return False, f"{field_name} must be a number"
    
    @staticmethod
    def validate_text(value, min_length=1, max_length=None, field_name="Field") -> tuple:
        """Validate text input"""
        if not value or len(value.strip()) < min_length:
            return False, f"{field_name} is required"
        if max_length and len(value) > max_length:
            return False, f"{field_name} too long (max {max_length} chars)"
        return True, value.strip()