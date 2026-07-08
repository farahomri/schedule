"""
Migrate product catalogue from data/products_classified.csv to the database.

Run once after the baseline migration:
    python scripts/migrate_products.py

Idempotent: skips any SAP number that already exists.
Class and Class Code columns are not migrated — they are computed on the fly.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd

from db.database import get_session
from db.models import Product
from repositories.product_repository import ProductRepository

_CSV = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "products_classified.csv",
)


def main() -> None:
    df = pd.read_csv(_CSV, dtype={"SAP": str})
    df["routing time"] = pd.to_numeric(df["routing time"], errors="coerce").fillna(0)

    print(f"Read {len(df)} rows from products_classified.csv")

    created = skipped = 0

    with get_session() as session:
        for _, row in df.iterrows():
            sap = str(row["SAP"]).strip()

            if ProductRepository.find_by_sap(session, sap):
                skipped += 1
                continue

            product = Product(
                sap_number=sap,
                description=str(row["Material Description"]).strip(),
                routing_time_minutes=float(row["routing time"]),
            )
            ProductRepository.save(session, product)
            created += 1

    print(f"Done. {created} created, {skipped} skipped.")


if __name__ == "__main__":
    main()
