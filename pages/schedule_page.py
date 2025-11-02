import streamlit as st
import pandas as pd
from datetime import datetime
from services.schedule_service import ScheduleService
from utils.ui_components import UIComponents
from utils.session_manager import SessionManager
from config import Config

class SchedulePage:
    """Editable schedule page with multiple session tracking"""
    
    @staticmethod
    def render():
        """Main render function for schedule page"""
        UIComponents.page_header(
            "📅 Schedule Management",
            f"Current Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        
        df = SessionManager.get('initial_schedule_df')
        
        if df is None:
            UIComponents.info_message(
                "No schedule available. Please upload orders and shifts files in the Initial Scheduling page.",
                "info"
            )
            return
        
        # ===== EDITABLE SCHEDULE SECTION =====
        SchedulePage._render_edit_section(df)
        
        st.markdown("---")
        
        # ===== FILTERS =====
        filtered_df = SchedulePage._render_filters(df)
        
        # ===== STATISTICS =====
        SchedulePage._render_statistics(df)
        
        st.markdown("---")
        
        # ===== ORDERS DISPLAY =====
        SchedulePage._render_orders(filtered_df)
        
        # ===== DETAILED TABLE =====
        if st.checkbox("📊 Show Detailed Schedule Table"):
            SchedulePage._render_detailed_table(df)
    
    @staticmethod
    def _render_edit_section(df: pd.DataFrame):
        """Render editable schedule controls"""
        st.markdown("### ✏️ Edit Schedule")
        
        with st.expander("📝 Modify Schedule (Orders Not Started)", expanded=False):
            planned_orders = df[df['Status'] == 'Planned'].copy()
            
            if planned_orders.empty:
                st.info("No planned orders available for editing")
                return
            
            tab1, tab2, tab3 = st.tabs([
                "👤 Change Technician",
                "🔢 Change Priority", 
                "⏱️ Modify Time"
            ])
            
            # TAB 1: Change Technician
            with tab1:
                SchedulePage._render_technician_change(planned_orders)
            
            # TAB 2: Change Priority
            with tab2:
                SchedulePage._render_priority_change(planned_orders)
            
            # TAB 3: Modify Routing Time
            with tab3:
                SchedulePage._render_time_modification(planned_orders)
    
    @staticmethod
    def _render_technician_change(planned_orders: pd.DataFrame):
        """Render technician reassignment interface"""
        st.markdown("**Reassign Order to Different Technician**")
        
        col1, col2 = st.columns(2)
        
        with col1:
            order_options = {
                f"{row['Order ID']} - {row['SAP']} ({row['Technician Name']})": row['ScheduleRowID']
                for _, row in planned_orders.iterrows()
            }
            
            if not order_options:
                st.info("No orders available")
                return
            
            selected_order = st.selectbox(
                "Select Order to Reassign",
                list(order_options.keys()),
                key="reassign_order_select"
            )
            selected_order_id = order_options[selected_order]
        
        with col2:
            working_techs = SessionManager.get('working_technicians')
            
            if working_techs is not None:
                if isinstance(working_techs, pd.DataFrame):
                    tech_list = working_techs.to_dict('records')
                else:
                    tech_list = working_techs
                
                tech_options = {
                    f"{tech['Technician Name']} (Level {tech.get('Expertise Class', '?')}) - {tech.get('Working Time', 0):.0f} min": 
                    (tech['Technician Name'], tech['Matricule'], tech.get('Expertise Class', 1))
                    for tech in tech_list
                }
                
                if tech_options:
                    selected_tech = st.selectbox(
                        "Assign to Technician",
                        list(tech_options.keys()),
                        key="new_tech_select"
                    )
                    new_tech_name, new_tech_matricule, new_tech_expertise = tech_options[selected_tech]
                else:
                    st.warning("No technicians available")
                    return
            else:
                st.warning("Technician data not available")
                return
        
        if st.button("🔄 Reassign Technician", key="btn_reassign_tech"):
            df = SessionManager.get('initial_schedule_df')
            updated_df, success, message = ScheduleService.change_technician(
                df, selected_order_id, new_tech_name, new_tech_matricule, new_tech_expertise
            )
            
            if success:
                SessionManager.set('initial_schedule_df', updated_df)
                st.success(f"✅ {message}")
                st.rerun()
            else:
                st.error(f"❌ {message}")
    @staticmethod
    def _render_priority_change(planned_orders: pd.DataFrame):
        """Render priority change interface"""
        st.markdown("**Change Order Priority (A/B/C)**")
        
        col1, col2 = st.columns(2)
        
        with col1:
            order_options = {
                f"{row['Order ID']} - Current Priority: {row.get('Priority', 'None')}": row['ScheduleRowID']
                for _, row in planned_orders.iterrows()
            }
            
            if not order_options:
                st.info("No orders available")
                return
            
            selected_order = st.selectbox(
                "Select Order",
                list(order_options.keys()),
                key="priority_order_select"
            )
            selected_order_id = order_options[selected_order]
        
        with col2:
            # ✅ CHANGED: Dropdown instead of number input
            new_priority = st.selectbox(
                "New Priority",
                options=['A', 'B', 'C', 'None'],
                index=0,  # Default to 'A'
                key="new_priority_select",
                help="A = Highest priority, B = Medium, C = Low, None = No priority"
            )
        
        if st.button("🔢 Update Priority", key="btn_update_priority"):
            df = SessionManager.get('initial_schedule_df')
            
            # Find the order
            row_mask = df['ScheduleRowID'] == selected_order_id
            if not row_mask.any():
                st.error("❌ Order not found")
                return
            
            row_idx = df[row_mask].index[0]
            
            # Check if order can be edited
            if df.at[row_idx, "Status"] != "Planned":
                st.error("❌ Can only change priority for Planned orders")
                return
            
            # Store old priority for message
            old_priority = df.at[row_idx, "Priority"]
            
            # ✅ UPDATE PRIORITY (A/B/C or None)
            new_priority_value = None if new_priority == 'None' else new_priority
            df.at[row_idx, "Priority"] = new_priority_value
            
            # ✅ RE-SORT ENTIRE SCHEDULE BY PRIORITY
            # Create temporary numeric priority for sorting
            priority_mapping = {'A': 1, 'B': 2, 'C': 3}
            df['_temp_priority_num'] = df['Priority'].map(priority_mapping)
            df['_temp_priority_num'] = df['_temp_priority_num'].fillna(999)  # None = 999 (last)
            
            # Sort by priority, then by routing time (descending)
            df = df.sort_values(
                by=['_temp_priority_num', 'Routing Time (min)'], 
                ascending=[True, False]
            ).reset_index(drop=True)
            
            # Update sequence numbers
            df['SequenceNumber'] = range(1, len(df) + 1)
            
            # Remove temporary column
            df = df.drop('_temp_priority_num', axis=1)
            
            # Save back to session
            SessionManager.set('initial_schedule_df', df)
            
            st.success(f"✅ Priority changed from '{old_priority}' to '{new_priority_value}'")
            st.success(f"📊 Schedule re-sorted. Order is now at position #{df.at[row_idx, 'SequenceNumber']}")
            st.rerun()
    

    
    @staticmethod
    def _render_time_modification(planned_orders: pd.DataFrame):
        """Render routing time modification interface"""
        st.markdown("**Modify Order Routing Time**")
        
        col1, col2 = st.columns(2)
        
        with col1:
            order_options = {
                f"{row['Order ID']} - Current: {row['Routing Time (min)']} min": row['ScheduleRowID']
                for _, row in planned_orders.iterrows()
            }
            
            if not order_options:
                st.info("No orders available")
                return
            
            selected_order = st.selectbox(
                "Select Order",
                list(order_options.keys()),
                key="modify_time_order_select"
            )
            selected_order_id = order_options[selected_order]
        
        with col2:
            new_time = st.number_input(
                "New Routing Time (minutes)",
                min_value=1,
                max_value=1000,
                value=60,
                key="new_time_input"
            )
        
        if st.button("⏱️ Update Routing Time", key="btn_update_time"):
            df = SessionManager.get('initial_schedule_df')
            updated_df, success, message = ScheduleService.modify_routing_time(
                df, selected_order_id, new_time
            )
            
            if success:
                SessionManager.set('initial_schedule_df', updated_df)
                st.success(f"✅ {message}")
                st.rerun()
            else:
                st.error(f"❌ {message}")
    
    @staticmethod
    def _render_filters(df: pd.DataFrame) -> pd.DataFrame:
        """Render filter controls"""
        st.markdown("### 🔍 Filters")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            status_filter = st.multiselect(
                "Status",
                options=df['Status'].unique(),
                default=[],
                key="status_filter"
            )
        
        with col2:
            tech_filter = st.multiselect(
                "Technician",
                options=sorted(df['Technician Name'].unique()),
                default=[],
                key="tech_filter"
            )
        
        with col3:
            priority_filter = st.multiselect(
                "Priority",
                options=sorted(df['Priority'].dropna().unique()) if 'Priority' in df.columns else [],
                default=[],
                key="priority_filter"
            )
        
        # Apply filters
        filtered_df = df.copy()
        
        if status_filter:
            filtered_df = ScheduleService.filter_by_status(filtered_df, status_filter)
        
        if tech_filter:
            filtered_df = ScheduleService.filter_by_technician(filtered_df, tech_filter)
        
        if priority_filter and 'Priority' in filtered_df.columns:
            filtered_df = filtered_df[filtered_df['Priority'].isin(priority_filter)]
        
        # Sort by priority
        if 'Priority' in filtered_df.columns:
            filtered_df = filtered_df.sort_values('Priority', na_position='last')
        
        return filtered_df
    
    @staticmethod
    def _render_statistics(df: pd.DataFrame):
        """Render schedule statistics"""
        st.markdown("### 📊 Statistics")
        
        stats = ScheduleService.get_statistics(df)
        UIComponents.metric_cards(stats)
    
    @staticmethod
    def _render_orders(filtered_df: pd.DataFrame):
        """Render order cards with action buttons"""
        st.markdown("### 📋 Orders")
        
        if filtered_df.empty:
            st.info("No orders match the current filters")
            return
        
        for idx, row in filtered_df.iterrows():
            priority_display = ""
            priority_value = row.get('Priority', None)
            if priority_value == 'A' or priority_value == 1:
                priority_display = "🔴 Priority A"
            elif priority_value == 'B' or priority_value == 2:
                priority_display = "🟡 Priority B"
            elif priority_value == 'C' or priority_value == 3:
                priority_display = "🟢 Priority C"
            else:
                priority_display = "⚪ No Priority"

            with st.expander(
                f"{priority_display} | Order {row['Order ID']} - {row['SAP']} | {row['Technician Name']}",
                expanded=False
            ):
                SchedulePage._render_order_card(row)
    
    @staticmethod
    def _render_order_card(row: pd.Series):
        """Render individual order card"""
        col1, col2, col3, col4 = st.columns([3, 2, 2, 2])
        
        # Column 1: Order Details
        with col1:
            st.markdown(f"**Material:** {row['Material Description']}")
            st.markdown(f"**Technician:** {row['Technician Name']}")
            
            # Display Priority (A/B/C)
            priority_value = row.get('Priority', None)
            if priority_value:
                st.markdown(f"**Priority:** {priority_value}")
            else:
                st.markdown(f"**Priority:** No Priority")
            
            if pd.notnull(row.get('FirstStartTime')):
                start_time = pd.to_datetime(row['FirstStartTime']).strftime('%H:%M:%S')
                st.markdown(f"**First Started:** {start_time}")
            
            # Display work sessions
            if pd.notna(row.get('WorkSessions')) and row['WorkSessions'] != '[]':
                with st.expander("📝 Work Sessions"):
                    sessions_text = UIComponents.format_work_sessions(row['WorkSessions'])
                    st.text(sessions_text)
        
        # Column 2: Time Information
        with col2:
            st.markdown(f"**Planned:** {row['Routing Time (min)']} min")
            
            if pd.notnull(row.get('TotalTimeSpent')) and row['TotalTimeSpent'] > 0:
                st.markdown(f"**Time Spent:** {row['TotalTimeSpent']:.1f} min")
                efficiency = (row['TotalTimeSpent'] / row['Routing Time (min)']) * 100
                st.markdown(f"**Efficiency:** {efficiency:.1f}%")
            
            if pd.notnull(row.get('RemainingRoutingTime')):
                st.markdown(f"**Remaining:** {row['RemainingRoutingTime']:.1f} min")
        
        # Column 3: Status
        with col3:
            st.markdown(f"**Status:**")
            st.markdown(UIComponents.status_badge(row['Status']), unsafe_allow_html=True)
            
            if row.get('Remark'):
                st.markdown(f"**Remark:** {row['Remark']}")
        
        # Column 4: Action Buttons
        with col4:
            SchedulePage._render_action_buttons(row)
    
    
    @staticmethod
    def _render_action_buttons(row: pd.Series):
        """Render action buttons based on order status"""
        status = row['Status']
        schedule_row_id = row['ScheduleRowID']
        
        if status == "Planned":
            if st.button("▶️ Start", key=f"start_{schedule_row_id}"):
                SchedulePage._handle_status_action(schedule_row_id, "start")
        
        elif status == "In Progress":
            col_a, col_b = st.columns(2)
            with col_a:
                if st.button("⏸️ Stop", key=f"stop_{schedule_row_id}"):
                    SchedulePage._handle_status_action(schedule_row_id, "stop")
            with col_b:
                if st.button("✅ End", key=f"end_{schedule_row_id}"):
                    SchedulePage._handle_status_action(schedule_row_id, "end")
                elif status == "Partially Completed":
                    col_a, col_b = st.columns(2)
                    with col_a:
                        if st.button("▶️ Resume", key=f"resume_{schedule_row_id}"):
                            SchedulePage._handle_status_action(schedule_row_id, "start")
                    with col_b:
                        if st.button("✅ End", key=f"end_partial_{schedule_row_id}"):
                            SchedulePage._handle_status_action(schedule_row_id, "end")
                elif status == "Completed":
                    st.success("✅ Completed")
                
                elif status == "Blocked":
                    st.error("🚫 Blocked")
    @staticmethod
    def _handle_status_action(schedule_row_id: str, action: str):
        """Handle status change action"""
        df = SessionManager.get('initial_schedule_df')
        updated_df, success, message = ScheduleService.update_order_status(df, schedule_row_id, action)
        
        if success:
            SessionManager.set('initial_schedule_df', updated_df)
            st.success(f"✅ {message}")
            st.rerun()
        else:
            st.error(f"❌ {message}")
    
    @staticmethod
    def _render_detailed_table(df: pd.DataFrame):
        """Render detailed schedule table"""
        display_columns = [
            'Priority', 'Order ID', 'SAP', 'Material Description',
            'Technician Name', 'Status', 'Routing Time (min)',
            'TotalTimeSpent', 'RemainingRoutingTime'
        ]
        
        available_columns = [col for col in display_columns if col in df.columns]
        
        display_df = df[available_columns].copy()
        if 'Priority' in display_df.columns:
            display_df = display_df.sort_values('Priority', na_position='last')
        
        st.dataframe(
            display_df,
            use_container_width=True,
            hide_index=True
        )
