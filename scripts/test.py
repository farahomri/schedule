import os
import sys

PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..")
)
sys.path.insert(0, PROJECT_ROOT)

from db.database import get_session
from repositories.technician_repository import TechnicianRepository
from db.models import Technician


with get_session() as session:
    all_techs = TechnicianRepository.find_all(session)
    print(f"find_all:          {len(all_techs)} technicians (expected 0 — DB not seeded yet)")

    t = TechnicianRepository.find_by_matricule(session, "9999999")
    print(f"find_by_matricule: {t} (expected None)")

    t2 = TechnicianRepository.find_by_id(session, 999)
    print(f"find_by_id:        {t2} (expected None)")

    tech = Technician(
        matricule="TEST001",
        full_name="Test Technician",
        department="TEST"
    )

    TechnicianRepository.save(session, tech)
    print(f"save:              assigned id={tech.id}")

    found = TechnicianRepository.find_by_matricule(session, "TEST001")
    print(f"find after save:   {found.full_name} (expected Test Technician)")

    session.rollback()
    print("rollback OK — no test data written to DB")