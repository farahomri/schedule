from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session
from sqlalchemy import func

from db.models import ScheduleLock


class ScheduleLockRepository:

    @staticmethod
    def acquire(session: Session, schedule_date, user_id: int) -> bool:
        """
        Atomically claim the scheduling lock for schedule_date.
        Returns True on success, False if the date is already locked.
        """
        existing = (
            session.query(ScheduleLock)
            .filter_by(schedule_date=schedule_date)
            .first()
        )

        if existing is None:
            session.add(ScheduleLock(schedule_date=schedule_date, locked_by=user_id))
            session.flush()
            return True

        if existing.released_at is None:
            return False  # still held by another session

        # A prior lock was released — re-use the row.
        existing.locked_by = user_id
        existing.locked_at = func.now()
        existing.released_at = None
        session.flush()
        return True

    @staticmethod
    def release(session: Session, schedule_date) -> None:
        """Mark the active lock for schedule_date as released."""
        lock = (
            session.query(ScheduleLock)
            .filter(
                ScheduleLock.schedule_date == schedule_date,
                ScheduleLock.released_at == None,  # noqa: E711
            )
            .first()
        )
        if lock:
            lock.released_at = func.now()
            session.flush()

    @staticmethod
    def cleanup_stale(session: Session, max_age_minutes: int = 30) -> int:
        """
        Release any locks that have been held (released_at IS NULL) for longer
        than max_age_minutes.  Returns the number of locks released.
        """
        stale_before = datetime.now(timezone.utc) - timedelta(minutes=max_age_minutes)
        stale = (
            session.query(ScheduleLock)
            .filter(
                ScheduleLock.released_at == None,  # noqa: E711
                ScheduleLock.locked_at < stale_before,
            )
            .all()
        )
        for lock in stale:
            lock.released_at = func.now()
        session.flush()
        return len(stale)

    @staticmethod
    def is_locked(session: Session, schedule_date) -> bool:
        """Return True if an active (unreleased) lock exists for schedule_date."""
        return (
            session.query(ScheduleLock)
            .filter(
                ScheduleLock.schedule_date == schedule_date,
                ScheduleLock.released_at == None,  # noqa: E711
            )
            .count()
        ) > 0
