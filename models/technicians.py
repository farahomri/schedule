# technicians.py

import pandas as pd

class Technician:
    def __init__(self, matricule, nom_prenom, niveau_4, niveau_3, niveau_2, niveau_1):
        self.matricule = str(matricule)
        self.nom_prenom = nom_prenom
        self.niveau_4 = niveau_4
        self.niveau_3 = niveau_3
        self.niveau_2 = niveau_2
        self.niveau_1 = niveau_1
        self.classification = self.classify_technician()
        self.expertise_class = self.convert_class_to_numeric(self.classification)

    def classify_technician(self):
        skill_levels = [self.niveau_1, self.niveau_2, self.niveau_3, self.niveau_4]
        max_skill_level = max(skill_levels)

        if max_skill_level == 0:
            return 'Unknown'
        elif max_skill_level == self.niveau_1:
            return 'Basic Knowledge'
        elif max_skill_level == self.niveau_2:
            return 'Above Average'
        elif max_skill_level == self.niveau_3:
            return 'Good'
        else:
            return 'Advanced'

    def convert_class_to_numeric(self, class_name):
        class_map = {
            "Basic Knowledge": 1,
            "Above Average": 2,
            "Good": 3,
            "Advanced": 4
        }
        return class_map.get(class_name, 0)

    def to_dict(self):
        return {
            'Matricule': self.matricule,
            'Nom et prénom': self.nom_prenom,
            'Niveau 4': self.niveau_4,
            'Niveau 3': self.niveau_3,
            'Niveau 2': self.niveau_2,
            'Niveau 1': self.niveau_1,
            'Classification': self.classification,
            'Expertise Class': self.expertise_class
        }

def load_technicians(file_path):
    try:
        technicians = []
        df = pd.read_csv(file_path)
        for _, row in df.iterrows():
            technician = Technician(str(row['Matricule']), row['Nom et prénom'], row['Niveau 4'], row['Niveau 3'], row['Niveau 2'], row['Niveau 1'])
            technicians.append(technician)
        return technicians
    except FileNotFoundError:
        print(f"File '{file_path}' not found.")
        return []

def save_technicians(technicians, file_path):
    try:
        if isinstance(technicians, list):
            df = pd.DataFrame([tech.to_dict() for tech in technicians])
        else:
            raise ValueError("Unsupported data type for saving technicians.")
        df.to_csv(file_path, index=False)
    except Exception as e:
        print(f"Error saving technicians data: {str(e)}")

def add_technician(matricule, nom_prenom, niveau_4, niveau_3, niveau_2, niveau_1, file_path='data/technicians_file.csv'):
    try:
        technicians = load_technicians(file_path)
        new_technician = Technician(str(matricule), nom_prenom, niveau_4, niveau_3, niveau_2, niveau_1)
        technicians.append(new_technician)
        save_technicians(technicians, file_path)
        return True, "Technician added successfully."
    except Exception as e:
        return False, f"Error adding technician: {str(e)}"

def modify_technician(matricule, new_data, file_path='data/technicians_file.csv'):
    try:
        technicians = load_technicians(file_path)
        for tech in technicians:
            if tech.matricule == str(matricule):
                tech.nom_prenom = new_data.get('Nom et prénom', tech.nom_prenom)
                tech.niveau_4 = new_data.get('Niveau 4', tech.niveau_4)
                tech.niveau_3 = new_data.get('Niveau 3', tech.niveau_3)
                tech.niveau_2 = new_data.get('Niveau 2', tech.niveau_2)
                tech.niveau_1 = new_data.get('Niveau 1', tech.niveau_1)
                tech.classification = tech.classify_technician()
                tech.expertise_class = tech.convert_class_to_numeric(tech.classification)
                save_technicians(technicians, file_path)
                return True, "Technician modified successfully."
        return False, f"Technician with matricule '{matricule}' not found."
    except Exception as e:
        return False, f"Error modifying technician: {str(e)}"

def delete_technician(matricule, file_path='data/technicians_file.csv'):
    try:
        technicians = load_technicians(file_path)
        technicians = [tech for tech in technicians if tech.matricule != str(matricule)]
        save_technicians(technicians, file_path)
        return True, "Technician deleted successfully."
    except Exception as e:
        return False, f"Error deleting technician: {str(e)}"
