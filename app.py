import streamlit as st
import pandas as pd
from datetime import datetime
import os

from config import Config
from utils.session_manager import SessionManager
from services.auth_service import AuthService
from services.file_service import FileService
from services.schedule_service import ScheduleService
from pages.schedule_page import SchedulePage

# Import YOUR existing models
from models.orders import load_orders, add_order, modify_order, delete_order
from models.technicians import load_technicians, add_technician, modify_technician, delete_technician
from models.reclamations import load_reclamations, add_reclamation, modify_reclamation, delete_reclamation
from models.initial_scheduling import (
    find_missing_sap_numbers, merge_orders_with_class_code,
    calculate_working_time, create_initial_schedule
)

# Page config
st.set_page_config(
    page_title="Draexlmaier Scheduling System",
    page_icon="📅",
    layout="wide",
    initial_sidebar_state="expanded"
)

def main():
    """Main application entry point"""
    
    # Initialize
    SessionManager.initialize()
    FileService.initialize_all_files()
    
    # Check authentication
    if not AuthService.require_login():
        return
    
    # Sidebar
    st.sidebar.title("🗂️ Draexlmaier")
    st.sidebar.markdown(f"**👤 User:** {SessionManager.get('username', 'Unknown')}")
    st.sidebar.markdown("---")
    
    pages = {
        "📅 Schedule Management": render_schedule_page,
        "📊 Initial Scheduling": render_initial_scheduling_page,
        "👷 Manage Technicians": render_technicians_page,
        "📦 Manage Orders": render_orders_page,
        "⚠️ Manage Reclamations": render_reclamations_page,
    }
    
    choice = st.sidebar.radio("📍 Navigate to", list(pages.keys()))
    
    st.sidebar.markdown("---")
    if st.sidebar.button("🚪 Logout", use_container_width=True):
        AuthService.logout()
        st.rerun()
    
    # Render selected page
    pages[choice]()

def render_schedule_page():
    """Editable schedule management"""
    SchedulePage.render()

def render_initial_scheduling_page():
    """Initial scheduling with file upload"""
    from utils.ui_components import UIComponents
    
    UIComponents.page_header(
        "📊 Initial Scheduling",
        "Upload orders and shifts files to generate schedule"
    )
    
    # Instructions
    with st.expander("📖 Instructions", expanded=False):
        st.markdown("""
        **How to use:**
        1. Prepare your **Orders File** (Excel) with columns: `Order`, `Material Number`, `Material description`, `Priority`
        2. Prepare your **Shifts File** (Excel) with columns: `Matricule`, `Technician Name`, `Working`, `To another`, `Break`, `Extra Time`
        3. Upload both files below
        4. Click "Generate Schedule"
        5. Go to "Schedule Management" to view and edit
        """)
    
    # File uploads
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("#### 📄 Orders File")
        uploaded_orders = st.file_uploader(
            "Upload Orders Excel File",
            type=['xlsx'],
            key="init_orders",
            help="Excel file with columns: Order, Material Number, Material description, Priority"
        )
        
        if uploaded_orders:
            st.success(f"✅ {uploaded_orders.name}")
    
    with col2:
        st.markdown("#### 👷 Shifts File")
        uploaded_shifts = st.file_uploader(
            "Upload Shifts Excel File",
            type=['xlsx'],
            key="init_shifts",
            help="Excel file with columns: Matricule, Technician Name, Working, To another, Break, Extra Time"
        )
        
        if uploaded_shifts:
            st.success(f"✅ {uploaded_shifts.name}")
    
    # Generate button
    if uploaded_orders and uploaded_shifts:
        st.markdown("---")
        
        col_a, col_b, col_c = st.columns([1, 2, 1])
        with col_b:
            if st.button("🚀 Generate Schedule", type="primary", use_container_width=True):
                try:
                    with st.spinner("⏳ Processing files and generating schedule..."):
                        # Read files
                        orders_df = pd.read_excel(uploaded_orders, engine='openpyxl')
                        shifts_df = pd.read_excel(uploaded_shifts, engine='openpyxl')
                        
                        st.info(f"📊 Loaded {len(orders_df)} orders and {len(shifts_df)} technician shifts")
                        
                        # Validate SAP numbers
                        products_df = pd.read_csv(Config.PRODUCTS_FILE)
                        missing_sap = find_missing_sap_numbers(orders_df, products_df)
                        
                        if missing_sap:
                            st.error("❌ Missing SAP numbers found. Please add them in 'Manage Orders' page first.")
                            with st.expander("📋 Missing SAP Numbers"):
                                for sap in missing_sap:
                                    st.write(f"• {sap}")
                            return
                        
                        # Process orders
                        merged_orders = merge_orders_with_class_code(orders_df, Config.PRODUCTS_FILE)
                        st.success(f"✅ Orders classified: {len(merged_orders)} orders")
                        
                        # Calculate working time
                        working_technicians = calculate_working_time(Config.TECHNICIANS_FILE, shifts_df)
                        st.success(f"✅ Working technicians calculated: {len(working_technicians)} available")
                        
                        # Create schedule
                        schedule_df, _, unscheduled_df = create_initial_schedule(working_technicians, merged_orders)
                        
                        # Initialize with tracking columns
                        schedule_df = ScheduleService.initialize_schedule_dataframe(schedule_df)
                        
                        # Save to session
                        SessionManager.set('initial_schedule_df', schedule_df)
                        SessionManager.set('unscheduled_orders_df', unscheduled_df)
                        SessionManager.set('merged_orders', merged_orders)
                        SessionManager.set('working_technicians', working_technicians)
                        SessionManager.set('_initial_schedule_processed', True)
                        
                        st.success("✅ Schedule generated successfully!")
                        st.balloons()
                        
                        # Summary
                        st.markdown("### 📊 Schedule Summary")
                        col1, col2, col3, col4 = st.columns(4)
                        
                        with col1:
                            st.metric("📅 Scheduled", len(schedule_df))
                        with col2:
                            st.metric("⏳ Unscheduled", len(unscheduled_df))
                        with col3:
                            st.metric("👷 Technicians", len(working_technicians))
                        with col4:
                            total_time = schedule_df['Routing Time (min)'].sum()
                            st.metric("⏱️ Total Time", f"{total_time:.0f} min")
                        
                        st.info("💡 Go to '📅 Schedule Management' to view and edit the schedule")
                
                except Exception as e:
                    st.error(f"❌ Error processing files: {str(e)}")
                    import traceback
                    with st.expander("🔍 Show error details"):
                        st.code(traceback.format_exc())
                    st.warning("Please check your file formats and try again.")
    
    # Display current schedule if exists
    if SessionManager.get('initial_schedule_df') is not None:
        st.markdown("---")
        st.markdown("### 📋 Current Schedule Preview")
        
        df = SessionManager.get('initial_schedule_df')
        unscheduled = SessionManager.get('unscheduled_orders_df')
        
        col1, col2 = st.columns([3, 1])
        
        with col1:
            st.dataframe(
                df[['Priority', 'Order ID', 'SAP', 'Material Description', 'Technician Name', 'Status', 'Routing Time (min)']].head(10),
                use_container_width=True,
                hide_index=True
            )
        
        with col2:
            if st.button("🗑️ Clear Schedule", use_container_width=True):
                SessionManager.clear_schedule()
                st.success("Schedule cleared!")
                st.rerun()
            
            if len(unscheduled) > 0:
                st.warning(f"⚠️ {len(unscheduled)} unscheduled")

def render_technicians_page():
    """Technicians management page - Copy your existing code here"""
    st.header("👷 Manage Technicians")
    
    technicians_file_path = Config.TECHNICIANS_FILE
    
    try:
        technicians = load_technicians(technicians_file_path)
    except FileNotFoundError:
        st.error(f"File not found: {technicians_file_path}")
        return
    
    # Display technicians
    if st.checkbox("Show Technicians List"):
        if technicians:
            st.subheader("Current Technicians")
            technicians_data = [tech.to_dict() for tech in technicians]
            st.dataframe(pd.DataFrame(technicians_data), use_container_width=True)
        else:
            st.info("No technicians found")
    
    # Add, Modify, Delete sections
    st.info("💡 Copy your full manage_technicians() function code here from your old app.py")
    st.markdown("### Add / Modify / Delete Technicians")
    with st.expander("Add a Technician"):
        col1, col2 = st.columns(2)
        with col1:
            matricule = st.text_input("Matricule")
            nom_prenom = st.text_input("Nom et prénom")
            niveau_4 = st.text_input("Niveau 4")
            niveau_3 = st.text_input("Niveau 3")
        with col2:
            niveau_2 = st.text_input("Niveau 2")
            niveau_1 = st.text_input("Niveau 1")
        if st.button("Add Technician"):
            success, message = add_technician(matricule, nom_prenom, niveau_4, niveau_3, niveau_2, niveau_1, technicians_file_path)
            if success:
                st.success(message)
                st.rerun()
            else:
                st.error(message)
    with st.expander("Modify a Technician"):
        matricule_modify = st.text_input("Matricule to modify")
        new_data = {
            'Nom et prénom': st.text_input("New Nom et prénom"),
            'Niveau 4': st.text_input("New Niveau 4"),
            'Niveau 3': st.text_input("New Niveau 3"),
            'Niveau 2': st.text_input("New Niveau 2"),
            'Niveau 1': st.text_input("New Niveau 1")
        }
        if st.button("Modify Technician"):
            success, message = modify_technician(matricule_modify, new_data, technicians_file_path)
            if success:
                st.success(message)
                st.rerun()
            else:
                st.error(message)
    with st.expander("Delete a Technician"):
        matricule_delete = st.text_input("Matricule to delete")
        if st.button("Delete Technician"):
            success, message = delete_technician(matricule_delete, technicians_file_path)
            if success:
                st.success(message)
                st.rerun()
            else:
                st.error(message)
    st.header("Technicians Statistics")
    df = pd.DataFrame([tech.to_dict() for tech in technicians])
    st.write("### Classification Counts")
    classification_counts = df['Classification'].value_counts()
    st.bar_chart(classification_counts)
    st.write("### Basic Statistics")
    st.write(df.describe())

def render_orders_page():
    """Orders management page - Copy your existing code here"""
    st.header("📦 Manage Orders")
    
    products_classified_path = Config.PRODUCTS_FILE
    
    try:
        df_orders = load_orders(products_classified_path)
        st.success(f"✅ Loaded {len(df_orders)} products")
    except FileNotFoundError:
        st.error(f"File not found: {products_classified_path}")
        return
    
    # Display orders
    if st.checkbox("Show Products List (first 100)"):
        st.dataframe(df_orders.head(100), use_container_width=True)
    
    st.info("💡 Copy your full manage_orders() function code here from your old app.py")
    st.markdown("""
    **Replace:**
```python
    products_classified_path = '../data/products_classified.csv'
```
    **With:**
```python
    products_classified_path = Config.PRODUCTS_FILE
```
    """)

def render_reclamations_page():
    st.header("Manage Reclamations")
    reclamations_file_path = Config.RECLAMATIONS_FILE
    reclamations = load_reclamations(reclamations_file_path)
    if 'show_reclamations' not in st.session_state:
        st.session_state['show_reclamations'] = False
    if st.checkbox("Show/Hide Reclamations"):
        st.session_state['show_reclamations'] = not st.session_state['show_reclamations']
    if st.session_state['show_reclamations']:
        if reclamations:
            st.subheader("Current Reclamations")
            reclamations_data = [rec.to_dict() for rec in reclamations]
            st.table(pd.DataFrame(reclamations_data))
        else:
            st.write("No reclamations available.")
    with st.expander("Add a Reclamation"):
        col1, col2 = st.columns(2)
        with col1:
            date = st.text_input("Date")
            ordre = st.text_input("Ordre")
            sap = st.text_input("SAP")
            description = st.text_input("Description")
        with col2:
            qty = st.text_input("Qty")
            reclamation = st.text_input("Reclamation")
            remarque = st.text_input("Remarque")
            technicien = st.text_input("Technicien")
            decision = st.text_input("Decision")
            qs = st.text_input("QS")
        if st.button("Add Reclamation"):
            success, message = add_reclamation(date, ordre, sap, description, qty, reclamation, remarque, technicien, decision, qs, reclamations_file_path)
            if success:
                st.success(message)
                st.rerun()
            else:
                st.error(message)
    with st.expander("Modify a Reclamation"):
        ordre_modify = st.text_input("Ordre to modify")
        new_data = {
            'Date': st.text_input("New Date"),
            'SAP': st.text_input("New SAP"),
            'Description': st.text_input("New Description"),
            'Qty': st.text_input("New Qty"),
            'Reclamation': st.text_input("New Reclamation"),
            'Remarque': st.text_input("New Remarque"),
            'Technicien': st.text_input("New Technicien"),
            'Decision': st.text_input("New Decision"),
            'QS': st.text_input("New QS")
        }
        if st.button("Modify Reclamation"):
            success, message = modify_reclamation(ordre_modify, new_data, reclamations_file_path)
            if success:
                st.success(message)
                st.rerun()
            else:
                st.error(message)
    with st.expander("Delete a Reclamation"):
        ordre_delete = st.text_input("Ordre to delete")
        if st.button("Delete Reclamation"):
            success, message = delete_reclamation(ordre_delete, reclamations_file_path)
            if success:
                st.success(message)
                st.rerun()
            else:
                st.error(message)
    st.subheader("Recommendations")
    recommendations = generate_recommendations(reclamations)
    if recommendations:
        st.table(pd.DataFrame(recommendations))
    else:
        st.write("No recommendations available.")


if __name__ == "__main__":
    main()