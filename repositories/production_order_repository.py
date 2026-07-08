from __future__ import annotations

from datetime import date as Date

from sqlalchemy import exists, func
from sqlalchemy.orm import Session, joinedload

from db.models import ProductionOrder, ScheduleAssignment


class ProductionOrderRepository:

    @staticmethod
    def find_by_date(session: Session, order_date: Date) -> list[ProductionOrder]:
        return (
            session.query(ProductionOrder)
            .options(joinedload(ProductionOrder.product))
            .filter_by(order_date=order_date)
            .all()
        )

    @staticmethod
    def find_unstarted_before_date(session: Session, order_date: Date) -> list[ProductionOrder]:
        """Return production orders from before order_date that have no schedule assignment."""
        return (
            session.query(ProductionOrder)
            .options(joinedload(ProductionOrder.product))
            .filter(ProductionOrder.order_date < order_date)
            .filter(
                ~exists().where(
                    ScheduleAssignment.production_order_id == ProductionOrder.id
                )
            )
            .all()
        )

    @staticmethod
    def find_by_erp_id_and_date(
        session: Session, erp_order_id: str, order_date: Date
    ) -> ProductionOrder | None:
        return (
            session.query(ProductionOrder)
            .filter_by(erp_order_id=erp_order_id, order_date=order_date)
            .first()
        )

    @staticmethod
    def bulk_insert(session: Session, orders: list[ProductionOrder]) -> None:
        for order in orders:
            session.add(order)
        session.flush()

    @staticmethod
    def delete_by_date(session: Session, order_date: Date) -> int:
        return (
            session.query(ProductionOrder)
            .filter_by(order_date=order_date)
            .delete(synchronize_session=False)
        )
