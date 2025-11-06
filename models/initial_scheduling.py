import os
import pandas as pd
from datetime import datetime
import streamlit as st
import uuid


cumulative_scheduled_orders = set()

def find_missing_sap_numbers(plannification_df, products_classified_df):
    try:
        plannification_materials = plannification_df['Material Number']
        classified_materials = products_classified_df['SAP']
        missing_materials = plannification_materials[~plannification_materials.isin(classified_materials)]

        if missing_materials.empty:
            return None
        else:
            missing_sap_list = missing_materials.tolist()
            st.warning("Please go to the manage orders page and add these SAP numbers with their routing time:")
            for material in missing_sap_list:
                st.write(f"SAP Number: {material}")
            return missing_sap_list

    except KeyError as e:
        st.error(f"Error: Missing column - {e}")
        return None
    except Exception as e:
        st.error(f"An unexpected error occurred: {e}")
        return None

def merge_orders_with_class_code(orders_df, products_classified_path):
    products_classified_df = pd.read_csv(products_classified_path)
    orders_df = orders_df.rename(columns={
        "Material Number": "SAP",
        "Material description": "Material Description",
        "Order": "Order ID"
    })
    if 'Priority' not in orders_df.columns:
        orders_df['Priority'] = None

    merged_df = pd.merge(
        orders_df,
        products_classified_df[['SAP', 'routing time', 'Class', 'Class Code']],
        on='SAP',
        how='left'
    )
    return merged_df

def calculate_working_time(technicians_path, shifts_df):
    technicians = pd.read_csv(technicians_path)
    shifts = shifts_df.copy()
    shifts['Working'] = shifts['Working'].str.strip().str.lower()
    shifts['To another'] = shifts['To another'].str.strip().str.lower()
    working_technicians = shifts[(shifts['Working'] == 'yes') & (shifts['To another'] == 'no')]
    working_technicians['Break'].fillna(0, inplace=True)
    working_technicians['Extra Time'].fillna(0, inplace=True)
    working_technicians['Working Time'] = 480 + 30 - working_technicians['Break'] + working_technicians['Extra Time']
    result = pd.merge(working_technicians, technicians[['Matricule', 'Expertise Class']], on='Matricule', how='left')
    return result
def create_initial_schedule(technicians_df, orders_df):
    """
    Create schedule with THREE-PHASE BALANCING:
    Phase 1: Assign ONE order to each technician (round-robin)
    Phase 2: Continue with priority orders, balanced assignment
    Phase 3: Fill remaining capacity until technicians are full
    """
    
    # ===== PRIORITY HANDLING =====
    priority_mapping = {
        'Urgent': 0, 'urgent': 0, '0': 0,
        'A': 1, 'a': 1,
        'B': 2, 'b': 2,
        'C': 3, 'c': 3
    }
    
    if 'Priority' not in orders_df.columns:
        orders_df['Priority'] = None
    
    # Clean and convert priority
    orders_df['Priority'] = orders_df['Priority'].fillna('None').astype(str).str.strip()
    orders_df['Priority_Num'] = orders_df['Priority'].map(priority_mapping)
    orders_df['Priority_Num'] = orders_df['Priority_Num'].fillna(999).astype(int)
    
    # ✅ CRITICAL: Sort orders by Priority FIRST, then by routing time
    orders_df = orders_df.sort_values(
        by=['Priority_Num', 'routing time'], 
        ascending=[True, False]  # Priority ascending (0=Urgent first), time descending (longer first)
    ).reset_index(drop=True).copy()
    
    print("\n" + "="*80)
    print("ORDER PRIORITY SORTING")
    print("="*80)
    priority_counts = orders_df.groupby('Priority').size()
    for priority, count in priority_counts.items():
        if priority != 'None':
            print(f"Priority {priority}: {count} orders")
    print("="*80)
    
    technicians_df = technicians_df.copy()
    
    schedule = []
    current_date = datetime.now().strftime('%Y-%m-%d')

    # Tracking dictionaries
    technician_initial_time = technicians_df.set_index('Matricule')['Working Time'].to_dict()
    technician_working_time = technician_initial_time.copy()
    technician_names = technicians_df.set_index('Matricule')['Technician Name'].to_dict()
    technician_expertise = technicians_df.set_index('Matricule')['Expertise Class'].to_dict()
    technician_assigned_time = {mat: 0 for mat in technician_working_time.keys()}
    
    scheduled_order_indices = set()

    # ========== PHASE 1: ROUND-ROBIN ==========
    print("\n" + "="*80)
    print("PHASE 1: ROUND-ROBIN - ONE order per technician")
    print("="*80)

    tech_list = list(technician_working_time.keys())
    technicians_assigned_phase1 = set()
    
    # Go through orders and assign ONE to each technician
    for order_idx, order in orders_df.iterrows():
        if order_idx in scheduled_order_indices:
            continue
        
        # Stop Phase 1 when all technicians have at least one order
        if len(technicians_assigned_phase1) >= len(tech_list):
            break
        
        # Try to find a technician who hasn't been assigned yet
        for tech_matricule in tech_list:
            if tech_matricule in technicians_assigned_phase1:
                continue  # This technician already has an order
            
            tech_expertise_level = technician_expertise.get(tech_matricule, 0)
            tech_time_left = technician_working_time[tech_matricule]
            
            can_do_expertise = tech_expertise_level >= order['Class Code']
            has_time = tech_time_left >= order['routing time']
            
            if can_do_expertise and has_time:
                schedule.append({
                    'Day/Date': current_date,
                    'SAP': order['SAP'],
                    'Order ID': order['Order ID'],
                    'Material Description': order['Material Description'],
                    'Routing Time (min)': order['routing time'],
                    'Technician Matricule': tech_matricule,
                    'Technician Name': technician_names.get(tech_matricule, 'Unknown'),
                    'Status': 'Planned',
                    'Remaining Time': order['routing time'],
                    'Remark': '',
                    'Priority': order['Priority'] if order['Priority'] != 'None' else None,
                    'Class Code': order['Class Code'],
                    'StartTime': None,
                    'StopTime': None,
                    'EndTime': None,
                    'RealSpentTime': None,
                    'RemainingRoutingTime': order['routing time']
                })
                
                technician_working_time[tech_matricule] -= order['routing time']
                technician_assigned_time[tech_matricule] += order['routing time']
                scheduled_order_indices.add(order_idx)
                technicians_assigned_phase1.add(tech_matricule)
                
                print(f"✓ Order {order['Order ID']} (Priority: {order.get('Priority', 'None')}, {order['routing time']}min) → {technician_names.get(tech_matricule)}")
                break

    print(f"\nPhase 1 Complete: {len(technicians_assigned_phase1)} technicians assigned, {len(scheduled_order_indices)} orders scheduled")

    # ========== PHASE 2: BALANCED ASSIGNMENT BY PRIORITY & EXPERTISE ==========
    print("\n" + "="*80)
    print("PHASE 2: BALANCED - Assign remaining orders respecting priority")
    print("="*80)

    # Get remaining orders (maintain priority order!)
    remaining_orders_phase2 = orders_df[~orders_df.index.isin(scheduled_order_indices)].copy()
    phase2_count = 0
    
    for order_idx, order in remaining_orders_phase2.iterrows():
        # Find qualified technicians with time
        available_technicians = []
        
        for mat in technician_working_time.keys():
            tech_time_left = technician_working_time[mat]
            tech_expertise_level = technician_expertise.get(mat, 0)
            
            # Check if technician can do this order
            can_do = tech_expertise_level >= order['Class Code']
            has_time = tech_time_left >= order['routing time']
            
            if can_do and has_time:
                available_technicians.append((
                    mat,
                    tech_time_left,
                    technician_assigned_time[mat],
                    tech_expertise_level
                ))
        
        if not available_technicians:
            continue  # Skip this order, will be unscheduled
        
        # Sort by: 1) Least assigned time (balance), 2) Exact expertise match, 3) Most available
        available_technicians.sort(key=lambda x: (
            x[2],  # Least assigned time
            -(x[3] == order['Class Code']),  # Prefer exact match
            -x[1]  # Most available time
        ))
        
        # Assign to best technician
        tech_matricule = available_technicians[0][0]
        
        schedule.append({
            'Day/Date': current_date,
            'SAP': order['SAP'],
            'Order ID': order['Order ID'],
            'Material Description': order['Material Description'],
            'Routing Time (min)': order['routing time'],
            'Technician Matricule': tech_matricule,
            'Technician Name': technician_names.get(tech_matricule, 'Unknown'),
            'Status': 'Planned',
            'Remaining Time': order['routing time'],
            'Remark': '',
            'Priority': order['Priority'] if order['Priority'] != 'None' else None,
            'Class Code': order['Class Code'],
            'StartTime': None,
            'StopTime': None,
            'EndTime': None,
            'RealSpentTime': None,
            'RemainingRoutingTime': order['routing time']
        })
        
        technician_working_time[tech_matricule] -= order['routing time']
        technician_assigned_time[tech_matricule] += order['routing time']
        scheduled_order_indices.add(order_idx)
        phase2_count += 1
        
        utilization = (technician_assigned_time[tech_matricule] / technician_initial_time[tech_matricule]) * 100
        print(f"✓ Order {order['Order ID']} (Priority: {order.get('Priority', 'None')}, {order['routing time']}min) → {technician_names.get(tech_matricule)} [{utilization:.0f}%]")

    print(f"\nPhase 2 Complete: {phase2_count} orders assigned")

    # ========== PHASE 3: FILL CAPACITY ==========
    print("\n" + "="*80)
    print("PHASE 3: CAPACITY FILL - Use remaining technician time")
    print("="*80)

    remaining_orders_phase3 = orders_df[~orders_df.index.isin(scheduled_order_indices)].copy()
    phase3_count = 0
    
    for order_idx, order in remaining_orders_phase3.iterrows():
        # Find ANY technician with time (ignore expertise for capacity filling)
        available_technicians = []
        
        for mat in technician_working_time.keys():
            tech_time_left = technician_working_time[mat]
            
            if tech_time_left >= order['routing time']:
                available_technicians.append((
                    mat,
                    tech_time_left,
                    technician_assigned_time[mat]
                ))
        
        if not available_technicians:
            continue
        
        # Sort by least assigned
        available_technicians.sort(key=lambda x: (x[2], -x[1]))
        tech_matricule = available_technicians[0][0]
        
        schedule.append({
            'Day/Date': current_date,
            'SAP': order['SAP'],
            'Order ID': order['Order ID'],
            'Material Description': order['Material Description'],
            'Routing Time (min)': order['routing time'],
            'Technician Matricule': tech_matricule,
            'Technician Name': technician_names.get(tech_matricule, 'Unknown'),
            'Status': 'Planned',
            'Remaining Time': order['routing time'],
            'Remark': 'Capacity fill - may not match expertise',
            'Priority': order['Priority'] if order['Priority'] != 'None' else None,
            'Class Code': order['Class Code'],
            'StartTime': None,
            'StopTime': None,
            'EndTime': None,
            'RealSpentTime': None,
            'RemainingRoutingTime': order['routing time']
        })
        
        technician_working_time[tech_matricule] -= order['routing time']
        technician_assigned_time[tech_matricule] += order['routing time']
        scheduled_order_indices.add(order_idx)
        phase3_count += 1
        
        utilization = (technician_assigned_time[tech_matricule] / technician_initial_time[tech_matricule]) * 100
        print(f"✓ Order {order['Order ID']} ({order['routing time']}min) → {technician_names.get(tech_matricule)} [{utilization:.0f}%] (Capacity fill)")

    print(f"\nPhase 3 Complete: {phase3_count} orders assigned")

    # ========== FINAL SUMMARY ==========
    print("\n" + "="*80)
    print("FINAL WORKLOAD DISTRIBUTION")
    print("="*80)
    
    total_scheduled = len(scheduled_order_indices)
    total_orders = len(orders_df)
    
    print(f"Total Orders: {total_orders}")
    print(f"Scheduled: {total_scheduled} ({(total_scheduled/total_orders*100):.1f}%)")
    print(f"Unscheduled: {total_orders - total_scheduled}")
    print("-" * 80)
    
    for mat in sorted(technician_assigned_time.keys()):
        name = technician_names.get(mat, 'Unknown')
        assigned = technician_assigned_time[mat]
        total = technician_initial_time[mat]
        utilization = (assigned / total * 100) if total > 0 else 0
        remaining = total - assigned
        
        order_count = len([s for s in schedule if s['Technician Matricule'] == mat])
        
        bar_length = 30
        filled = int((assigned / total) * bar_length) if total > 0 else 0
        bar = "█" * filled + "░" * (bar_length - filled)
        
        status = "FULL" if remaining < 30 else "Available"
        print(f"{name:20} [{bar}] {utilization:5.1f}% ({order_count:2d} orders, {assigned:4.0f}/{total:4.0f}min) {status}")
    
    print("="*80)

    schedule_df = pd.DataFrame(schedule)
    unscheduled_orders_df = orders_df[~orders_df.index.isin(scheduled_order_indices)].copy()
    
    if not schedule_df.empty:
        schedule_df['Priority'] = schedule_df['Priority'].replace('None', None)

    print(f"\n✅ Schedule created: {len(schedule_df)} orders scheduled, {len(unscheduled_orders_df)} unscheduled\n")

    return schedule_df, technicians_df, unscheduled_orders_df

'''def create_initial_schedule(technicians_df, orders_df):
    priority_mapping = {'A': 1, 'B': 2, 'C': 3}
    orders_df['Priority_Num'] = orders_df['Priority'].replace(priority_mapping).infer_objects(copy=False)
    orders_df['Priority_Num'] = pd.to_numeric(orders_df['Priority_Num'], errors='coerce').fillna(999).astype(int)
    
    # Sort orders by Priority (A, B, C) and then by routing time (descending)
    orders_df = orders_df.sort_values(by=['Priority_Num', 'routing time'], ascending=[True, False]).copy() # Use .copy() to avoid SettingWithCopyWarning
    
    # Sort technicians by Working Time (descending)
    technicians_df = technicians_df.sort_values(by='Working Time', ascending=False).copy() # Use .copy()
    
    schedule = []
    current_date = datetime.now().strftime('%Y-%m-%d')

    # Create a mutable copy of technicians' working time for tracking
    # We will decrement this as orders are assigned.
    technician_working_time = technicians_df.set_index('Matricule')['Working Time'].to_dict()
    technician_names = technicians_df.set_index('Matricule')['Technician Name'].to_dict()
    technician_expertise = technicians_df.set_index('Matricule')['Expertise Class'].to_dict()


    # List to keep track of orders that have been successfully scheduled
    scheduled_order_indices = set() 

    # --- Assignment Pass 1: Exact Match Expertise ---
    print("\n--- Assignment Pass 1: Exact Match Expertise ---")
    for order_idx, order in orders_df.iterrows():
        if order_idx in scheduled_order_indices:
            continue # Skip if already scheduled in a previous pass

        assigned = False
        # Sort available technicians by working time descending
        available_technicians = sorted(
            [
                (mat, time_left) for mat, time_left in technician_working_time.items()
                if time_left > 0 # Technician must have time left
                and technician_expertise.get(mat) == order['Class Code'] # Exact expertise match
            ],
            key=lambda item: item[1], # Sort by time left (currently, this is total working time, will be decremented)
            reverse=True # Assign to those with more time first (or other logic you prefer)
        )
        
        for tech_matricule, tech_time_left in available_technicians:
            if tech_time_left >= order['routing time']:
                # Assign the order
                schedule.append({
                    'Day/Date': current_date,
                    'SAP': order['SAP'],
                    'Order ID': order['Order ID'],
                    'Material Description': order['Material Description'],
                    'Routing Time (min)': order['routing time'],
                    'Technician Matricule': tech_matricule,
                    'Technician Name': technician_names.get(tech_matricule, 'Unknown'),
                    'Status': 'Planned',
                    'Remaining Time': order['routing time'],
                    'Remark': '',
                    'Priority': order['Priority'],
                    'StartTime': None,
                    'StopTime': None,
                    'EndTime': None,
                    'RealSpentTime': None,
                    'RemainingRoutingTime': order['routing time']
                })
                
                # Crucially, update the technician's remaining working time
                technician_working_time[tech_matricule] -= order['routing time']
                scheduled_order_indices.add(order_idx)
                assigned = True
                print(f"Assigned Order {order['Order ID']} ({order['Class Code']}) to {technician_names.get(tech_matricule)} (Exact Match). Remaining time: {technician_working_time[tech_matricule]}")
                break # Move to the next order

        if not assigned:
            print(f"Order {order['Order ID']} ({order['Class Code']}) not assigned in Pass 1.")


    # --- Assignment Pass 2: Less Strict Match (e.g., higher expertise can do lower class) ---
    # Assuming 'Class Code' is numeric or can be compared (e.g., 1 < 2 < 3)
    # This pass attempts to assign remaining orders to technicians who have higher or equal expertise,
    # and also have remaining time.
    print("\n--- Assignment Pass 2: Less Strict Match (Higher Expertise can do Lower Class) ---")
    remaining_orders_pass2 = orders_df[~orders_df.index.isin(scheduled_order_indices)].copy()
    
    for order_idx, order in remaining_orders_pass2.iterrows():
        assigned = False
        available_technicians = sorted(
            [
                (mat, time_left) for mat, time_left in technician_working_time.items()
                if time_left > 0
                and technician_expertise.get(mat) >= order['Class Code'] # Technician's expertise is higher or equal
            ],
            key=lambda item: item[1],
            reverse=True
        )

        for tech_matricule, tech_time_left in available_technicians:
            if tech_time_left >= order['routing time']:
                schedule.append({
                    'Day/Date': current_date,
                    'SAP': order['SAP'],
                    'Order ID': order['Order ID'],
                    'Material Description': order['Material Description'],
                    'Routing Time (min)': order['routing time'],
                    'Technician Matricule': tech_matricule,
                    'Technician Name': technician_names.get(tech_matricule, 'Unknown'),
                    'Status': 'Planned',
                    'Remaining Time': order['routing time'],
                    'Remark': '',
                    'Priority': order['Priority'],
                    'StartTime': None,
                    'StopTime': None,
                    'EndTime': None,
                    'RealSpentTime': None,
                    'RemainingRoutingTime': order['routing time']
                })
                technician_working_time[tech_matricule] -= order['routing time']
                scheduled_order_indices.add(order_idx)
                assigned = True
                print(f"Assigned Order {order['Order ID']} ({order['Class Code']}) to {technician_names.get(tech_matricule)} (Less Strict Match). Remaining time: {technician_working_time[tech_matricule]}")
                break # Move to the next order
        
        if not assigned:
            print(f"Order {order['Order ID']} ({order['Class Code']}) not assigned in Pass 2.")


    # --- Assignment Pass 3: General Assignment (Any technician with time) ---
    # This pass attempts to assign any remaining orders to any technician with time left,
    # regardless of expertise, if Pass 1 and 2 failed. You might want to remove this pass
    # or make it more sophisticated if expertise is a strict requirement.
    print("\n--- Assignment Pass 3: General Assignment (Any Technician with Time) ---")
    remaining_orders_pass3 = orders_df[~orders_df.index.isin(scheduled_order_indices)].copy()

    for order_idx, order in remaining_orders_pass3.iterrows():
        assigned = False
        available_technicians = sorted(
            [
                (mat, time_left) for mat, time_left in technician_working_time.items()
                if time_left > 0 # Technician must have time left
            ],
            key=lambda item: item[1],
            reverse=True
        )

        for tech_matricule, tech_time_left in available_technicians:
            if tech_time_left >= order['routing time']:
                schedule.append({
                    'Day/Date': current_date,
                    'SAP': order['SAP'],
                    'Order ID': order['Order ID'],
                    'Material Description': order['Material Description'],
                    'Routing Time (min)': order['routing time'],
                    'Technician Matricule': tech_matricule,
                    'Technician Name': technician_names.get(tech_matricule, 'Unknown'),
                    'Status': 'Planned',
                    'Remaining Time': order['routing time'],
                    'Remark': '',
                    'Priority': order['Priority'],
                    'StartTime': None,
                    'StopTime': None,
                    'EndTime': None,
                    'RealSpentTime': None,
                    'RemainingRoutingTime': order['routing time']
                })
                technician_working_time[tech_matricule] -= order['routing time']
                scheduled_order_indices.add(order_idx)
                assigned = True
                print(f"Assigned Order {order['Order ID']} ({order['Class Code']}) to {technician_names.get(tech_matricule)} (General Match). Remaining time: {technician_working_time[tech_matricule]}")
                break # Move to the next order
        
        if not assigned:
            print(f"Order {order['Order ID']} ({order['Class Code']}) not assigned in Pass 3.")


    schedule_df = pd.DataFrame(schedule)
    
    # You might want to return a list of unscheduled orders as well
    unscheduled_orders_df = orders_df[~orders_df.index.isin(scheduled_order_indices)].copy()

    # The technicians_df here will be the original one. If you want the updated working times,
    # you'd need to create a new technicians_df from the technician_working_time dict.
    # For now, let's return the original technicians_df as your function signature expects.
    return schedule_df, technicians_df, unscheduled_orders_df # Added unscheduled_orders_df for completeness'''

def remove_scheduled_orders(schedule_df, unscheduled_orders):
    scheduled_orders = set(schedule_df['SAP'])
    unscheduled_orders = unscheduled_orders[~unscheduled_orders['SAP'].isin(scheduled_orders)]
    return unscheduled_orders

def reassign_blocked_order(schedule_df, unscheduled_orders_df, blocked_sap, technician_id, time_spent, block_reason):
    blocked_sap = str(blocked_sap)
    technician_id = str(technician_id)
    blocked_order_index = schedule_df[(schedule_df['SAP'].astype(str) == blocked_sap) & (schedule_df['Technician Matricule'].astype(str) == technician_id)].index

    if not blocked_order_index.empty:
        blocked_order_index = blocked_order_index[0]
        schedule_df.at[blocked_order_index, 'Status'] = 'Blocked'
        schedule_df.at[blocked_order_index, 'Remark'] = f'Blocked due to: {block_reason}. Technician spent {time_spent} minutes before blocking'
        schedule_df.at[blocked_order_index, 'Remaining Time'] = schedule_df.at[blocked_order_index, 'Routing Time (min)'] - time_spent

    new_assignment = None
    next_order = schedule_df[(schedule_df['Technician Matricule'].astype(str) == technician_id) & (schedule_df['Status'] != 'Blocked')]
    if not next_order.empty:
        next_order = next_order.iloc[0]
    else:
        if unscheduled_orders_df.empty:
            raise ValueError("No unscheduled orders available to reassign.")
        small_order = unscheduled_orders_df.iloc[0]
        unscheduled_orders_df = unscheduled_orders_df.iloc[1:]
        new_assignment = small_order
        routing_time = small_order['routing time']
        difference = routing_time - time_spent
        status = 'Completed' if difference >= 0 else 'In Progress'
        remaining_time = 0 if difference >= 0 else abs(difference)
        technician_name = schedule_df.loc[schedule_df['Technician Matricule'].astype(str) == technician_id, 'Technician Name'].iloc[0]
        new_row = pd.DataFrame([{
            'Day/Date': '',
            'SAP': small_order['SAP'],
            'Order ID': small_order['Order ID'],
            'Material Description': small_order['Material Description'],
            'Routing Time (min)': routing_time,
            'Technician Matricule': technician_id,
            'Technician Name': technician_name,
            'Status': status,
            'Remaining Time': remaining_time,
            'Remark': f'Reassigned from blocked order {blocked_sap}',
            'Priority': small_order.get('Priority', None),
            'StartTime': None,
            'StopTime': None,
            'EndTime': None,
            'RealSpentTime': None,
            'RemainingRoutingTime': routing_time
        }])
        schedule_df = pd.concat([schedule_df, new_row], ignore_index=True)
    return schedule_df, unscheduled_orders_df, new_assignment