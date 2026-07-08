from __future__ import annotations

from dataclasses import dataclass
from datetime import date as Date

import pandas as pd
from sqlalchemy.orm import joinedload

from db.database import get_session
from db.models import Shift, Technician
from repositories.shift_repository import ShiftRepository
from repositories.technician_repository import TechnicianRepository
from services.technician_service import TechnicianService


@dataclass
class ShiftDTO:
    technician_id: int
    matricule: str
    full_name: str
    shift_date: Date
    is_working: bool
    is_transferred: bool
    break_minutes: int
    extra_time_minutes: int
    working_time_minutes: int  # 480 − break + extra


@dataclass
class WorkingTechnicianDTO:
    technician_id: int
    matricule: str
    full_name: str
    expertise_class: int
    working_time_minutes: int


def _working_time(break_minutes: int, extra_time_minutes: int) -> int:
    """V2 confirmed formula: 480 − break + extra."""
    return 480 - break_minutes + extra_time_minutes


def _parse_bool(value: str) -> bool:
    return str(value).strip().lower() in ('yes', 'true', '1', 'oui')


def _safe_int(value, default: int) -> int:
    try:
        return int(float(value))
    except (ValueError, TypeError):
        return default


class ShiftService:

    @staticmethod
    def parse_shifts_from_upload(
        shifts_df: pd.DataFrame, shift_date: Date
    ) -> tuple[list[ShiftDTO], list[str]]:
        """
        Parse a shifts DataFrame (working_technicians.csv format).
        Returns (shift_dtos, unmatched_matricules).
        """
        dtos: list[ShiftDTO] = []
        unmatched: list[str] = []

        with get_session() as session:
            all_techs = TechnicianRepository.find_all(session)
            tech_map = {t.matricule: t for t in all_techs}

            for _, row in shifts_df.iterrows():
                matricule = str(row.get('Matricule', '')).strip()
                if not matricule or matricule == 'nan':
                    continue

                tech = tech_map.get(matricule)
                if not tech:
                    unmatched.append(matricule)
                    continue

                is_working = _parse_bool(row.get('Working', 'no'))
                is_transferred = _parse_bool(row.get('To another', 'no'))
                break_min = _safe_int(row.get('Break', 30), 30)
                extra_min = _safe_int(row.get('Extra Time', 0), 0)

                dtos.append(ShiftDTO(
                    technician_id=tech.id,
                    matricule=tech.matricule,
                    full_name=tech.full_name,
                    shift_date=shift_date,
                    is_working=is_working,
                    is_transferred=is_transferred,
                    break_minutes=break_min,
                    extra_time_minutes=extra_min,
                    working_time_minutes=_working_time(break_min, extra_min),
                ))

        return dtos, unmatched

    @staticmethod
    def save_shifts(shift_dtos: list[ShiftDTO], shift_date: Date) -> None:
        with get_session() as session:
            shifts = [
                Shift(
                    technician_id=dto.technician_id,
                    shift_date=shift_date,
                    is_working=dto.is_working,
                    is_transferred=dto.is_transferred,
                    break_minutes=dto.break_minutes,
                    extra_time_minutes=dto.extra_time_minutes,
                )
                for dto in shift_dtos
            ]
            ShiftRepository.upsert(session, shifts)

    @staticmethod
    def get_working_technicians(shift_date: Date) -> list[WorkingTechnicianDTO]:
        """
        Return technicians scheduled to work on shift_date (is_working=True, is_transferred=False).
        Loads technician skills in a single batched query to avoid N+1.
        """
        with get_session() as session:
            shifts = ShiftRepository.find_by_date(session, shift_date)
            working = [s for s in shifts if s.is_working and not s.is_transferred]

            if not working:
                return []

            tech_ids = [s.technician_id for s in working]
            techs = (
                session.query(Technician)
                .options(joinedload(Technician.skills))
                .filter(Technician.id.in_(tech_ids))
                .all()
            )
            tech_map = {t.id: t for t in techs}

            result: list[WorkingTechnicianDTO] = []
            for shift in working:
                tech = tech_map.get(shift.technician_id)
                if not tech:
                    continue
                skills = {s.skill_level: s.score for s in tech.skills}
                _, expertise_class = TechnicianService.compute_expertise_class(skills)
                result.append(WorkingTechnicianDTO(
                    technician_id=tech.id,
                    matricule=tech.matricule,
                    full_name=tech.full_name,
                    expertise_class=expertise_class,
                    working_time_minutes=_working_time(shift.break_minutes, shift.extra_time_minutes),
                ))

        return result

    @staticmethod
    def is_technician_working(shift_date: Date, technician_id: int) -> bool:
        with get_session() as session:
            shift = (
                session.query(Shift)
                .filter_by(technician_id=technician_id, shift_date=shift_date)
                .first()
            )
            return bool(shift and shift.is_working and not shift.is_transferred)

    @staticmethod
    def get_previous_shift(before_date: Date) -> list[ShiftDTO]:
        with get_session() as session:
            shifts = ShiftRepository.find_previous_shift(session, before_date)
            return [
                ShiftDTO(
                    technician_id=s.technician_id,
                    matricule=s.technician.matricule,
                    full_name=s.technician.full_name,
                    shift_date=s.shift_date,
                    is_working=s.is_working,
                    is_transferred=s.is_transferred,
                    break_minutes=s.break_minutes,
                    extra_time_minutes=s.extra_time_minutes,
                    working_time_minutes=_working_time(s.break_minutes, s.extra_time_minutes),
                )
                for s in shifts
            ]
