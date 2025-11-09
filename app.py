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
from services.persistence_service import PersistenceService
def process_bulk_orders(uploaded_df, existing_df, file_path):
    """
    Process bulk orders upload:
    - Add new orders
    - Update orders with different routing times
    - Skip unchanged orders
    
    NO UI ELEMENTS - PURE PROCESSING ONLY
    """
    added = []
    modified = []
    skipped = []
    errors = []
    
    # Ensure SAP columns are strings for comparison
    existing_df['SAP'] = existing_df['SAP'].astype(str)
    
    for idx, row in uploaded_df.iterrows():
        try:
            # Extract data from uploaded file
            sap = str(row.get('Material Number', row.get('Material number', row.get('SAP', '')))).strip()
            description = str(row.get('Material description', row.get('Material Description', ''))).strip()
            routing_time = row.get('routing time', row.get('Routing Time', row.get('Routing time', None)))
            
            # Validate required fields
            if not sap or pd.isna(sap) or sap == 'nan' or sap == '':
                errors.append(f"Row {idx+2}: Missing Material Number")
                continue
            
            if pd.isna(routing_time) or routing_time == '':
                errors.append(f"Row {idx+2}: Missing routing time for SAP {sap}")
                continue
            
            try:
                routing_time = float(routing_time)
            except ValueError:
                errors.append(f"Row {idx+2} (SAP {sap}): Invalid routing time '{routing_time}'")
                continue
            
            if routing_time <= 0:
                errors.append(f"Row {idx+2} (SAP {sap}): Routing time must be positive")
                continue
            
            if not description or description == 'nan':
                description = f"Product {sap}"  # Default description
            
            # Check if SAP exists
            if sap in existing_df['SAP'].values:
                # Get existing routing time
                existing_time = existing_df.loc[existing_df['SAP'] == sap, 'routing time'].values[0]
                
                if abs(float(existing_time) - routing_time) > 0.01:  # Different routing time
                    # Modify order
                    from models.orders import modify_order
                    existing_df = modify_order(existing_df, sap, description, routing_time, file_path)
                    modified.append({
                        'SAP': sap,
                        'Description': description,
                        'Old Time': existing_time,
                        'New Time': routing_time
                    })
                else:
                    # Skip - same routing time
                    skipped.append({
                        'SAP': sap,
                        'Description': description,
                        'Routing Time': routing_time
                    })
            else:
                # Add new order
                from models.orders import add_order
                existing_df = add_order(existing_df, sap, description, routing_time, file_path)
                added.append({
                    'SAP': sap,
                    'Description': description,
                    'Routing Time': routing_time
                })
        
        except Exception as e:
            errors.append(f"Row {idx+2} (SAP {sap if 'sap' in locals() else 'Unknown'}): {str(e)}")
    
    return existing_df, added, modified, skipped, errors

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
                        PersistenceService.save_schedule(schedule_df, unscheduled_df)
                        
                        st.success("✅ Schedule generated successfully!")
                        
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
    """Orders management page with full CRUD operations + Bulk Upload"""
    st.header("📦 Manage Orders (Products)")
    
    products_classified_path = Config.PRODUCTS_FILE
    
    try:
        df_orders = load_orders(products_classified_path)
        st.success(f"✅ Loaded {len(df_orders)} products")
    except FileNotFoundError:
        st.error(f"File not found: {products_classified_path}")
        return
    
    # ===== BULK UPLOAD SECTION =====
    st.markdown("---")
    st.markdown("### 📤 Bulk Upload Orders")

    with st.expander("📂 Upload Orders File (Excel/CSV)", expanded=False):
        st.info("""
        **📋 Required Columns:**
        - `Material Number` (or `SAP`) - Product identifier
        - `Material description` (or `Material Description`) - Product name
        - `routing time` (or `Routing Time`) - Time in minutes
        
        **Optional Columns:**
        - `Order` (or `Order ID`) - Order number (not stored in products file)
        - `Priority` - Order priority (not stored in products file)
        
        **How it works:**
        - ✅ **New products** → Added to database
        - 🔄 **Existing products with different routing time** → Updated
        - ⏭️ **Existing products with same routing time** → Skipped
        """)
        
        uploaded_file = st.file_uploader(
            "Upload Orders File",
            type=['xlsx', 'xls', 'csv'],
            key="bulk_orders_upload",
            help="Excel or CSV file with Material Number, Material Description, and Routing Time"
        )
        
        if uploaded_file:
            try:
                # Read file
                if uploaded_file.name.endswith('.csv'):
                    uploaded_df = pd.read_csv(uploaded_file)
                else:
                    uploaded_df = pd.read_excel(uploaded_file, engine='openpyxl')
                
                st.success(f"✅ Loaded {len(uploaded_df)} orders from file")
                
                # Show preview
                st.markdown("#### 📋 File Preview (first 10 rows)")
                st.dataframe(uploaded_df.head(10), use_container_width=True)
                
                # Validate columns
                required_cols = ['Material Number', 'Material number', 'SAP', 'material number']
                has_material = any(col in uploaded_df.columns for col in required_cols)
                
                time_cols = ['routing time', 'Routing Time', 'Routing time']
                has_routing_time = any(col in uploaded_df.columns for col in time_cols)
                
                if not has_material:
                    st.error("❌ Missing required column: 'Material Number' or 'SAP'")
                elif not has_routing_time:
                    st.error("❌ Missing required column: 'routing time' or 'Routing Time'")
                else:
                    st.success("✅ File format validated")
                    
                    # Process button
                    st.markdown("---")
                    col1, col2, col3 = st.columns([1, 2, 1])
                    
                    with col2:
                        if st.button("🚀 Process Orders", type="primary", use_container_width=True, key="btn_process_bulk"):
                            with st.spinner("⏳ Processing orders..."):
                                # Process the orders
                                df_orders, added, modified, skipped, errors = process_bulk_orders(
                                    uploaded_df, df_orders, products_classified_path
                                )
                                
                                # ✅ ONLY store results in session state - NO display here!
                                st.session_state['bulk_results'] = {
                                    'added': added,
                                    'modified': modified,
                                    'skipped': skipped,
                                    'errors': errors,
                                    'timestamp': datetime.now()
                                }
                                
                                # Reload data
                                df_orders = load_orders(products_classified_path)
                                
                                st.success("✅ Processing complete! See results below.")
                                st.rerun()
            
            except Exception as e:
                st.error(f"❌ Error reading file: {str(e)}")
                st.markdown("**Error Details:**")
                import traceback
                st.code(traceback.format_exc())

    # ===== DISPLAY BULK UPLOAD RESULTS (OUTSIDE EXPANDER) =====
    if 'bulk_results' in st.session_state:
        results = st.session_state['bulk_results']
        added = results['added']
        modified = results['modified']
        skipped = results['skipped']
        errors = results['errors']
        
        st.markdown("---")
        st.markdown("### 📊 Bulk Upload Results")
        st.info(f"Processed at: {results['timestamp'].strftime('%Y-%m-%d %H:%M:%S')}")
        
        col_a, col_b, col_c, col_d = st.columns(4)
        
        with col_a:
            st.metric("✅ Added", len(added))
        with col_b:
            st.metric("🔄 Modified", len(modified))
        with col_c:
            st.metric("⏭️ Skipped", len(skipped))
        with col_d:
            st.metric("❌ Errors", len(errors))
        
        # ✅ Use TABS instead of expanders (tabs can't be nested, so safer)
        if added or modified or skipped or errors:
            tab1, tab2, tab3, tab4 = st.tabs([
                f"✅ Added ({len(added)})",
                f"🔄 Modified ({len(modified)})",
                f"⏭️ Skipped ({len(skipped)})",
                f"❌ Errors ({len(errors)})"
            ])
            
            with tab1:
                if added:
                    st.dataframe(pd.DataFrame(added), use_container_width=True, hide_index=True)
                else:
                    st.info("No products were added")
            
            with tab2:
                if modified:
                    st.dataframe(pd.DataFrame(modified), use_container_width=True, hide_index=True)
                else:
                    st.info("No products were modified")
            
            with tab3:
                if skipped:
                    st.info("These products already exist with the same routing time")
                    if len(skipped) <= 50:
                        st.dataframe(pd.DataFrame(skipped), use_container_width=True, hide_index=True)
                    else:
                        st.write(f"Too many to display ({len(skipped)} items). Showing first 50:")
                        st.dataframe(pd.DataFrame(skipped[:50]), use_container_width=True, hide_index=True)
                else:
                    st.info("No products were skipped")
            
            with tab4:
                if errors:
                    for error in errors:
                        st.error(error)
                else:
                    st.success("No errors occurred")
        
        # Clear results button
        col_clear1, col_clear2, col_clear3 = st.columns([1, 1, 1])
        with col_clear2:
            if st.button("🗑️ Clear Results", key="clear_bulk_results", use_container_width=True):
                del st.session_state['bulk_results']
                st.rerun()
        
        if len(added) + len(modified) > 0:
            st.success(f"✅ Successfully processed {len(added) + len(modified)} products!")
    
    # ===== DISPLAY ORDERS =====
    st.markdown("---")
    st.markdown("### 📋 Current Products")
    
    # Search/Filter
    col1, col2 = st.columns([2, 1])
    with col1:
        search_term = st.text_input("🔍 Search by SAP or Description", "")
    with col2:
        show_all = st.checkbox("Show All Products", value=False)
    
    # Filter dataframe
    if search_term:
        filtered_df = df_orders[
            df_orders['SAP'].astype(str).str.contains(search_term, case=False, na=False) |
            df_orders['Material Description'].astype(str).str.contains(search_term, case=False, na=False)
        ]
        st.info(f"Found {len(filtered_df)} matching products")
    else:
        filtered_df = df_orders
    
    # Display table
    if show_all:
        st.dataframe(filtered_df, use_container_width=True, hide_index=True)
    else:
        st.dataframe(filtered_df.head(100), use_container_width=True, hide_index=True)
        if len(filtered_df) > 100:
            st.info(f"Showing first 100 of {len(filtered_df)} products. Check 'Show All Products' to see all.")
    
    # ===== MANAGE ORDERS =====
    st.markdown("---")
    st.markdown("### ⚙️ Manage Products")
    
    tab1, tab2, tab3 = st.tabs(["➕ Add Product", "✏️ Modify Product", "🗑️ Delete Product"])
    
    # ===== TAB 1: ADD PRODUCT =====
    with tab1:
        st.markdown("#### Add New Product")
        st.info("💡 Classification is automatic based on routing time: Low (0-160min), Medium (160-320min), High (320-480min), Very High (480+min)")
        
        col1, col2 = st.columns(2)
        
        with col1:
            add_sap = st.text_input("SAP Number*", key="add_sap", help="Unique product identifier")
            add_description = st.text_input("Material Description*", key="add_description")
        
        with col2:
            add_routing_time = st.number_input(
                "Routing Time (minutes)*",
                min_value=1,
                max_value=10000,
                value=60,
                key="add_routing_time"
            )
            
            # Show predicted classification
            from models.orders import classify_order
            preview_class, preview_code = classify_order(add_routing_time)
            st.info(f"📊 Classification Preview: **{preview_class}** (Level {preview_code})")
        
        st.markdown("---")
        
        if st.button("➕ Add Product", type="primary", use_container_width=True, key="btn_add_order"):
            if not add_sap or not add_description:
                st.error("❌ SAP Number and Material Description are required")
            elif str(add_sap) in df_orders['SAP'].astype(str).values:
                st.error(f"❌ SAP {add_sap} already exists. Use 'Modify Product' to update it.")
            else:
                try:
                    df_orders = add_order(df_orders, add_sap, add_description, add_routing_time, products_classified_path)
                    st.success(f"✅ Product {add_sap} added successfully!")
                    st.balloons()
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Error adding product: {str(e)}")
    
    # ===== TAB 2: MODIFY PRODUCT =====
    with tab2:
        st.markdown("#### Modify Existing Product")
        
        col1, col2 = st.columns([1, 2])
        
        with col1:
            modify_sap = st.text_input("SAP Number to Modify*", key="modify_sap")
            
            if modify_sap and st.button("🔍 Load Product", key="btn_load_order"):
                df_orders['SAP'] = df_orders['SAP'].astype(str)
                if str(modify_sap) in df_orders['SAP'].values:
                    existing = df_orders[df_orders['SAP'] == str(modify_sap)].iloc[0]
                    st.session_state['modify_loaded'] = True
                    st.session_state['modify_existing'] = existing
                    st.success(f"✅ Loaded product: {existing['Material Description']}")
                else:
                    st.error(f"❌ SAP {modify_sap} not found")
                    st.session_state['modify_loaded'] = False
        
        with col2:
            if st.session_state.get('modify_loaded', False):
                existing = st.session_state['modify_existing']
                
                st.markdown("**Current Values:**")
                st.write(f"• Description: {existing['Material Description']}")
                st.write(f"• Routing Time: {existing['routing time']} min")
                st.write(f"• Class: {existing['Class']} (Level {existing['Class Code']})")
        
        if st.session_state.get('modify_loaded', False):
            st.markdown("---")
            st.markdown("**New Values:**")
            
            col_a, col_b = st.columns(2)
            
            with col_a:
                new_description = st.text_input(
                    "New Material Description*",
                    value=existing['Material Description'],
                    key="new_description"
                )
            
            with col_b:
                new_routing_time = st.number_input(
                    "New Routing Time (minutes)*",
                    min_value=1,
                    max_value=10000,
                    value=int(existing['routing time']),
                    key="new_routing_time"
                )
                
                # Show new classification
                from models.orders import classify_order
                new_class, new_code = classify_order(new_routing_time)
                st.info(f"📊 New Classification: **{new_class}** (Level {new_code})")
            
            st.markdown("---")
            
            if st.button("✏️ Update Product", type="primary", use_container_width=True, key="btn_modify_order"):
                if not new_description:
                    st.error("❌ Material Description is required")
                else:
                    try:
                        df_orders = modify_order(df_orders, modify_sap, new_description, new_routing_time, products_classified_path)
                        st.success(f"✅ Product {modify_sap} updated successfully!")
                        st.session_state['modify_loaded'] = False
                        st.balloons()
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Error modifying product: {str(e)}")
    
    # ===== TAB 3: DELETE PRODUCT =====
    with tab3:
        st.markdown("#### Delete Product")
        st.warning("⚠️ This action cannot be undone!")
        
        col1, col2 = st.columns([1, 2])
        
        with col1:
            delete_sap = st.text_input("SAP Number to Delete*", key="delete_sap")
            
            if delete_sap and st.button("🔍 Check Product", key="btn_check_delete"):
                df_orders['SAP'] = df_orders['SAP'].astype(str)
                if str(delete_sap) in df_orders['SAP'].values:
                    existing = df_orders[df_orders['SAP'] == str(delete_sap)].iloc[0]
                    st.session_state['delete_loaded'] = True
                    st.session_state['delete_existing'] = existing
                    st.info(f"Found: {existing['Material Description']}")
                else:
                    st.error(f"❌ SAP {delete_sap} not found")
                    st.session_state['delete_loaded'] = False
        
        with col2:
            if st.session_state.get('delete_loaded', False):
                existing = st.session_state['delete_existing']
                
                st.markdown("**Product Details:**")
                st.write(f"• SAP: {existing['SAP']}")
                st.write(f"• Description: {existing['Material Description']}")
                st.write(f"• Routing Time: {existing['routing time']} min")
                st.write(f"• Class: {existing['Class']}")
        
        if st.session_state.get('delete_loaded', False):
            st.markdown("---")
            
            col_confirm1, col_confirm2, col_confirm3 = st.columns([1, 2, 1])
            
            with col_confirm2:
                confirm_delete = st.checkbox(
                    f"⚠️ I confirm deletion of SAP {delete_sap}",
                    key="confirm_delete"
                )
                
                if confirm_delete:
                    if st.button("🗑️ DELETE PRODUCT", type="primary", use_container_width=True, key="btn_delete_order"):
                        try:
                            df_orders = delete_order(df_orders, delete_sap, products_classified_path)
                            st.success(f"✅ Product {delete_sap} deleted successfully!")
                            st.session_state['delete_loaded'] = False
                            st.rerun()
                        except Exception as e:
                            st.error(f"❌ Error deleting product: {str(e)}")
    
    # ===== STATISTICS =====
    st.markdown("---")
    st.markdown("### 📊 Product Statistics")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Total Products", len(df_orders))
    
    with col2:
        avg_time = df_orders['routing time'].mean()
        st.metric("Avg Routing Time", f"{avg_time:.1f} min")
    
    with col3:
        if 'Class' in df_orders.columns:
            most_common = df_orders['Class'].value_counts().index[0] if not df_orders['Class'].isna().all() else "N/A"
            st.metric("Most Common Class", most_common)
    
    with col4:
        max_time = df_orders['routing time'].max()
        st.metric("Max Routing Time", f"{max_time:.0f} min")
    
    # Class distribution
    if 'Class' in df_orders.columns:
        st.markdown("#### 📈 Classification Distribution")
        class_counts = df_orders['Class'].value_counts()
        st.bar_chart(class_counts)

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