from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from db.database import get_session
from db.models import ScheduleAssignment, WorkSession
from repositories.schedule_repository import ScheduleRepository
from repositories.technician_repository import TechnicianRepository
from repositories.work_session_repository import WorkSessionRepository
from services.daily_pool_service import AssignmentDTO, DailyOrderPoolService


@dataclass
class ActionResult:
    success: bool
    message: str
    assignment: Optional[AssignmentDTO] = None


class ScheduleService:

    # ── Status transitions ────────────────────────────────────────────────────

    @staticmethod
    def start_order(schedule_row_id: str) -> ActionResult:
        """Transition Planned/Partially Completed → In Progress. Opens a WorkSession."""
        with get_session() as session:
            assignment = ScheduleRepository.find_by_row_uuid(session, schedule_row_id)
            if not assignment:
                return ActionResult(False, "Order not found.")

            if assignment.status not in ('Planned', 'Partially Completed'):
                return ActionResult(
                    False,
                    f"Cannot start an order with status '{assignment.status}'.",
                )

            # Close any stale open session (defensive)
            open_ws = WorkSessionRepository.find_open(session, assignment.id)
            if open_ws:
                open_ws.stopped_at = datetime.now(timezone.utc)

            assignment.status = 'In Progress'
            WorkSessionRepository.save(
                session,
                WorkSession(
                    assignment_id=assignment.id,
                    started_at=datetime.now(timezone.utc),
                ),
            )
            session.flush()
            return ActionResult(
                True,
                "Order started.",
                DailyOrderPoolService._to_dto(assignment),
            )

    @staticmethod
    def stop_order(schedule_row_id: str) -> ActionResult:
        """Transition In Progress → Partially Completed. Closes the active WorkSession."""
        with get_session() as session:
            assignment = ScheduleRepository.find_by_row_uuid(session, schedule_row_id)
            if not assignment:
                return ActionResult(False, "Order not found.")

            if assignment.status != 'In Progress':
                return ActionResult(False, "Can only pause orders that are In Progress.")

            open_ws = WorkSessionRepository.find_open(session, assignment.id)
            now = datetime.now(timezone.utc)
            minutes_this_session = 0.0

            if open_ws:
                open_ws.stopped_at = now
                delta = now - open_ws.started_at.replace(tzinfo=timezone.utc)
                minutes_this_session = delta.total_seconds() / 60

            assignment.status = 'Partially Completed'
            new_remaining = max(0.0, float(assignment.remaining_time_minutes) - minutes_this_session)
            assignment.remaining_time_minutes = new_remaining
            session.flush()

            return ActionResult(
                True,
                f"Order paused. Remaining time: {new_remaining:.1f} min.",
                DailyOrderPoolService._to_dto(assignment),
            )

    @staticmethod
    def end_order(schedule_row_id: str) -> ActionResult:
        """Transition In Progress/Partially Completed → Completed. Closes any open session."""
        with get_session() as session:
            assignment = ScheduleRepository.find_by_row_uuid(session, schedule_row_id)
            if not assignment:
                return ActionResult(False, "Order not found.")

            if assignment.status not in ('In Progress', 'Partially Completed'):
                return ActionResult(
                    False,
                    f"Cannot complete an order with status '{assignment.status}'.",
                )

            open_ws = WorkSessionRepository.find_open(session, assignment.id)
            if open_ws:
                open_ws.stopped_at = datetime.now(timezone.utc)

            assignment.status = 'Completed'
            assignment.remaining_time_minutes = 0
            session.flush()

            return ActionResult(
                True,
                "Order completed.",
                DailyOrderPoolService._to_dto(assignment),
            )

    @staticmethod
    def mark_blocked(
        schedule_row_id: str,
        reason: str,
        time_spent_minutes: float,
    ) -> ActionResult:
        """
        Mark an In Progress or Partially Completed order as Blocked.
        Closes any open WorkSession and deducts time_spent from remaining.
        """
        with get_session() as session:
            assignment = ScheduleRepository.find_by_row_uuid(session, schedule_row_id)
            if not assignment:
                return ActionResult(False, "Order not found.")

            if assignment.status not in ('In Progress', 'Partially Completed', 'Planned'):
                return ActionResult(
                    False,
                    f"Cannot block an order with status '{assignment.status}'.",
                )

            open_ws = WorkSessionRepository.find_open(session, assignment.id)
            if open_ws:
                open_ws.stopped_at = datetime.now(timezone.utc)

            new_remaining = max(
                0.0,
                float(assignment.remaining_time_minutes) - time_spent_minutes,
            )
            assignment.status = 'Blocked'
            assignment.remaining_time_minutes = new_remaining
            assignment.remark = f"Blocked: {reason}. Time spent: {time_spent_minutes:.1f} min"
            session.flush()

            return ActionResult(
                True,
                f"Order blocked. Remaining time: {new_remaining:.1f} min.",
                DailyOrderPoolService._to_dto(assignment),
            )

    @staticmethod
    def unblock_order(schedule_row_id: str) -> ActionResult:
        """
        Manager action: flag a Blocked order for carryover to the next shift.
        Sets was_unblocked_by_manager = True so DailyOrderPoolService picks it up.
        """
        with get_session() as session:
            assignment = ScheduleRepository.find_by_row_uuid(session, schedule_row_id)
            if not assignment:
                return ActionResult(False, "Order not found.")

            if assignment.status != 'Blocked':
                return ActionResult(False, "Only Blocked orders can be unblocked.")

            assignment.was_unblocked_by_manager = True
            session.flush()

            return ActionResult(
                True,
                "Order flagged for carryover to the next shift.",
                DailyOrderPoolService._to_dto(assignment),
            )

    # ── Reassignment ──────────────────────────────────────────────────────────

    @staticmethod
    def change_technician(
        schedule_row_id: str,
        new_technician_id: int,
    ) -> ActionResult:
        """
        Reassign a Planned order to a different technician.
        Validates that the new technician's expertise meets the order's class requirement.
        """
        with get_session() as session:
            assignment = ScheduleRepository.find_by_row_uuid(session, schedule_row_id)
            if not assignment:
                return ActionResult(False, "Order not found.")

            if assignment.status != 'Planned':
                return ActionResult(False, "Can only reassign orders that have not started yet.")

            tech = TechnicianRepository.find_by_id(session, new_technician_id)
            if not tech:
                return ActionResult(False, "Technician not found.")

            # Derive expertise class from skills
            from services.technician_service import TechnicianService
            skills = {s.skill_level: s.score for s in tech.skills}
            _, expertise_class = TechnicianService.compute_expertise_class(skills)

            # Check against the product's class code
            product = assignment.production_order.product if assignment.production_order else None
            if product:
                from services.order_service import OrderService
                _, class_code = OrderService.classify(float(product.routing_time_minutes))
                if class_code and expertise_class < class_code:
                    return ActionResult(
                        False,
                        f"Technician expertise (Level {expertise_class}) is below the "
                        f"order requirement (Level {class_code}).",
                    )

            assignment.technician_id = new_technician_id
            assignment.is_expertise_override = False
            session.flush()

            return ActionResult(
                True,
                f"Order reassigned to {tech.matricule}.",
                DailyOrderPoolService._to_dto(assignment),
            )

    # ── Queries ───────────────────────────────────────────────────────────────

    @staticmethod
    def get_statistics(schedule_date) -> dict:
        """Return status counts for all assignments on schedule_date."""
        with get_session() as session:
            assignments = ScheduleRepository.find_by_date(session, schedule_date)
            counts: dict[str, int] = {}
            for a in assignments:
                counts[a.status] = counts.get(a.status, 0) + 1
            counts['Total'] = len(assignments)
            return counts

    @staticmethod
    def get_work_sessions(schedule_row_id: str) -> list[dict]:
        """Return all WorkSession records for an assignment as plain dicts."""
        with get_session() as session:
            assignment = ScheduleRepository.find_by_row_uuid(session, schedule_row_id)
            if not assignment:
                return []
            sessions = WorkSessionRepository.find_by_assignment(session, assignment.id)
            return [
                {
                    'started_at': ws.started_at,
                    'stopped_at': ws.stopped_at,
                    'duration_minutes': (
                        (ws.stopped_at - ws.started_at).total_seconds() / 60
                        if ws.stopped_at
                        else None
                    ),
                }
                for ws in sessions
            ]
