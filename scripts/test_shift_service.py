import os
import sys
from datetime import date

# Add project root to Python path
PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..")
)
sys.path.insert(0, PROJECT_ROOT)

from services.shift_service import ShiftService, _working_time


# Formula check (V2: 480 - break + extra)
assert _working_time(30, 0) == 450, f"Expected 450, got {_working_time(30, 0)}"
assert _working_time(0, 0) == 480, f"Expected 480, got {_working_time(0, 0)}"
assert _working_time(30, 60) == 510, f"Expected 510, got {_working_time(30, 60)}"

print("Formula: OK")


# DB call (no shifts yet)
techs = ShiftService.get_working_technicians(date.today())

print(
    f"get_working_technicians: {len(techs)} "
    "(expected 0 — no shifts in DB yet)"
)

print("ShiftService OK")