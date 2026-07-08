import os
import sys
from datetime import date

# Add project root to Python path
PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..")
)
sys.path.insert(0, PROJECT_ROOT)

from services.scheduling_service import SchedulingService
from services.order_service import ProductionOrderDTO
from services.shift_service import WorkingTechnicianDTO


# Minimal mock data — no DB needed for the algorithm itself

orders = [
    ProductionOrderDTO(
        id=1,
        erp_order_id="O1",
        product_id=1,
        sap_number="SAP1",
        routing_time_minutes=200,
        quantity=1,
        effective_time_minutes=200,
        class_code=2,
        priority="A",
        order_date=date.today()
    ),
    ProductionOrderDTO(
        id=2,
        erp_order_id="O2",
        product_id=2,
        sap_number="SAP2",
        routing_time_minutes=100,
        quantity=2,
        effective_time_minutes=200,
        class_code=1,
        priority=None,
        order_date=date.today()
    ),
    ProductionOrderDTO(
        id=3,
        erp_order_id="O3",
        product_id=3,
        sap_number="SAP3",
        routing_time_minutes=400,
        quantity=1,
        effective_time_minutes=400,
        class_code=3,
        priority="Urgent",
        order_date=date.today()
    ),
]


techs = [
    WorkingTechnicianDTO(
        technician_id=1,
        matricule="T01",
        full_name="Tech A",
        expertise_class=3,
        working_time_minutes=450
    ),
    WorkingTechnicianDTO(
        technician_id=2,
        matricule="T02",
        full_name="Tech B",
        expertise_class=2,
        working_time_minutes=450
    ),
]


scheduled, unscheduled = SchedulingService._run_algorithm(
    orders,
    techs
)


print(f"Scheduled: {len(scheduled)}, Unscheduled: {len(unscheduled)}")

for row in scheduled:
    print(
        f"  Order {row.order.erp_order_id} "
        f"(priority={row.order.priority}, "
        f"class={row.order.class_code}, "
        f"time={row.order.effective_time_minutes}min) "
        f"→ {row.tech.matricule} "
        f"(class={row.tech.expertise_class}) "
        f"override={row.is_override}"
    )

print("SchedulingService OK")