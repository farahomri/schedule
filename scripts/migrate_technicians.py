"""
Migrate technician data from data/technicians_file.csv to the database.

Run once after the baseline migration:
    python scripts/migrate_technicians.py

Idempotent: skips any technician whose matricule already exists.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd

from db.database import get_session
from db.models import Technician, TechnicianSkill
from repositories.technician_repository import TechnicianRepository

_CSV = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "technicians_file.csv",
)


def main() -> None:
    df = pd.read_csv(_CSV, encoding="utf-8")

    # Skill columns may be read as floats; normalise to int.
    for col in ["Niveau 4", "Niveau 3", "Niveau 2", "Niveau 1"]:
        df[col] = df[col].fillna(0).astype(int)

    print(f"Read {len(df)} rows from technicians_file.csv")

    created = skipped = 0

    with get_session() as session:
        for _, row in df.iterrows():
            matricule = str(row["Matricule"]).strip()

            if TechnicianRepository.find_by_matricule(session, matricule):
                print(f"  SKIP    {matricule}")
                skipped += 1
                continue

            tech = Technician(
                matricule=matricule,
                full_name=str(row["Nom et prénom"]).strip(),
                department=None,
            )
            tech.skills = [
                TechnicianSkill(skill_level=4, score=int(row["Niveau 4"])),
                TechnicianSkill(skill_level=3, score=int(row["Niveau 3"])),
                TechnicianSkill(skill_level=2, score=int(row["Niveau 2"])),
                TechnicianSkill(skill_level=1, score=int(row["Niveau 1"])),
            ]
            TechnicianRepository.save(session, tech)
            print(f"  CREATED {matricule}  {tech.full_name}")
            created += 1

    print(f"\nDone. {created} created, {skipped} skipped.")


if __name__ == "__main__":
    main()
