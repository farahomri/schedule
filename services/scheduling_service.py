from __future__ import annotations

from dataclasses import replace as _dataclass_replace
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
        Additive scheduling: existing assignments are preserved. Only new
        (unassigned) orders are passed to the algorithm. Each tech's capacity
        is reduced by the time already committed to their Planned / In Progress
        / Partially Completed assignments so new orders only fill the gap.

        Raises RuntimeError if a concurrent session holds the lock.
        """
        # ── Acquire lock ─────────────────────────────────────────────────────
        with get_session() as session:
            ScheduleLockRepository.cleanup_stale(session)
            acquired = ScheduleLockRepository.acquire(session, schedule_date, locked_by_user_id)

        if not acquired:
            raise RuntimeError(
                f"Schedule for {schedule_date} is already being generated. Try again shortly."
            )

        try:
            working_techs = ShiftService.get_working_technicians(schedule_date)
            if not working_techs:
                raise ValueError("No working technicians found for this date.")

            # ── Additive: inspect what's already on the board ─────────────────
            _COMMITTED = {'Planned', 'In Progress', 'Partially Completed'}
            with get_session() as session:
                existing = (
                    session.query(ScheduleAssignment)
                    .filter_by(schedule_date=schedule_date)
                    .all()
                )
                already_assigned_ids: set[int] = {a.production_order_id for a in existing}
                consumed_time: dict[int, float] = {}
                for a in existing:
                    if a.status in _COMMITTED:
                        consumed_time[a.technician_id] = (
                            consumed_time.get(a.technician_id, 0.0)
                            + float(a.remaining_time_minutes or 0)
                        )
                # Max sequence number per tech so new rows append, not overlap
                max_seq: dict[int, int] = {}
                for a in existing:
                    if a.sequence_number and a.sequence_number > max_seq.get(a.technician_id, 0):
                        max_seq[a.technician_id] = a.sequence_number

            # Only new orders enter the algorithm
            new_orders = [o for o in daily_pool.assignable_pool if o.id not in already_assigned_ids]

            # Reduce each tech's capacity by what's already committed
            adjusted_techs = [
                _dataclass_replace(
                    tech,
                    working_time_minutes=max(
                        0, int(tech.working_time_minutes - consumed_time.get(tech.technician_id, 0.0))
                    ),
                )
                for tech in working_techs
            ]

            algo_rows, unscheduled = SchedulingService._run_algorithm(new_orders, adjusted_techs)

            # ── Persist new assignments ───────────────────────────────────────
            with get_session() as session:
                tech_seq: dict[int, int] = dict(max_seq)  # start after existing rows
                for row in algo_rows:
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
        """
        Three-phase assignment. Time is never a gate — large orders are assigned
        to the best available technician and carried across multiple shifts via
        the in-progress carryover in resolve_pool. Load tracking still guides
        which tech receives each order so work is spread evenly.
        """
        if not techs:
            return [], list(orders)

        # Sort: priority ascending (Urgent=0 first), effective_time descending (longer first)
        sorted_orders = sorted(
            orders,
            key=lambda o: (_priority_key(o.priority), -(o.effective_time_minutes or 0)),
        )

        # Track load per tech for balancing (not for gating)
        tech_remaining: dict[int, float] = {t.technician_id: float(t.working_time_minutes) for t in techs}
        tech_assigned: dict[int, float] = {t.technician_id: 0.0 for t in techs}

        scheduled: list[_AlgoRow] = []
        scheduled_ids: set[int | None] = set()

        # ── Phase 1: Round-robin — one order per technician ───────────────
        # Iterate techs by descending remaining capacity so that the freest
        # techs are filled first. This is critical for additive runs: a second
        # batch of orders should go to the 10 idle techs, not the 3 that
        # already carry batch-1 orders.
        techs_by_remaining = sorted(
            techs, key=lambda t: tech_remaining[t.technician_id], reverse=True
        )
        techs_done_p1: set[int] = set()

        for order in sorted_orders:
            if len(techs_done_p1) >= len(techs):
                break
            if order.id in scheduled_ids:
                continue
            duration = order.effective_time_minutes or 0.0

            for tech in techs_by_remaining:
                if tech.technician_id in techs_done_p1:
                    continue
                if order.class_code is None or tech.expertise_class >= order.class_code:
                    scheduled.append(_AlgoRow(order, tech, False))
                    tech_remaining[tech.technician_id] -= duration
                    tech_assigned[tech.technician_id] += duration
                    scheduled_ids.add(order.id)
                    techs_done_p1.add(tech.technician_id)
                    break

        # ── Phase 2: Balanced — expertise respected, least-loaded first ──
        for order in sorted_orders:
            if order.id in scheduled_ids:
                continue
            duration = order.effective_time_minutes or 0.0

            candidates = [
                t for t in techs
                if order.class_code is None or t.expertise_class >= order.class_code
            ]
            if not candidates:
                continue

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

        # ── Phase 3: Capacity fill — expertise ignored, any tech ─────────
        for order in sorted_orders:
            if order.id in scheduled_ids:
                continue
            duration = order.effective_time_minutes or 0.0

            best = min(
                techs,
                key=lambda t: (tech_assigned[t.technician_id], -tech_remaining[t.technician_id]),
            )
            scheduled.append(_AlgoRow(order, best, True))
            tech_remaining[best.technician_id] -= duration
            tech_assigned[best.technician_id] += duration
            scheduled_ids.add(order.id)

        unscheduled = [o for o in orders if o.id not in scheduled_ids]
        return scheduled, unscheduled
