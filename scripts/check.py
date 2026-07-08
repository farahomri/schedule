import os
import sys

# Add project root to Python path
PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..")
)
sys.path.insert(0, PROJECT_ROOT)

from services.technician_service import TechnicianService


techs = TechnicianService.get_all()

print(f"Technicians in DB: {len(techs)}")

for t in techs[:3]:
    print(f"  {t.matricule}  {t.full_name}  {t.classification} ({t.expertise_class})")

print("  ...")