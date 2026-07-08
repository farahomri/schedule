import os
import sys
from datetime import date

# Add project root to Python path
PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..")
)
sys.path.insert(0, PROJECT_ROOT)

from services.daily_pool_service import (
    DailyOrderPoolService,
    DailyPoolResult,
    AssignmentDTO
)


result = DailyOrderPoolService.resolve_pool(date.today())

print("carried:", len(result.carried_in_progress))
print("blocked:", len(result.newly_blocked))
print("unblocked:", len(result.unblocked_reassigned))
print("assignable:", len(result.assignable_pool))
print("summary:", result.summary)

print("DailyOrderPoolService OK")