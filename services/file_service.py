import os
import pandas as pd
from config import Config

class FileService:
    """Handle file operations"""
    
    @staticmethod
    def ensure_data_directory():
        """Create data directory if needed"""
        os.makedirs(Config.DATA_DIR, exist_ok=True)
    
    @staticmethod
    def create_empty_csv(file_path: str, columns: list):
        """Create empty CSV with headers"""
        if not os.path.exists(file_path):
            pd.DataFrame(columns=columns).to_csv(file_path, index=False)
    
    @staticmethod
    def create_empty_excel(file_path: str, columns: list):
        """Create empty Excel with headers"""
        if not os.path.exists(file_path):
            pd.DataFrame(columns=columns).to_excel(file_path, index=False)
    
    @staticmethod
    def save_schedule(schedule_df):
        """Save schedule to persistent file"""
        try:
            from config import Config
            schedule_df.to_csv(Config.SCHEDULE_FILE, index=False)
            return True
        except Exception as e:
            print(f"Error saving schedule: {e}")
            return False
    
    @staticmethod
    def load_schedule():
        """Load schedule from persistent file"""
        try:
            from config import Config
            import pandas as pd
            
            if os.path.exists(Config.SCHEDULE_FILE):
                df = pd.read_csv(Config.SCHEDULE_FILE)
                
                # Convert datetime columns back from strings
                datetime_cols = ['FirstStartTime', 'EndTime']
                for col in datetime_cols:
                    if col in df.columns:
                        df[col] = pd.to_datetime(df[col], errors='coerce')
                
                # Ensure numeric columns are correct type
                if 'TotalTimeSpent' in df.columns:
                    df['TotalTimeSpent'] = pd.to_numeric(df['TotalTimeSpent'], errors='coerce').fillna(0.0)
                if 'RemainingRoutingTime' in df.columns:
                    df['RemainingRoutingTime'] = pd.to_numeric(df['RemainingRoutingTime'], errors='coerce')
                if 'Routing Time (min)' in df.columns:
                    df['Routing Time (min)'] = pd.to_numeric(df['Routing Time (min)'], errors='coerce')
                if 'SequenceNumber' in df.columns:
                    df['SequenceNumber'] = pd.to_numeric(df['SequenceNumber'], errors='coerce').fillna(0).astype(int)
                
                # Ensure WorkSessions is string
                if 'WorkSessions' in df.columns:
                    df['WorkSessions'] = df['WorkSessions'].fillna('[]').astype(str)
                
                print(f"✅ Loaded schedule: {len(df)} orders")
                return df
            else:
                print("ℹ️ No saved schedule found")
                return None
        except Exception as e:
            print(f"❌ Error loading schedule: {e}")
            return None
    
    @staticmethod
    def schedule_exists():
        """Check if a saved schedule exists"""
        from config import Config
        return os.path.exists(Config.SCHEDULE_FILE)
    
    @staticmethod
    def delete_schedule():
        """Delete the saved schedule file"""
        try:
            from config import Config
            if os.path.exists(Config.SCHEDULE_FILE):
                os.remove(Config.SCHEDULE_FILE)
                return True
            return False
        except Exception as e:
            print(f"Error deleting schedule: {e}")
            return False
    
    @staticmethod
    def initialize_all_files():
        """Initialize all required data files"""
        FileService.ensure_data_directory()
        
        # Technicians file
        FileService.create_empty_csv(
            Config.TECHNICIANS_FILE,
            ['Matricule', 'Nom et prénom', 'Niveau 4', 'Niveau 3', 'Niveau 2', 'Niveau 1', 'Classification', 'Expertise Class']
        )
        
        # Products file
        FileService.create_empty_csv(
            Config.PRODUCTS_FILE,
            ['SAP', 'Material Description', 'routing time', 'Class', 'Class Code']
        )
        
        # Reclamations file
        FileService.create_empty_excel(
            Config.RECLAMATIONS_FILE,
            ['Date', 'Ordre', 'SAP', 'Description', 'Qty', 'Reclamation', 'Remarque', 'Technicien', 'Decision', 'QS']
        )