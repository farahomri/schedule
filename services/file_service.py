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