from __future__ import annotations

from datetime import date as Date

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from db.models import Shift


class ShiftRepository:

    @staticmethod
    def find_by_date(session: Session, shift_date: Date) -> list[Shift]:
        return (
            session.query(Shift)
            .options(joinedload(Shift.technician))
            .filter_by(shift_date=shift_date)
            .all()
        )

    @staticmethod
    def find_previous_shift(session: Session, before_date: Date) -> list[Shift]:
        """Return shifts from the most recent date strictly before before_date."""
        max_date = (
            session.query(func.max(Shift.shift_date))
            .filter(Shift.shift_date < before_date)
            .scalar()
        )
        if not max_date:
            return []
        return (
            session.query(Shift)
            .options(joinedload(Shift.technician))
            .filter_by(shift_date=max_date)
            .all()
        )

    @staticmethod
    def upsert(session: Session, shifts: list[Shift]) -> None:
        """Insert new shifts or update existing ones matched by (technician_id, shift_date)."""
        for shift in shifts:
            existing = (
                session.query(Shift)
                .filter_by(technician_id=shift.technician_id, shift_date=shift.shift_date)
                .first()
            )
            if existing:
                existing.is_working = shift.is_working
                existing.is_transferred = shift.is_transferred
                existing.break_minutes = shift.break_minutes
                existing.extra_time_minutes = shift.extra_time_minutes
            else:
                session.add(shift)
        session.flush()
