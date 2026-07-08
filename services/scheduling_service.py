from __future__ import annotations

from datetime import date as Date
from typing import NamedTuple

from db.database import get_session
from db.models import ScheduleAssignment
from repositories.schedule_lock_repository import ScheduleLockRepository
from repositories.schedule_repository import ScheduleRepository
from services.daily_pool_service import AssignmentDTO, DailyOrderPoolService, DailyPoolResult
from services.order_service import OrderService, ProductionOrderDTO
from services.shift_service import ShiftService, WorkingTechnicianDTO


_PRIORITY_ORDER = {'urgent': 0, '0': 0, 'a': 1, '1': 1, 'b': 2, '2': 2, 'c': 3, '3': 3}


def _priority_key(priority: str | None) -> int:
    if not priority:
        return 999
    return _PRIORITY_ORDER.get(str(priority).strip().lower(), 999)


class _AlgoRow(NamedTuple):
    order: ProductionOrderDTO
    tech: WorkingTechnicianDTO
    is_override: bool  # True = Phase 3 capacity fill, expertise not matched


class SchedulingService:

    @staticmethod
    def generate_schedule(
        schedule_date: Date,
        daily_pool: DailyPoolResult,
        locked_by_user_id: int,
    ) -> tuple[list[AssignmentDTO], list[ProductionOrderDTO]]:
        """
        Run the three-phase algorithm against daily_pool.assignable_pool and
        persist ScheduleAssignment rows. Returns (scheduled_dtos, unscheduled_dtos).

        Raises RuntimeError if a concurrent session already holds the lock.
        """
        # ── Acquire lock ────────────────────────────────────────────────────
        with get_session() as session:
            ScheduleLockRepository.cleanup_stale(session)
            acquired = ScheduleLockRepository.acquire(session, schedule_date, locked_by_user_id)

        if not acquired:
            raise RuntimeError(
                f"Schedule for {schedule_date} is already being generated. Try again shortly."
            )

        try:
            # ── Run algorithm (no DB session — pure in-memory) ───────────────
            working_techs = ShiftService.get_working_technicians(schedule_date)
            if not working_techs:
                raise ValueError("No working technicians found for this date.")

            algo_rows, unscheduled = SchedulingService._run_algorithm(
                daily_pool.assignable_pool, working_techs
            )

            # ── Persist results ──────────────────────────────────────────────
            with get_session() as session:
                # Skip orders that already have an assignment for today
                # (handles idempotent re-runs without violating the unique constraint)
                already_assigned = {
                    row[0]
                    for row in session.query(ScheduleAssignment.production_order_id)
                    .filter_by(schedule_date=schedule_date)
                    .all()
                }

                tech_seq: dict[int, int] = {}  # per-tech sequence counter

                for row in algo_rows:
                    if row.order.id in already_assigned:
                        continue
                    tech_id = row.tech.technician_id
                    tech_seq[tech_id] = tech_seq.get(tech_id, 0) + 1
                    session.add(ScheduleAssignment(
                        production_order_id=row.order.id,
                        technician_id=tech_id,
                        schedule_date=schedule_date,
                        sequence_number=tech_seq[tech_id],
                        status='Planned',
                        routing_time_minutes=row.order.routing_time_minutes,
                        remaining_time_minutes=row.order.effective_time_minutes,
                        is_expertise_override=row.is_override,
                        remark='Capacity fill — expertise not matched' if row.is_override else None,
                    ))

                session.flush()
                ScheduleLockRepository.release(session, schedule_date)

        except Exception:
            with get_session() as session:
                ScheduleLockRepository.release(session, schedule_date)
            raise

        scheduled_dtos = SchedulingService.get_schedule(schedule_date)
        return scheduled_dtos, unscheduled

    @staticmethod
    def get_schedule(schedule_date: Date) -> list[AssignmentDTO]:
        """Return all ScheduleAssignments for schedule_date as AssignmentDTOs."""
        with get_session() as session:
            assignments = ScheduleRepository.find_by_date(session, schedule_date)
            return [DailyOrderPoolService._to_dto(a) for a in assignments]

    @staticmethod
    def get_unscheduled(schedule_date: Date) -> list[ProductionOrderDTO]:
        """Return production orders for schedule_date that have no assignment."""
        with get_session() as session:
            orders = ScheduleRepository.find_unscheduled_by_date(session, schedule_date)
            return [OrderService._order_to_dto(o) for o in orders]

    # ── Three-phase algorithm ─────────────────────────────────────────────────

    @staticmethod
    def _run_algorithm(
        orders: list[ProductionOrderDTO],
        techs: list[WorkingTechnicianDTO],
    ) -> tuple[list[_AlgoRow], list[ProductionOrderDTO]]:
        # Sort: priority ascending (Urgent=0 first), effective_time descending (longer first)
        sorted_orders = sorted(
            orders,
            key=lambda o: (_priority_key(o.priority), -(o.effective_time_minutes or 0)),
        )

        # Per-tech capacity state
        tech_remaining: dict[int, float] = {t.technician_id: float(t.working_time_minutes) for t in techs}
        tech_assigned: dict[int, float] = {t.technician_id: 0.0 for t in techs}

        scheduled: list[_AlgoRow] = []
        scheduled_ids: set[int | None] = set()

        def fits(tech_id: int, duration: float) -> bool:
            return tech_remaining[tech_id] >= duration

        # ── Phase 1: Round-robin — one order per technician ───────────────
        techs_done_p1: set[int] = set()

        for order in sorted_orders:
            if len(techs_done_p1) >= len(techs):
                break
            if order.id in scheduled_ids:
                continue
            duration = order.effective_time_minutes or 0.0

            for tech in techs:
                if tech.technician_id in techs_done_p1:
                    continue
                expertise_ok = (order.class_code is None or tech.expertise_class >= order.class_code)
                if expertise_ok and fits(tech.technician_id, duration):
                    scheduled.append(_AlgoRow(order, tech, False))
                    tech_remaining[tech.technician_id] -= duration
                    tech_assigned[tech.technician_id] += duration
                    scheduled_ids.add(order.id)
                    techs_done_p1.add(tech.technician_id)
                    break

        # ── Phase 2: Balanced — remaining orders, expertise respected ─────
        for order in sorted_orders:
            if order.id in scheduled_ids:
                continue
            duration = order.effective_time_minutes or 0.0

            candidates = [
                t for t in techs
                if (order.class_code is None or t.expertise_class >= order.class_code)
                and fits(t.technician_id, duration)
            ]
            if not candidates:
                continue

            # Tiebreak: least assigned time → exact expertise match → most remaining time
            best = min(
                candidates,
                key=lambda t: (
                    tech_assigned[t.technician_id],
                    -(t.expertise_class == (order.class_code or 0)),
                    -tech_remaining[t.technician_id],
                ),
            )
            scheduled.append(_AlgoRow(order, best, False))
            tech_remaining[best.technician_id] -= duration
            tech_assigned[best.technician_id] += duration
            scheduled_ids.add(order.id)

        # ── Phase 3: Capacity fill — expertise ignored ────────────────────
        for order in sorted_orders:
            if order.id in scheduled_ids:
                continue
            duration = order.effective_time_minutes or 0.0

            candidates = [t for t in techs if fits(t.technician_id, duration)]
            if not candidates:
                continue

            best = min(
                candidates,
                key=lambda t: (tech_assigned[t.technician_id], -tech_remaining[t.technician_id]),
            )
            scheduled.append(_AlgoRow(order, best, True))
            tech_remaining[best.technician_id] -= duration
            tech_assigned[best.technician_id] += duration
            scheduled_ids.add(order.id)

        unscheduled = [o for o in orders if o.id not in scheduled_ids]
        return scheduled, unscheduled
