import os
import sys
from datetime import date
print("SCRIPT STARTED")
# Add project root to Python path
PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..")
)
sys.path.insert(0, PROJECT_ROOT)

from db.database import get_session
from repositories.schedule_lock_repository import ScheduleLockRepository


test_date = date(2099, 1, 1)  # safe sentinel date

with get_session() as session:
    print(
        "before acquire:",
        ScheduleLockRepository.is_locked(session, test_date)
    )

    ok = ScheduleLockRepository.acquire(
        session,
        test_date,
        user_id=4
    )
    print("first acquire:", ok)  # Expected: True

    ok2 = ScheduleLockRepository.acquire(
        session,
        test_date,
        user_id=1
    )
    print("second acquire (should fail):", ok2)  # Expected: False

    ScheduleLockRepository.release(
        session,
        test_date
    )

    print(
        "after release:",
        ScheduleLockRepository.is_locked(session, test_date)
    )  # Expected: False

    stale = ScheduleLockRepository.cleanup_stale(
        session,
        max_age_minutes=0
    )
    print("cleanup_stale released:", stale)

print("ScheduleLockRepository OK")