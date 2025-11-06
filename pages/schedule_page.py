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
        
        # Editable schedule section
        SchedulePage._render_edit_section(df)
        
        st.markdown("---")
        
        # Filters
        filtered_df = SchedulePage._render_filters(df)
        
        # Statistics
        SchedulePage._render_statistics(df)
        
        st.markdown("---")
        
        # Orders display
        SchedulePage._render_orders(filtered_df)
        
        # Detailed table
        if st.checkbox("📊 Show Detailed Schedule Table"):
            SchedulePage._render_detailed_table(df)
        
        # ✅ NEW: Unscheduled Orders Section
        st.markdown("---")
        SchedulePage._render_unscheduled_orders()
    '''
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
            SchedulePage._render_detailed_table(df)'''
    
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
        """
        Priority change with SMART urgent logic:
        - Only show Planned orders (not In Progress/Completed)
        - For Urgent: Show technicians with REAL available time
        - Real time = Total - (In Progress orders actual time)
        """
        st.markdown("**Change Order Priority**")
        st.info("💡 Only orders that haven't started can be reprioritized. Select 'Urgent' for manual assignment.")
        
        # ✅ FILTER: Only show PLANNED orders
        planned_only = planned_orders[planned_orders['Status'] == 'Planned'].copy()
        
        if planned_only.empty:
            st.warning("⚠️ No Planned orders available. All orders are either in progress or completed.")
            return
        
        col1, col2 = st.columns(2)
        
        with col1:
            order_options = {
                f"{row['Order ID']} - {row.get('Priority', 'None')} - {row['Technician Name']}": row['ScheduleRowID']
                for _, row in planned_only.iterrows()
            }
            
            selected_order = st.selectbox(
                "Select Order (Planned Only)",
                list(order_options.keys()),
                key="priority_order_select"
            )
            selected_order_id = order_options[selected_order]
            
            df = SessionManager.get('initial_schedule_df')
            selected_order_row = df[df['ScheduleRowID'] == selected_order_id].iloc[0]
        
        with col2:
            new_priority = st.selectbox(
                "New Priority",
                options=['Urgent', '0', 'A', 'B', 'C', 'None'],
                index=0,
                key="new_priority_select",
                help="Urgent/0 = Manual assignment with REAL-TIME availability"
            )
        
        # ✅ SMART URGENT: Show REAL available time (not counting Planned orders)
        selected_technician = None
        if new_priority in ['Urgent', '0']:
            st.markdown("---")
            st.markdown("### 🚨 URGENT Priority - Real-Time Technician Availability")
            st.info("ℹ️ Available time shows ACTUAL free time (only counting In Progress orders)")
            
            working_techs = SessionManager.get('working_technicians')
            schedule_df = SessionManager.get('initial_schedule_df')
            
            if working_techs is not None and schedule_df is not None:
                if isinstance(working_techs, pd.DataFrame):
                    tech_list = working_techs.to_dict('records')
                else:
                    tech_list = working_techs
                
                tech_availability = []
                for tech in tech_list:
                    matricule = tech['Matricule']
                    name = tech['Technician Name']
                    total_time = tech.get('Working Time', 0)
                    expertise = tech.get('Expertise Class', 0)
                    
                    # ✅ CALCULATE REAL AVAILABLE TIME
                    # Only count orders that are IN PROGRESS (actually being worked on)
                    in_progress_orders = schedule_df[
                        (schedule_df['Technician Matricule'] == matricule) & 
                        (schedule_df['Status'] == 'In Progress')
                    ]
                    
                    # For in-progress orders, use actual time spent (or routing time if not tracked)
                    actual_used_time = 0
                    for _, order in in_progress_orders.iterrows():
                        # Use TotalTimeSpent if available, otherwise use remaining time estimate
                        if pd.notna(order.get('TotalTimeSpent')) and order['TotalTimeSpent'] > 0:
                            actual_used_time += order['TotalTimeSpent']
                        else:
                            # Estimate: routing time - remaining time
                            actual_used_time += order['Routing Time (min)'] - order.get('RemainingRoutingTime', 0)
                    
                    # Real available time = Total time - Actual used time
                    real_available = total_time - actual_used_time
                    
                    # Count Planned orders (not counting their time, just for info)
                    planned_count = len(schedule_df[
                        (schedule_df['Technician Matricule'] == matricule) & 
                        (schedule_df['Status'] == 'Planned')
                    ])
                    
                    # Count In Progress orders
                    in_progress_count = len(in_progress_orders)
                    
                    # Determine status based on REAL availability
                    if real_available >= selected_order_row['Routing Time (min)']:
                        status = "🟢 Available"
                    elif real_available > 0:
                        status = "🟡 Limited"
                    else:
                        status = "🔴 Busy"
                    
                    tech_availability.append({
                        'Matricule': matricule,
                        'Name': name,
                        'Expertise': f"Level {expertise}",
                        'Status': status,
                        'Real Available': f"{real_available:.0f} min",
                        'In Progress': f"{in_progress_count} orders",
                        'Planned': f"{planned_count} orders",
                        'Total Time': f"{total_time:.0f} min",
                        'real_available_num': real_available,
                        'expertise_num': expertise
                    })
                
                # Sort by most available time
                tech_availability.sort(key=lambda x: x['real_available_num'], reverse=True)
                
                st.markdown("#### 👷 Technician Real-Time Availability")
                
                display_df = pd.DataFrame([
                    {
                        'Technician': t['Name'],
                        'Expertise': t['Expertise'],
                        'Status': t['Status'],
                        'Real Available': t['Real Available'],
                        'In Progress': t['In Progress'],
                        'Planned': t['Planned'],
                        'Total Capacity': t['Total Time']
                    }
                    for t in tech_availability
                ])
                
                st.dataframe(display_df, use_container_width=True, hide_index=True)
                
                st.markdown("#### 🎯 Select Technician")
                
                # Only show technicians with some available time
                available_techs = [t for t in tech_availability if t['real_available_num'] > 0]
                
                if not available_techs:
                    st.error("❌ No technicians have available time right now. All are working on current orders.")
                    return
                
                tech_options = {
                    f"{t['Name']} - {t['Status']} - {t['Real Available']} free ({t['In Progress']} working, {t['Planned']} planned)": 
                    (t['Matricule'], t['Name'], t['expertise_num'])
                    for t in available_techs
                }
                
                selected_tech_display = st.selectbox(
                    "Choose Technician",
                    list(tech_options.keys()),
                    key="urgent_tech_select"
                )
                selected_technician = tech_options[selected_tech_display]
                
                st.success(f"✅ Will assign to: **{selected_technician[1]}** (Level {selected_technician[2]})")
            
            else:
                st.error("❌ Data not available")
                return
        
        # Update button
        button_text = "🚨 Set URGENT & Assign" if new_priority in ['Urgent', '0'] else "🔢 Update Priority"
        
        if st.button(button_text, key="btn_update_priority", type="primary", use_container_width=True):
            df = SessionManager.get('initial_schedule_df')
            
            row_mask = df['ScheduleRowID'] == selected_order_id
            if not row_mask.any():
                st.error("❌ Order not found")
                return
            
            row_idx = df[row_mask].index[0]
            
            # Double-check status
            if df.at[row_idx, "Status"] != "Planned":
                st.error("❌ Can only change priority for Planned orders")
                return
            
            old_priority = df.at[row_idx, "Priority"]
            old_technician = df.at[row_idx, "Technician Name"]
            
            # Update priority
            if new_priority in ['Urgent', '0']:
                new_priority_value = 'Urgent'
            elif new_priority == 'None':
                new_priority_value = None
            else:
                new_priority_value = new_priority
            
            df.at[row_idx, "Priority"] = new_priority_value
            
            # Update technician if urgent
            if new_priority in ['Urgent', '0'] and selected_technician:
                df.at[row_idx, "Technician Matricule"] = selected_technician[0]
                df.at[row_idx, "Technician Name"] = selected_technician[1]
            
            # Re-sort
            priority_mapping = {'Urgent': 0, '0': 0, 'A': 1, 'B': 2, 'C': 3}
            df['_temp_priority'] = df['Priority'].map(priority_mapping).fillna(999)
            df = df.sort_values(
                by=['_temp_priority', 'Routing Time (min)'], 
                ascending=[True, False]
            ).reset_index(drop=True)
            df['SequenceNumber'] = range(1, len(df) + 1)
            df = df.drop('_temp_priority', axis=1)
            
            SessionManager.set('initial_schedule_df', df)
            
            st.success(f"✅ Priority: {old_priority} → {new_priority_value}")
            
            if new_priority in ['Urgent', '0'] and selected_technician and old_technician != selected_technician[1]:
                st.success(f"👤 Reassigned: {old_technician} → {selected_technician[1]}")
            
            new_pos = df[df['ScheduleRowID'] == selected_order_id]['SequenceNumber'].values[0]
            st.success(f"📊 Position: #{new_pos}")
            
            if new_priority in ['Urgent', '0']:
                st.balloons()
            
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
    @staticmethod
    def _render_unscheduled_orders():
        """Render unscheduled orders with detailed technician availability like urgent priority"""
        st.markdown("### 📦 Unscheduled Orders")
        
        unscheduled_df = SessionManager.get('unscheduled_orders_df')
        
        if unscheduled_df is None or unscheduled_df.empty:
            st.success("✅ All orders have been scheduled!")
            return
        
        st.warning(f"⚠️ {len(unscheduled_df)} orders could not be automatically scheduled")
        
        with st.expander("📋 View & Manually Assign Unscheduled Orders", expanded=True):
            st.markdown("**Orders needing manual assignment:**")
            
            # Display unscheduled orders
            display_cols = ['Order ID', 'SAP', 'Material Description', 'routing time', 'Class', 'Class Code', 'Priority']
            available_cols = [col for col in display_cols if col in unscheduled_df.columns]
            st.dataframe(unscheduled_df[available_cols], use_container_width=True, hide_index=True)
            
            st.markdown("---")
            st.markdown("#### 🎯 Manually Assign Order")
            
            col1, col2 = st.columns([1, 1])
            
            with col1:
                st.markdown("**1️⃣ Select Order**")
                
                # Select unscheduled order
                order_options = {
                    f"{row['Order ID']} - {row['SAP']} ({row['routing time']}min, Level {row.get('Class Code', '?')})": idx
                    for idx, row in unscheduled_df.iterrows()
                }
                
                selected_order_display = st.selectbox(
                    "Choose Order",
                    list(order_options.keys()),
                    key="unscheduled_order_select"
                )
                selected_order_idx = order_options[selected_order_display]
                selected_order = unscheduled_df.loc[selected_order_idx]
                
                # Show order details
                st.info(f"""
                **Order Details:**
                - Routing Time: {selected_order['routing time']} min
                - Complexity: Level {selected_order.get('Class Code', '?')}
                - Priority: {selected_order.get('Priority', 'None')}
                """)
            
            with col2:
                st.markdown("**2️⃣ View Technician Availability**")
                
                # Get working technicians with REAL-TIME availability
                working_techs = SessionManager.get('working_technicians')
                schedule_df = SessionManager.get('initial_schedule_df')
                
                if working_techs is None or schedule_df is None:
                    st.error("❌ Technician data not available")
                    return
                
                # Convert to list
                if isinstance(working_techs, pd.DataFrame):
                    tech_list = working_techs.to_dict('records')
                else:
                    tech_list = working_techs
            
            # Build detailed technician availability table
            st.markdown("---")
            st.markdown("#### 👷 Technician Real-Time Availability")
            st.info("💡 Available time shows REAL free time (Total - Planned orders)")
            
            tech_availability = []
            for tech in tech_list:
                matricule = tech['Matricule']
                name = tech['Technician Name']
                total_time = tech.get('Working Time', 0)
                expertise = tech.get('Expertise Class', 0)
                
                # Calculate allocated time (ONLY Planned orders)
                allocated = schedule_df[
                    (schedule_df['Technician Matricule'] == matricule) & 
                    (schedule_df['Status'] == 'Planned')
                ]['Routing Time (min)'].sum()
                
                # Real available time
                available = total_time - allocated
                utilization = (allocated / total_time * 100) if total_time > 0 else 0
                
                # Count orders
                planned_count = len(schedule_df[
                    (schedule_df['Technician Matricule'] == matricule) & 
                    (schedule_df['Status'] == 'Planned')
                ])
                
                in_progress_count = len(schedule_df[
                    (schedule_df['Technician Matricule'] == matricule) & 
                    (schedule_df['Status'] == 'In Progress')
                ])
                
                # Check qualification
                order_class = selected_order.get('Class Code', 1)
                qualified = "✅ Yes" if expertise >= order_class else "❌ No"
                
                # Check if has enough time for this order
                can_fit = available >= selected_order['routing time']
                
                # Determine status
                if can_fit and expertise >= order_class:
                    status = "🟢 Available & Qualified"
                elif can_fit:
                    status = "🟡 Available (Low Expertise)"
                elif available > 0:
                    status = "🟠 Insufficient Time"
                else:
                    status = "🔴 Fully Booked"
                
                tech_availability.append({
                    'Matricule': matricule,
                    'Name': name,
                    'Expertise': f"Level {expertise}",
                    'Qualified': qualified,
                    'Status': status,
                    'Available Time': f"{available:.0f} min",
                    'Utilization': f"{utilization:.0f}%",
                    'Planned Orders': planned_count,
                    'In Progress': in_progress_count,
                    'Can Fit Order': "✅ Yes" if can_fit else "❌ No",
                    'available_num': available,
                    'expertise_num': expertise,
                    'can_fit': can_fit
                })
            
            # Sort by: 1) Can fit order, 2) Qualified, 3) Most available
            tech_availability.sort(key=lambda x: (-x['can_fit'], -(x['expertise_num'] >= selected_order.get('Class Code', 1)), -x['available_num']))
            
            # Display table
            display_df = pd.DataFrame([
                {
                    'Technician': t['Name'],
                    'Expertise': t['Expertise'],
                    'Qualified': t['Qualified'],
                    'Status': t['Status'],
                    'Available': t['Available Time'],
                    'Utilization': t['Utilization'],
                    'Planned': t['Planned Orders'],
                    'In Progress': t['In Progress'],
                    'Can Fit': t['Can Fit Order']
                }
                for t in tech_availability
            ])
            
            st.dataframe(display_df, use_container_width=True, hide_index=True)
            
            # Technician selection
            st.markdown("#### 🎯 Select Technician to Assign")
            
            # Filter to technicians who can fit the order
            can_fit_techs = [t for t in tech_availability if t['can_fit']]
            
            if not can_fit_techs:
                st.error("❌ No technicians have enough available time for this order")
                st.info(f"💡 Order requires {selected_order['routing time']} minutes. All technicians are fully allocated.")
                return
            
            # Create options
            tech_options = {}
            for t in can_fit_techs:
                display_text = f"{t['Name']} - {t['Status']} - {t['Available Time']} free ({t['Expertise']})"
                tech_options[display_text] = (t['Matricule'], t['Name'], t['expertise_num'])
            
            selected_tech_display = st.selectbox(
                "Choose Technician",
                list(tech_options.keys()),
                key="unscheduled_tech_select",
                help="Showing only technicians with sufficient available time"
            )
            selected_tech = tech_options[selected_tech_display]
            
            # Show selection summary
            col_a, col_b = st.columns(2)
            with col_a:
                st.metric("Order Requires", f"Level {selected_order.get('Class Code', 1)}")
            with col_b:
                st.metric("Selected Tech Level", f"Level {selected_tech[2]}")
            
            # Qualification warning
            if selected_tech[2] < selected_order.get('Class Code', 1):
                st.warning(f"⚠️ Selected technician (Level {selected_tech[2]}) may not be fully qualified for this order (requires Level {selected_order.get('Class Code', 1)})")
            else:
                st.success(f"✅ Selected technician is qualified for this order")
            
            # Assign button
            if st.button("✅ Assign Order to Selected Technician", type="primary", use_container_width=True, key="btn_assign_unscheduled"):
                import uuid
                
                # Add order to schedule
                schedule_df = SessionManager.get('initial_schedule_df')
                unscheduled_df = SessionManager.get('unscheduled_orders_df')
                
                new_order = {
                    'Day/Date': datetime.now().strftime('%Y-%m-%d'),
                    'SAP': selected_order['SAP'],
                    'Order ID': selected_order['Order ID'],
                    'Material Description': selected_order['Material Description'],
                    'Routing Time (min)': selected_order['routing time'],
                    'Technician Matricule': selected_tech[0],
                    'Technician Name': selected_tech[1],
                    'Status': 'Planned',
                    'Remaining Time': selected_order['routing time'],
                    'Remark': 'Manually assigned from unscheduled orders',
                    'Priority': selected_order.get('Priority', None),
                    'Class Code': selected_order.get('Class Code', 1),
                    'ScheduleRowID': str(uuid.uuid4()),
                    'SequenceNumber': len(schedule_df) + 1,
                    'FirstStartTime': None,
                    'EndTime': None,
                    'TotalTimeSpent': 0.0,
                    'RemainingRoutingTime': selected_order['routing time'],
                    'WorkSessions': '[]'
                }
                
                # Add to schedule
                schedule_df = pd.concat([schedule_df, pd.DataFrame([new_order])], ignore_index=True)
                
                # Remove from unscheduled
                unscheduled_df = unscheduled_df.drop(selected_order_idx)
                
                # Update session
                SessionManager.set('initial_schedule_df', schedule_df)
                SessionManager.set('unscheduled_orders_df', unscheduled_df)
                
                st.success(f"✅ Order {selected_order['Order ID']} assigned to {selected_tech[1]}")
                st.balloons()
                st.rerun()

