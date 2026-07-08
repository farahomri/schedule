from __future__ import annotations

from sqlalchemy.orm import Session, joinedload

from db.models import Technician


class TechnicianRepository:

    @staticmethod
    def find_all(session: Session) -> list[Technician]:
        """Return all active technicians with their skills pre-loaded."""
        return (
            session.query(Technician)
            .options(joinedload(Technician.skills))
            .filter_by(is_active=True)
            .order_by(Technician.matricule)
            .all()
        )

    @staticmethod
    def find_by_matricule(session: Session, matricule: str) -> Technician | None:
        return (
            session.query(Technician)
            .options(joinedload(Technician.skills))
            .filter_by(matricule=matricule)
            .first()
        )

    @staticmethod
    def find_by_id(session: Session, technician_id: int) -> Technician | None:
        return (
            session.query(Technician)
            .options(joinedload(Technician.skills))
            .filter_by(id=technician_id)
            .first()
        )

    @staticmethod
    def save(session: Session, technician: Technician) -> Technician:
        """Persist a new or modified Technician. Does not commit."""
        session.add(technician)
        session.flush()
        return technician
