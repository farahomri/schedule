import os
import sys
from datetime import date

# Add project root to Python path
PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..")
)
sys.path.insert(0, PROJECT_ROOT)

from services.order_service import OrderService, ProductionOrderDTO


# Test validate_orders pure logic
dtos = [
    ProductionOrderDTO(
        None,
        "ORD001",
        1,
        "500123449",
        5.0,
        1,
        5.0,
        1,
        None,
        date.today()
    ),
    ProductionOrderDTO(
        None,
        "ORD002",
        None,
        "999999999",
        None,
        1,
        None,
        None,
        None,
        date.today()
    ),
]

missing = OrderService.validate_orders(dtos)

print(
    f"validate_orders: {missing}  "
    '(expected ["999999999"])'
)


# Test get_late_orders (empty DB)
late = OrderService.get_late_orders(date.today())

print(
    f"get_late_orders: {len(late)} "
    "(expected 0)"
)

print("OrderService 1.5.3 OK")