import pandas as pd
import os
from typing import Optional, Tuple
from config import Config

class PersistenceService:
    """Handle saving and loading schedule data"""
    
    @staticmethod
    def save_schedule(schedule_df: pd.DataFrame, unscheduled_df: pd.DataFrame = None, working_technicians = None) -> bool:
        """Save current schedule to CSV file"""
        try:
            # Save schedule
            if schedule_df is not None and not schedule_df.empty:
                schedule_df.to_csv(Config.SCHEDULE_FILE, index=False)
                print(f"✅ Schedule saved: {len(schedule_df)} orders")
            
            # Save unscheduled orders
            if unscheduled_df is not None:
                unscheduled_df.to_csv(Config.UNSCHEDULED_FILE, index=False)
                print(f"✅ Unscheduled saved: {len(unscheduled_df)} orders")
            
            # Save working technicians
            if working_technicians is not None:
                if isinstance(working_technicians, list):
                    working_technicians = pd.DataFrame(working_technicians)
                if isinstance(working_technicians, pd.DataFrame):
                    working_technicians.to_csv(Config.WORKING_TECHNICIANS_FILE, index=False)
                    print(f"✅ Working technicians saved: {len(working_technicians)} technicians")
            
            return True
        except Exception as e:
            print(f"❌ Error saving schedule: {e}")
            return False
    
    @staticmethod
    def load_schedule() -> Tuple[Optional[pd.DataFrame], Optional[pd.DataFrame], Optional[pd.DataFrame]]:
        """Load schedule from CSV file if it exists"""
        schedule_df = None
        unscheduled_df = None
        working_technicians = None
        
        try:
            # Load schedule
            if os.path.exists(Config.SCHEDULE_FILE):
                schedule_df = pd.read_csv(Config.SCHEDULE_FILE)
                
                # Convert date columns back to datetime
                date_columns = ['FirstStartTime', 'EndTime', 'Day/Date']
                for col in date_columns:
                    if col in schedule_df.columns:
                        schedule_df[col] = pd.to_datetime(schedule_df[col], errors='coerce')
                
                print(f"✅ Schedule loaded: {len(schedule_df)} orders")
            
            # Load unscheduled
            if os.path.exists(Config.UNSCHEDULED_FILE):
                unscheduled_df = pd.read_csv(Config.UNSCHEDULED_FILE)
                print(f"✅ Unscheduled loaded: {len(unscheduled_df)} orders")
            else:
                unscheduled_df = pd.DataFrame()
            
            # Load working technicians
            if os.path.exists(Config.WORKING_TECHNICIANS_FILE):
                working_technicians = pd.read_csv(Config.WORKING_TECHNICIANS_FILE)
                print(f"✅ Working technicians loaded: {len(working_technicians)} technicians")
            
            return schedule_df, unscheduled_df, working_technicians
        
        except Exception as e:
            print(f"❌ Error loading schedule: {e}")
            return None, None, None
    
    @staticmethod
    def clear_schedule() -> bool:
        """Delete saved schedule files"""
        try:
            if os.path.exists(Config.SCHEDULE_FILE):
                os.remove(Config.SCHEDULE_FILE)
                print("✅ Schedule file deleted")
            
            if os.path.exists(Config.UNSCHEDULED_FILE):
                os.remove(Config.UNSCHEDULED_FILE)
                print("✅ Unscheduled file deleted")
            
            if os.path.exists(Config.WORKING_TECHNICIANS_FILE):
                os.remove(Config.WORKING_TECHNICIANS_FILE)
                print("✅ Working technicians file deleted")
            
            return True
        except Exception as e:
            print(f"❌ Error clearing schedule: {e}")
            return False
    
    @staticmethod
    def schedule_exists() -> bool:
        """Check if a saved schedule exists"""
        return os.path.exists(Config.SCHEDULE_FILE)