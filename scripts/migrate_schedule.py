"""
Task 1.6.3 — Migrate current_schedule.csv → schedule_assignments table.

For each CSV row the script:
  1. Resolves the Product by SAP number.
  2. Finds or creates a ProductionOrder (erp_order_id + order_date).
  3. Resolves the Technician by matricule.
  4. Inserts a ScheduleAssignment (skipped if schedule_row_id already exists).

Run from the project root:
    python scripts/migrate_schedule.py
"""

import os
import sys
import uuid
from datetime import date, datetime

import pandas as pd

# ── Bootstrap path so local packages resolve ─────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.database import get_session
from db.models import ProductionOrder, ScheduleAssignment, Technician
from repositories.product_repository import ProductRepository
from repositories.technician_repository import TechnicianRepository

CSV_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "current_schedule.csv")

# Status values valid in the new schema
VALID_STATUSES = {'Planned', 'In Progress', 'Partially Completed', 'Completed', 'Blocked'}


def _parse_date(value: str) -> date:
    for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y'):
        try:
            return datetime.strptime(str(value).strip(), fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Unrecognised date format: {value!r}")


def main():
    df = pd.read_csv(CSV_PATH, dtype=str)
    df.fillna('', inplace=True)

    print(f"Rows in CSV: {len(df)}")

    created_orders = 0
    skipped_orders = 0
    created_assignments = 0
    skipped_assignments = 0
    errors = []

    with get_session() as session:
        # Pre-load lookup maps
        all_products = ProductRepository.find_all(session)
        product_map = {p.sap_number: p for p in all_products}

        all_techs = TechnicianRepository.find_all(session)
        tech_map = {t.matricule: t for t in all_techs}

        # Pre-load existing schedule_row_ids to skip duplicates
        existing_uuids = {
            str(row[0])
            for row in session.query(ScheduleAssignment.schedule_row_id).all()
        }

        for idx, row in df.iterrows():
            line = idx + 2  # 1-indexed + header row

            # ── Parse required fields ─────────────────────────────────────
            sap = row.get('SAP', '').strip()
            erp_order_id = row.get('Order ID', '').strip()
            matricule = row.get('Technician Matricule', '').strip()
            date_str = row.get('Day/Date', '').strip()
            schedule_row_id_str = row.get('ScheduleRowID', '').strip()

            if not all([sap, erp_order_id, matricule, date_str]):
                errors.append(f"Row {line}: missing required field(s) — skipped")
                continue

            # ── Resolve date ──────────────────────────────────────────────
            try:
                order_date = _parse_date(date_str)
            except ValueError as e:
                errors.append(f"Row {line}: {e}")
                continue

            # ── Resolve UUID ──────────────────────────────────────────────
            try:
                row_uuid = uuid.UUID(schedule_row_id_str) if schedule_row_id_str else uuid.uuid4()
            except ValueError:
                row_uuid = uuid.uuid4()

            if str(row_uuid) in existing_uuids:
                skipped_assignments += 1
                continue

            # ── Resolve product ───────────────────────────────────────────
            product = product_map.get(sap)
            if not product:
                errors.append(f"Row {line}: SAP '{sap}' not in products table — skipped")
                continue

            # ── Resolve technician ────────────────────────────────────────
            tech = tech_map.get(matricule)
            if not tech:
                errors.append(f"Row {line}: matricule '{matricule}' not in technicians table — skipped")
                continue

            # ── Find or create ProductionOrder ────────────────────────────
            production_order = (
                session.query(ProductionOrder)
                .filter_by(erp_order_id=erp_order_id, order_date=order_date)
                .first()
            )
            if not production_order:
                try:
                    priority_raw = row.get('Priority', '').strip()
                    priority = priority_raw if priority_raw and priority_raw not in ('0', 'nan', '') else None
                    production_order = ProductionOrder(
                        erp_order_id=erp_order_id,
                        product_id=product.id,
                        priority=priority,
                        order_date=order_date,
                        quantity=1,
                    )
                    session.add(production_order)
                    session.flush()
                    created_orders += 1
                except Exception as e:
                    errors.append(f"Row {line}: could not create ProductionOrder — {e}")
                    continue
            else:
                skipped_orders += 1

            # ── Parse numeric fields ──────────────────────────────────────
            def _float(val, default=0.0):
                try:
                    return float(val) if val else default
                except (ValueError, TypeError):
                    return default

            routing_time = _float(row.get('Routing Time (min)'), float(product.routing_time_minutes))
            remaining_time = _float(row.get('Remaining Time'), routing_time)

            raw_status = row.get('Status', 'Planned').strip()
            status = raw_status if raw_status in VALID_STATUSES else 'Planned'

            try:
                seq = int(float(row.get('SequenceNumber', 0)))
            except (ValueError, TypeError):
                seq = 0

            remark = row.get('Remark', '').strip() or None

            # ── Insert ScheduleAssignment ─────────────────────────────────
            assignment = ScheduleAssignment(
                schedule_row_id=row_uuid,
                production_order_id=production_order.id,
                technician_id=tech.id,
                schedule_date=order_date,
                sequence_number=seq,
                status=status,
                routing_time_minutes=routing_time,
                remaining_time_minutes=remaining_time,
                remark=remark,
            )
            session.add(assignment)
            existing_uuids.add(str(row_uuid))
            created_assignments += 1

        session.flush()

    print(f"\nDone.")
    print(f"  ProductionOrders  — created: {created_orders}, already existed: {skipped_orders}")
    print(f"  ScheduleAssignments — created: {created_assignments}, already existed: {skipped_assignments}")
    if errors:
        print(f"\nWarnings/errors ({len(errors)}):")
        for e in errors:
            print(f"  • {e}")


if __name__ == '__main__':
    main()
