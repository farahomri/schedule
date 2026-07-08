import os
import sys

# Add project root to Python path
PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..")
)
sys.path.insert(0, PROJECT_ROOT)

from services.technician_service import TechnicianService


# Test compute_expertise_class (pure function, no DB needed)
cases = [
    ({1: 0, 2: 0, 3: 0, 4: 0},   ("Unknown", 0)),
    ({1: 10, 2: 3, 3: 4, 4: 0},  ("Basic Knowledge", 1)),
    ({1: 3, 2: 10, 3: 4, 4: 0},  ("Above Average", 2)),
    ({1: 0, 2: 4, 3: 27, 4: 0},  ("Good", 3)),
    ({1: 0, 2: 3, 3: 4, 4: 20},  ("Advanced", 4)),
]


print("Testing compute_expertise_class:")

for skills, expected in cases:
    result = TechnicianService.compute_expertise_class(skills)
    status = "OK" if result == expected else f"FAIL (got {result})"
    print(f"  {status}  skills={skills}")


# Test get_all (DB, should return 0 rows if not seeded)
print("\nTesting get_all:")

techs = TechnicianService.get_all()
print(f"get_all: {len(techs)} technicians (expected 0)")