import pandas as pd

class Reclamation:
    def __init__(self, Date, Ordre, SAP, Description, Qty, Reclamation, Remarque, technicien, decision, QS):
        self.Date = Date
        self.Ordre = Ordre
        self.SAP = SAP
        self.Description = Description
        self.Qty = Qty
        self.Reclamation = Reclamation
        self.Remarque = Remarque
        self.technicien = technicien
        self.decision = decision
        self.QS = QS

    def to_dict(self):
        return {
            "Date": self.Date,
            "Ordre": self.Ordre,
            "SAP": self.SAP,
            "Description": self.Description,
            "Qty": self.Qty,
            "Reclamation": self.Reclamation,
            "Remarque": self.Remarque,
            "technicien": self.technicien,
            "decision": self.decision,
            "QS": self.QS,
        }

def load_reclamations(file_path):
    try:
        df = pd.read_excel(file_path)
        df.columns = df.columns.str.strip()  # Remove any leading or trailing spaces from column names
        print("Column names:", df.columns.tolist())  # Debugging: Print column names
        reclamations = [Reclamation(**row) for index, row in df.iterrows()]
        return reclamations
    except FileNotFoundError:
        return []


def save_reclamations(file_path, reclamations):
    df = pd.DataFrame([rec.to_dict() for rec in reclamations])
    df.to_excel(file_path, index=False)

def add_reclamation(date, ordre, sap, description, qty, reclamation, remarque, technicien, decision, qs):
    reclamations = load_reclamations('../data/reclamations_file.xlsx')  # Adjusted path
    new_reclamation = Reclamation(date, ordre, sap, description, qty, reclamation, remarque, technicien, decision, qs)
    reclamations.append(new_reclamation)
    save_reclamations('../data/reclamations_file.xlsx', reclamations)
    return True, "Reclamation added successfully."

def modify_reclamation(ordre, new_data):
    reclamations = load_reclamations('../data/reclamations_file.xlsx')  # Adjusted path
    for rec in reclamations:
        if rec.ordre == ordre:
            rec.date = new_data.get('Date', rec.date)
            rec.sap = new_data.get('SAP', rec.sap)
            rec.description = new_data.get('Description', rec.description)
            rec.qty = new_data.get('Qty', rec.qty)
            rec.reclamation = new_data.get('Reclamation', rec.reclamation)
            rec.remarque = new_data.get('Remarque', rec.remarque)
            rec.technicien = new_data.get('Technicien', rec.technicien)
            rec.decision = new_data.get('Decision', rec.decision)
            rec.qs = new_data.get('QS', rec.qs)
            save_reclamations('../data/reclamations_file.xlsx', reclamations)
            return True, "Reclamation modified successfully."
    return False, "Reclamation not found."

def delete_reclamation(ordre):
    reclamations = load_reclamations('../data/reclamations_file.xlsx')  # Adjusted path
    reclamations = [rec for rec in reclamations if rec.ordre != ordre]
    save_reclamations('../data/reclamations_file.xlsx', reclamations)
    return True, "Reclamation deleted successfully."