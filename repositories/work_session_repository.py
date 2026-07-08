from __future__ import annotations

from sqlalchemy.orm import Session

from db.models import WorkSession


class WorkSessionRepository:

    @staticmethod
    def find_by_assignment(session: Session, assignment_id: int) -> list[WorkSession]:
        return (
            session.query(WorkSession)
            .filter_by(assignment_id=assignment_id)
            .order_by(WorkSession.started_at)
            .all()
        )

    @staticmethod
    def find_open(session: Session, assignment_id: int) -> WorkSession | None:
        """Return the currently open session (stopped_at IS NULL), if any."""
        return (
            session.query(WorkSession)
            .filter(
                WorkSession.assignment_id == assignment_id,
                WorkSession.stopped_at == None,  # noqa: E711
            )
            .first()
        )

    @staticmethod
    def save(session: Session, work_session: WorkSession) -> WorkSession:
        session.add(work_session)
        session.flush()
        return work_session
