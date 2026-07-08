import os
import sys

# Add project root to Python path
PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..")
)
sys.path.insert(0, PROJECT_ROOT)

from services.order_service import OrderService


# Pure function — no DB needed
cases = [
    (5.0,   ("Low", 1)),
    (160.0, ("Medium", 2)),
    (320.0, ("High", 3)),
    (480.0, ("Very High", 4)),
    (None,  (None, None)),
]


print("Testing classify:")

for rt, expected in cases:
    result = OrderService.classify(rt)
    status = "OK" if result == expected else f"FAIL (got {result})"
    print(f"  {status}  routing_time={rt}")


# DB call — should return 0 until migration runs
print("\nTesting get_all_products:")

products = OrderService.get_all_products()
print(f"get_all_products: {len(products)} (expected 0 — not migrated yet)")