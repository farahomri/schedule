import os

class Config:
    """Application configuration - CUSTOMIZE HERE"""
    
    # ===== FILE PATHS =====
    DATA_DIR = 'data'
    TECHNICIANS_FILE = os.path.join(DATA_DIR, 'technicians_file.csv')
    PRODUCTS_FILE = os.path.join(DATA_DIR, 'products_classified.csv')
    RECLAMATIONS_FILE = os.path.join(DATA_DIR, 'reclamations_file.xlsx')
    BLOCKED_ORDERS_FILE = os.path.join(DATA_DIR, 'blocked_orders.csv')
    # ✅ ADD THIS NEW LINE
    SCHEDULE_FILE = os.path.join(DATA_DIR, "current_schedule.csv")
    UNSCHEDULED_FILE = os.path.join(DATA_DIR, "unscheduled_orders.csv")
    # Add this line to Config class
    WORKING_TECHNICIANS_FILE = os.path.join(DATA_DIR, 'working_technicians.csv')
    # ===== AUTHENTICATION =====
    # ⚠️ CHANGE THESE PASSWORDS!
    CREDENTIALS = {
        "admin": "app2024",
        "manager": "manager123",
        "user": "user123"
    }
    
    # ===== ORDER CLASSIFICATION =====
    CLASS_THRESHOLDS = [
        (0, 160, 'Low', 1),
        (160, 320, 'Medium', 2),
        (320, 480, 'High', 3),
        (480, float('inf'), 'Very High', 4)
    ]
    
    # ===== EXPERTISE MAPPING =====
    EXPERTISE_LEVELS = {
        1: 'Basic Knowledge',
        2: 'Above Average',
        3: 'Good',
        4: 'Advanced'
    }
    
    # ===== UI COLORS =====
    STATUS_COLORS = {
        "Planned": "#d3d3d3",
        "In Progress": "#f9c846",
        "Partially Completed": "#fa7268",
        "Completed": "#91d18b",
        "Blocked": "#ff6b6b"
    }
    
    # ===== WORKING TIME =====
    STANDARD_WORKDAY_MINUTES = 480
    LUNCH_BREAK_MINUTES = 30
    
    # ===== BLOCK REASONS =====
    BLOCK_REASONS = [
        "Probleme Gravure SAP",
        "Ordre soudure NOK",
        "Qualite Soudure NOK",
        "Wackler",
        "Probleme DP",
        "Serrage",
        "Manque Piece",
        "Probleme Test IR",
        "Probleme SV",
        "Probleme Activation",
        "Manque etiquette",
        "Court circuit",
        "Montabilité",
        "Aspect Visuelle"
    ]
    
    # ===== PRIORITY MAPPING =====
    PRIORITY_MAPPING = {'A': 1, 'B': 2, 'C': 3}