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
    return schedule_df, technicians_df, unscheduled_orders_df # Added unscheduled_orders_df for completeness

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