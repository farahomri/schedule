# orders.py
import os
import pandas as pd

class_thresholds = [0, 160, 320, 480, float('inf')]
class_labels = ["Low", "Medium", "High", "Very High"]

def classify_order(routing_time):
    if pd.isna(routing_time):
        return None, None
    for i, threshold in enumerate(class_thresholds):
        if routing_time < threshold:
            return class_labels[i-1], i
    return class_labels[-1], len(class_labels)

def load_orders(file_path):
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")
    df = pd.read_csv(file_path, na_values=['NA', 'N/A', 'NaN'])
    return df

def save_orders(df, file_path):
    df.to_csv(file_path, index=False)

def add_order(df, sap, material_description, routing_time, file_path):
    order_class, class_code = classify_order(routing_time)
    new_order = pd.DataFrame([{
        "SAP": sap,
        "Material Description": material_description,
        "routing time": routing_time,
        "Class": order_class,
        "Class Code": class_code
    }])
    df = pd.concat([df, new_order], ignore_index=True)
    save_orders(df, file_path)
    return df

def modify_order(df, sap, material_description, routing_time, file_path):
    order_class, class_code = classify_order(routing_time)

    # Debugging prints
    print(f"Attempting to modify order with SAP: {sap}")
    print(f"Current DataFrame:\n{df}")

    # Convert SAP values to string for comparison
    df['SAP'] = df['SAP'].astype(str)
    sap = str(sap)

    # Check if the SAP exists in the DataFrame
    if sap in df['SAP'].values:
        print(f"SAP {sap} found. Modifying the order.")
        # Update the row with the new values
        df.loc[df['SAP'] == sap, ['Material Description', 'routing time', 'Class', 'Class Code']] = [
            material_description, routing_time, order_class, class_code
        ]
        save_orders(df, file_path)
        print(f"Order with SAP {sap} modified successfully.")
    else:
        print(f"SAP {sap} not found in the DataFrame.")
        raise ValueError(f"SAP {sap} not found in the DataFrame.")

    return df

def delete_order(df, sap, file_path):
    df['SAP'] = df['SAP'].astype(str)
    df = df[df['SAP'] != str(sap)]
    save_orders(df, file_path)
    return df
