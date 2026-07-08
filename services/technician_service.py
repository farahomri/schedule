from __future__ import annotations

from dataclasses import dataclass

from db.database import get_session
from db.models import Technician, TechnicianSkill
from repositories.technician_repository import TechnicianRepository


@dataclass
class TechnicianDTO:
    id: int
    matricule: str
    full_name: str
    department: str | None
    skills: dict[int, int]   # {skill_level: score}  skill_level is 1–4
    classification: str      # Basic Knowledge | Above Average | Good | Advanced | Unknown
    expertise_class: int     # 1–4, or 0 if Unknown
    is_active: bool


class TechnicianService:

    @staticmethod
    def compute_expertise_class(skills: dict[int, int]) -> tuple[str, int]:
        """Pure function. Mirrors the logic in models/technicians.py exactly."""
        s1 = skills.get(1, 0)
        s2 = skills.get(2, 0)
        s3 = skills.get(3, 0)
        s4 = skills.get(4, 0)
        max_score = max(s1, s2, s3, s4)

        if max_score == 0:
            classification = "Unknown"
        elif max_score == s1:
            classification = "Basic Knowledge"
        elif max_score == s2:
            classification = "Above Average"
        elif max_score == s3:
            classification = "Good"
        else:
            classification = "Advanced"

        class_map = {"Basic Knowledge": 1, "Above Average": 2, "Good": 3, "Advanced": 4}
        return classification, class_map.get(classification, 0)

    @staticmethod
    def _to_dto(tech: Technician) -> TechnicianDTO:
        skills = {s.skill_level: s.score for s in tech.skills}
        classification, expertise_class = TechnicianService.compute_expertise_class(skills)
        return TechnicianDTO(
            id=tech.id,
            matricule=tech.matricule,
            full_name=tech.full_name,
            department=tech.department,
            skills=skills,
            classification=classification,
            expertise_class=expertise_class,
            is_active=tech.is_active,
        )

    @staticmethod
    def get_all() -> list[TechnicianDTO]:
        with get_session() as session:
            techs = TechnicianRepository.find_all(session)
            return [TechnicianService._to_dto(t) for t in techs]

    @staticmethod
    def add(
        matricule: str,
        full_name: str,
        skills: dict[int, int],
        department: str | None = None,
    ) -> TechnicianDTO:
        with get_session() as session:
            if TechnicianRepository.find_by_matricule(session, matricule):
                raise ValueError(f"A technician with matricule '{matricule}' already exists.")

            tech = Technician(matricule=matricule, full_name=full_name, department=department)
            for level, score in skills.items():
                tech.skills.append(TechnicianSkill(skill_level=level, score=score))

            TechnicianRepository.save(session, tech)
            return TechnicianService._to_dto(tech)

    @staticmethod
    def modify(
        matricule: str,
        full_name: str | None = None,
        department: str | None = None,
        skills: dict[int, int] | None = None,
    ) -> TechnicianDTO:
        with get_session() as session:
            tech = TechnicianRepository.find_by_matricule(session, matricule)
            if not tech:
                raise ValueError(f"Technician '{matricule}' not found.")

            if full_name is not None:
                tech.full_name = full_name
            if department is not None:
                tech.department = department
            if skills is not None:
                existing = {s.skill_level: s for s in tech.skills}
                for level, score in skills.items():
                    if level in existing:
                        existing[level].score = score
                    else:
                        tech.skills.append(TechnicianSkill(skill_level=level, score=score))

            session.flush()
            return TechnicianService._to_dto(tech)

    @staticmethod
    def remove(matricule: str) -> None:
        """Soft-delete: sets is_active=False. The row is retained for historical records."""
        with get_session() as session:
            tech = TechnicianRepository.find_by_matricule(session, matricule)
            if not tech:
                raise ValueError(f"Technician '{matricule}' not found.")
            tech.is_active = False
