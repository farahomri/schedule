from __future__ import annotations

import math
from dataclasses import dataclass

import pandas as pd

from datetime import date as Date

from db.database import get_session
from db.models import Product, ProductionOrder
from repositories.product_repository import ProductRepository
from repositories.production_order_repository import ProductionOrderRepository

_THRESHOLDS = [0, 160, 320, 480, float('inf')]
_LABELS = ["Low", "Medium", "High", "Very High"]


@dataclass
class ProductDTO:
    id: int
    sap_number: str
    description: str
    routing_time_minutes: float
    classification: str | None
    class_code: int | None


@dataclass
class ProductionOrderDTO:
    id: int | None
    erp_order_id: str
    product_id: int | None      # None if SAP not found in products table
    sap_number: str
    routing_time_minutes: float | None
    quantity: int
    effective_time_minutes: float | None  # routing_time × quantity
    class_code: int | None
    priority: str | None
    order_date: Date | None


class OrderService:

    @staticmethod
    def classify(routing_time_minutes) -> tuple[str | None, int | None]:
        """Pure function. Mirrors classify_order() in models/orders.py exactly."""
        if routing_time_minutes is None:
            return None, None
        try:
            val = float(routing_time_minutes)
            if math.isnan(val):
                return None, None
        except (TypeError, ValueError):
            return None, None
        for i, threshold in enumerate(_THRESHOLDS):
            if val < threshold:
                return _LABELS[i - 1], i
        return _LABELS[-1], len(_LABELS)

    @staticmethod
    def _to_dto(product: Product) -> ProductDTO:
        rt = float(product.routing_time_minutes)
        classification, class_code = OrderService.classify(rt)
        return ProductDTO(
            id=product.id,
            sap_number=product.sap_number,
            description=product.description,
            routing_time_minutes=rt,
            classification=classification,
            class_code=class_code,
        )

    @staticmethod
    def get_all_products() -> list[ProductDTO]:
        with get_session() as session:
            products = ProductRepository.find_all(session)
            return [OrderService._to_dto(p) for p in products]

    @staticmethod
    def add_product(
        sap_number: str,
        description: str,
        routing_time_minutes: float,
    ) -> ProductDTO:
        with get_session() as session:
            if ProductRepository.find_by_sap(session, sap_number):
                raise ValueError(f"SAP '{sap_number}' already exists.")
            product = Product(
                sap_number=sap_number,
                description=description,
                routing_time_minutes=routing_time_minutes,
            )
            ProductRepository.save(session, product)
            return OrderService._to_dto(product)

    @staticmethod
    def modify_product(
        sap_number: str,
        description: str | None = None,
        routing_time_minutes: float | None = None,
    ) -> ProductDTO:
        with get_session() as session:
            product = ProductRepository.find_by_sap(session, sap_number)
            if not product:
                raise ValueError(f"SAP '{sap_number}' not found.")
            if description is not None:
                product.description = description
            if routing_time_minutes is not None:
                product.routing_time_minutes = routing_time_minutes
            session.flush()
            return OrderService._to_dto(product)

    @staticmethod
    def remove_product(sap_number: str) -> None:
        with get_session() as session:
            product = ProductRepository.find_by_sap(session, sap_number)
            if not product:
                raise ValueError(f"SAP '{sap_number}' not found.")
            session.delete(product)

    @staticmethod
    def bulk_upsert_products(uploaded_df: pd.DataFrame) -> dict:
        """
        Upsert products from an uploaded DataFrame.
        Returns {'added': [...], 'modified': [...], 'skipped': [...], 'errors': [...]}.
        """
        added, modified, skipped, errors = [], [], [], []

        with get_session() as session:
            for idx, row in uploaded_df.iterrows():
                sap = ""
                try:
                    sap = str(
                        row.get('Material Number',
                        row.get('Material number',
                        row.get('SAP', '')))
                    ).strip()
                    description = str(
                        row.get('Material description',
                        row.get('Material Description', ''))
                    ).strip()
                    rt_raw = row.get('routing time',
                             row.get('Routing Time',
                             row.get('Routing time', None)))

                    if not sap or sap == 'nan':
                        errors.append(f"Row {idx + 2}: Missing Material Number")
                        continue
                    if pd.isna(rt_raw) or rt_raw == '':
                        errors.append(f"Row {idx + 2}: Missing routing time for SAP {sap}")
                        continue

                    try:
                        routing_time = float(rt_raw)
                    except (ValueError, TypeError):
                        errors.append(f"Row {idx + 2} (SAP {sap}): Invalid routing time '{rt_raw}'")
                        continue

                    if routing_time <= 0:
                        errors.append(f"Row {idx + 2} (SAP {sap}): Routing time must be positive")
                        continue

                    if not description or description == 'nan':
                        description = f"Product {sap}"

                    existing = ProductRepository.find_by_sap(session, sap)
                    if existing:
                        old_time = float(existing.routing_time_minutes)
                        if abs(old_time - routing_time) > 0.01:
                            existing.description = description
                            existing.routing_time_minutes = routing_time
                            session.flush()
                            modified.append({
                                'SAP': sap, 'Description': description,
                                'Old Time': old_time, 'New Time': routing_time,
                            })
                        else:
                            skipped.append({
                                'SAP': sap, 'Description': description,
                                'Routing Time': routing_time,
                            })
                    else:
                        product = Product(
                            sap_number=sap,
                            description=description,
                            routing_time_minutes=routing_time,
                        )
                        ProductRepository.save(session, product)
                        added.append({
                            'SAP': sap, 'Description': description,
                            'Routing Time': routing_time,
                        })

                except Exception as e:
                    errors.append(f"Row {idx + 2} (SAP {sap or 'Unknown'}): {str(e)}")

        return {'added': added, 'modified': modified, 'skipped': skipped, 'errors': errors}

    # ------------------------------------------------------------------
    # Production order methods (Task 1.5.3)
    # ------------------------------------------------------------------

    @staticmethod
    def _order_to_dto(order: ProductionOrder) -> ProductionOrderDTO:
        product = order.product
        rt = float(product.routing_time_minutes) if product else None
        qty = order.quantity
        effective = rt * qty if rt is not None else None
        _, class_code = OrderService.classify(rt) if rt is not None else (None, None)
        return ProductionOrderDTO(
            id=order.id,
            erp_order_id=order.erp_order_id,
            product_id=order.product_id,
            sap_number=product.sap_number if product else "",
            routing_time_minutes=rt,
            quantity=qty,
            effective_time_minutes=effective,
            class_code=class_code,
            priority=order.priority,
            order_date=order.order_date,
        )

    @staticmethod
    def parse_orders_from_upload(
        orders_df: pd.DataFrame, order_date: Date
    ) -> list[ProductionOrderDTO]:
        """
        Parse an orders upload DataFrame into ProductionOrderDTOs.
        Handles column name variants from the Excel upload format.
        product_id is None for SAP numbers not found in the products table.
        """
        dtos: list[ProductionOrderDTO] = []

        with get_session() as session:
            all_products = ProductRepository.find_all(session)
            product_map = {p.sap_number: p for p in all_products}

            for _, row in orders_df.iterrows():
                sap = str(
                    row.get('Material Number', row.get('Material number', row.get('SAP', '')))
                ).strip()
                if not sap or sap == 'nan':
                    continue

                erp_order_id = str(
                    row.get('Order', row.get('Order ID', sap))
                ).strip()
                if not erp_order_id or erp_order_id == 'nan':
                    erp_order_id = sap

                priority_raw = str(row.get('Priority', '')).strip()
                priority = priority_raw if priority_raw and priority_raw != 'nan' else None

                try:
                    quantity = max(1, int(float(
                        row.get('Order quantity (GMEIN)',
                        row.get('Quantity', row.get('quantity', 1)))
                    )))
                except (ValueError, TypeError):
                    quantity = 1

                product = product_map.get(sap)
                if product:
                    rt = float(product.routing_time_minutes)
                    product_id = product.id
                    _, class_code = OrderService.classify(rt)
                    effective = rt * quantity
                else:
                    rt = product_id = class_code = effective = None

                dtos.append(ProductionOrderDTO(
                    id=None,
                    erp_order_id=erp_order_id,
                    product_id=product_id,
                    sap_number=sap,
                    routing_time_minutes=rt,
                    quantity=quantity,
                    effective_time_minutes=effective,
                    class_code=class_code,
                    priority=priority,
                    order_date=order_date,
                ))

        return dtos

    @staticmethod
    def validate_orders(order_dtos: list[ProductionOrderDTO]) -> list[str]:
        """Return SAP numbers whose product was not found in the products table."""
        return [dto.sap_number for dto in order_dtos if dto.product_id is None]

    @staticmethod
    def save_production_orders(
        order_dtos: list[ProductionOrderDTO], order_date: Date
    ) -> int:
        """Insert production orders into the DB, skipping duplicates. Returns count of newly inserted rows."""
        with get_session() as session:
            new_orders = []
            for dto in order_dtos:
                if dto.product_id is None:
                    continue
                if ProductionOrderRepository.find_by_erp_id_and_date(
                    session, dto.erp_order_id, order_date
                ):
                    continue
                new_orders.append(ProductionOrder(
                    erp_order_id=dto.erp_order_id,
                    product_id=dto.product_id,
                    priority=dto.priority,
                    order_date=order_date,
                    quantity=dto.quantity,
                ))
            if new_orders:
                ProductionOrderRepository.bulk_insert(session, new_orders)
            return len(new_orders)

    @staticmethod
    def get_late_orders(order_date: Date) -> list[ProductionOrderDTO]:
        """Return unstarted production orders from before order_date (never scheduled)."""
        with get_session() as session:
            orders = ProductionOrderRepository.find_unstarted_before_date(session, order_date)
            return [OrderService._order_to_dto(o) for o in orders]
