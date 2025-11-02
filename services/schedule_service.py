import pandas as pd
import json
import uuid
from datetime import datetime
from typing import Tuple, List, Dict
from config import Config

class ScheduleService:
    """Handle all scheduling operations including editable features"""
    
    # ===== INITIALIZATION =====
    
    @staticmethod
    def create_schedule_row_id() -> str:
        """Generate unique schedule row ID"""
        return str(uuid.uuid4())
    
    @staticmethod
    def initialize_schedule_dataframe(df: pd.DataFrame) -> pd.DataFrame:
        """Add all necessary tracking columns to schedule"""
        df = df.copy()
        df['ScheduleRowID'] = [ScheduleService.create_schedule_row_id() for _ in range(len(df))]
        df['Status'] = 'Planned'
        if 'Priority' not in df.columns:
            df['Priority'] = None  # If no priority exists
        df['SequenceNumber'] = range(1, len(df) + 1)  
        
        # Time tracking columns for multiple sessions
        df['FirstStartTime'] = None
        df['EndTime'] = None
        df['TotalTimeSpent'] = 0.0
        df['RemainingRoutingTime'] = df['Routing Time (min)']
        df['WorkSessions'] = '[]'  # JSON array of {start, stop} objects
        
        return df
    
    # ===== STATUS MANAGEMENT (Multiple Sessions) =====
    
    @staticmethod
    def update_order_status(
        df: pd.DataFrame,
        schedule_row_id: str,
        action: str
    ) -> Tuple[pd.DataFrame, bool, str]:
        """Update order status with multiple work session tracking"""
        row_mask = df['ScheduleRowID'] == schedule_row_id
        if not row_mask.any():
            return df, False, "Order not found"
        
        row_idx = df[row_mask].index[0]
        now = datetime.now()
        current_status = df.at[row_idx, "Status"]
        
        # Initialize WorkSessions if empty
        if pd.isna(df.at[row_idx, "WorkSessions"]) or df.at[row_idx, "WorkSessions"] == "":
            df.at[row_idx, "WorkSessions"] = "[]"
        
        work_sessions = json.loads(df.at[row_idx, "WorkSessions"])
        
        # Handle START action
        if action == "start":
            if current_status not in ["Planned", "Partially Completed"]:
                return df, False, f"Cannot start order with status: {current_status}"
            
            df.at[row_idx, "Status"] = "In Progress"
            
            # Record first start time
            if pd.isna(df.at[row_idx, "FirstStartTime"]):
                df.at[row_idx, "FirstStartTime"] = now
            
            # Add new session
            work_sessions.append({"start": now.isoformat(), "stop": None})
            message = "Order started"
        
        # Handle STOP action
        elif action == "stop":
            if current_status != "In Progress":
                return df, False, "Can only stop orders that are in progress"
            
            df.at[row_idx, "Status"] = "Partially Completed"
            
            # Close current session
            if work_sessions and work_sessions[-1]["stop"] is None:
                work_sessions[-1]["stop"] = now.isoformat()
            
            # Calculate cumulative time
            total_time = ScheduleService._calculate_total_session_time(work_sessions)
            routing_time = df.at[row_idx, "Routing Time (min)"]
            
            df.at[row_idx, "TotalTimeSpent"] = total_time
            df.at[row_idx, "RemainingRoutingTime"] = max(0, routing_time - total_time)
            
            message = f"Order paused. Total time spent: {total_time:.1f} min"
        
        # Handle END action
        elif action == "end":
            if current_status not in ["In Progress", "Partially Completed"]:
                return df, False, f"Cannot complete order with status: {current_status}"
            
            df.at[row_idx, "Status"] = "Completed"
            df.at[row_idx, "EndTime"] = now
            
            # Close current session if open
            if work_sessions and work_sessions[-1]["stop"] is None:
                work_sessions[-1]["stop"] = now.isoformat()
            
            # Calculate final time
            total_time = ScheduleService._calculate_total_session_time(work_sessions)
            df.at[row_idx, "TotalTimeSpent"] = total_time
            df.at[row_idx, "RemainingRoutingTime"] = 0
            
            message = f"Order completed. Total time: {total_time:.1f} min"
        
        else:
            return df, False, f"Unknown action: {action}"
        
        # Save updated sessions
        df.at[row_idx, "WorkSessions"] = json.dumps(work_sessions)
        
        return df, True, message
    
    @staticmethod
    def _calculate_total_session_time(work_sessions: List[Dict]) -> float:
        """Calculate total time across all work sessions in minutes"""
        total_time = 0.0
        for session in work_sessions:
            if session.get("stop"):
                start = datetime.fromisoformat(session["start"])
                stop = datetime.fromisoformat(session["stop"])
                total_time += (stop - start).total_seconds() / 60
        return total_time
    
    # ===== EDITABLE FEATURES =====
    
    @staticmethod
    def change_technician(
        df: pd.DataFrame,
        schedule_row_id: str,
        new_tech_name: str,
        new_tech_matricule: str,
        new_tech_expertise: int
    ) -> Tuple[pd.DataFrame, bool, str]:
        """Change assigned technician and update workloads"""
        row_mask = df['ScheduleRowID'] == schedule_row_id
        if not row_mask.any():
            return df, False, "Order not found"
        
        row_idx = df[row_mask].index[0]
        
        # Only allow for orders not yet started
        if df.at[row_idx, "Status"] != "Planned":
            return df, False, "Can only reassign orders that haven't started yet"
        
        # Check expertise compatibility
        order_class_code = df.at[row_idx, "Class Code"] if "Class Code" in df.columns else 1
        if new_tech_expertise < order_class_code:
            return df, False, f"Technician expertise (Level {new_tech_expertise}) insufficient for order (Level {order_class_code})"
        
        # Update assignment
        df.at[row_idx, "Technician Name"] = new_tech_name
        df.at[row_idx, "Technician Matricule"] = new_tech_matricule
        
        return df, True, f"Order reassigned to {new_tech_name}"
    
    @staticmethod
    def change_priority(
        df: pd.DataFrame,
        schedule_row_id: str,
        new_priority: int
    ) -> Tuple[pd.DataFrame, bool, str]:
        """Change order priority (only for Planned orders)"""
        row_mask = df['ScheduleRowID'] == schedule_row_id
        if not row_mask.any():
            return df, False, "Order not found"
        
        row_idx = df[row_mask].index[0]
        
        if df.at[row_idx, "Status"] != "Planned":
            return df, False, "Can only change priority for Planned orders"
        
        if new_priority < 1:
            return df, False, "Priority must be at least 1"
        
        old_priority = df.at[row_idx, "Priority"]
        df.at[row_idx, "Priority"] = new_priority
        
        # Re-sort by priority
        df = df.sort_values('Priority', na_position='last').reset_index(drop=True)
        
        return df, True, f"Priority changed from {old_priority} to {new_priority}"
    
    @staticmethod
    def modify_routing_time(
        df: pd.DataFrame,
        schedule_row_id: str,
        new_routing_time: float
    ) -> Tuple[pd.DataFrame, bool, str]:
        """Modify routing time for an order (only Planned orders)"""
        row_mask = df['ScheduleRowID'] == schedule_row_id
        if not row_mask.any():
            return df, False, "Order not found"
        
        row_idx = df[row_mask].index[0]
        
        if df.at[row_idx, "Status"] != "Planned":
            return df, False, "Can only modify routing time for Planned orders"
        
        if new_routing_time <= 0:
            return df, False, "Routing time must be positive"
        
        old_time = df.at[row_idx, "Routing Time (min)"]
        df.at[row_idx, "Routing Time (min)"] = new_routing_time
        df.at[row_idx, "RemainingRoutingTime"] = new_routing_time
        
        return df, True, f"Routing time changed from {old_time} to {new_routing_time} minutes"
    
    # ===== FILTERING & QUERIES =====
    
    @staticmethod
    def filter_by_status(df: pd.DataFrame, statuses: List[str]) -> pd.DataFrame:
        """Filter schedule by status(es)"""
        if not statuses:
            return df
        return df[df['Status'].isin(statuses)]
    
    @staticmethod
    def filter_by_technician(df: pd.DataFrame, technician_names: List[str]) -> pd.DataFrame:
        """Filter schedule by technician(s)"""
        if not technician_names:
            return df
        return df[df['Technician Name'].isin(technician_names)]
    
    @staticmethod
    def get_statistics(df: pd.DataFrame) -> Dict[str, int]:
        """Get schedule statistics"""
        return {
            "Planned": len(df[df['Status'] == 'Planned']),
            "In Progress": len(df[df['Status'] == 'In Progress']),
            "Partially Completed": len(df[df['Status'] == 'Partially Completed']),
            "Completed": len(df[df['Status'] == 'Completed']),
            "Total": len(df)
        }
    
    @staticmethod
    def mark_as_blocked(
        df: pd.DataFrame,
        schedule_row_id: str,
        block_reason: str,
        time_spent: float
    ) -> Tuple[pd.DataFrame, bool, str]:
        """Mark an order as blocked"""
        row_mask = df['ScheduleRowID'] == schedule_row_id
        if not row_mask.any():
            return df, False, "Order not found"
        
        row_idx = df[row_mask].index[0]
        
        df.at[row_idx, "Status"] = "Blocked"
        df.at[row_idx, "Remark"] = f"Blocked: {block_reason}. Time spent: {time_spent} min"
        
        routing_time = df.at[row_idx, "Routing Time (min)"]
        df.at[row_idx, "RemainingRoutingTime"] = max(0, routing_time - time_spent)
        
        return df, True, f"Order marked as blocked: {block_reason}"