from __future__ import annotations

import uuid
from datetime import date as Date

from sqlalchemy import exists
from sqlalchemy.orm import Session, joinedload

from db.models import ProductionOrder, ScheduleAssignment


class ScheduleRepository:

    @staticmethod
    def find_by_date(session: Session, schedule_date: Date) -> list[ScheduleAssignment]:
        return (
            session.query(ScheduleAssignment)
            .options(
                joinedload(ScheduleAssignment.production_order)
                .joinedload(ProductionOrder.product),
                joinedload(ScheduleAssignment.technician),
            )
            .filter_by(schedule_date=schedule_date)
            .order_by(
                ScheduleAssignment.technician_id,
                ScheduleAssignment.sequence_number,
            )
            .all()
        )

    @staticmethod
    def find_by_id(session: Session, assignment_id: int) -> ScheduleAssignment | None:
        return (
            session.query(ScheduleAssignment)
            .options(
                joinedload(ScheduleAssignment.production_order)
                .joinedload(ProductionOrder.product),
                joinedload(ScheduleAssignment.technician),
            )
            .filter_by(id=assignment_id)
            .first()
        )

    @staticmethod
    def find_by_row_uuid(
        session: Session, schedule_row_id: uuid.UUID | str
    ) -> ScheduleAssignment | None:
        return (
            session.query(ScheduleAssignment)
            .options(
                joinedload(ScheduleAssignment.production_order)
                .joinedload(ProductionOrder.product),
                joinedload(ScheduleAssignment.technician),
            )
            .filter_by(schedule_row_id=schedule_row_id)
            .first()
        )

    @staticmethod
    def save(session: Session, assignment: ScheduleAssignment) -> ScheduleAssignment:
        session.add(assignment)
        session.flush()
        return assignment

    @staticmethod
    def delete_by_date(session: Session, schedule_date: Date) -> int:
        """Delete all Planned assignments for a date (for re-generation). Returns row count."""
        return (
            session.query(ScheduleAssignment)
            .filter(
                ScheduleAssignment.schedule_date == schedule_date,
                ScheduleAssignment.status == 'Planned',
            )
            .delete(synchronize_session=False)
        )

    @staticmethod
    def delete_all_by_date(session: Session, schedule_date: Date) -> int:
        """Delete ALL assignments for a date regardless of status. Returns row count."""
        return (
            session.query(ScheduleAssignment)
            .filter(ScheduleAssignment.schedule_date == schedule_date)
            .delete(synchronize_session=False)
        )

    @staticmethod
    def find_unscheduled_by_date(
        session: Session, schedule_date: Date
    ) -> list[ProductionOrder]:
        """Production orders for schedule_date that have no ScheduleAssignment."""
        return (
            session.query(ProductionOrder)
            .options(joinedload(ProductionOrder.product))
            .filter(ProductionOrder.order_date == schedule_date)
            .filter(
                ~exists().where(
                    ScheduleAssignment.production_order_id == ProductionOrder.id
                )
            )
            .all()
        )
