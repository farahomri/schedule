from __future__ import annotations

from dataclasses import dataclass
from datetime import date as Date

from sqlalchemy.orm import joinedload

from db.database import get_session
from db.models import ProductionOrder, ScheduleAssignment
from repositories.production_order_repository import ProductionOrderRepository
from repositories.shift_repository import ShiftRepository
from services.order_service import OrderService, ProductionOrderDTO
from services.shift_service import ShiftService, WorkingTechnicianDTO


@dataclass
class AssignmentDTO:
    assignment_id: int
    erp_order_id: str
    sap_number: str
    technician_id: int
    technician_matricule: str
    schedule_date: Date
    status: str
    routing_time_minutes: float
    remaining_time_minutes: float
    is_expertise_override: bool
    remark: str | None


@dataclass
class DailyPoolResult:
    carried_in_progress: list[AssignmentDTO]
    newly_blocked: list[AssignmentDTO]
    unblocked_reassigned: list[AssignmentDTO]
    assignable_pool: list[ProductionOrderDTO]
    summary: dict


class DailyOrderPoolService:

    @staticmethod
    def resolve_pool(schedule_date: Date) -> DailyPoolResult:
        working_techs = ShiftService.get_working_technicians(schedule_date)
        working_tech_ids = {t.technician_id for t in working_techs}

        carried_in_progress: list[AssignmentDTO] = []
        newly_blocked: list[AssignmentDTO] = []
        unblocked_reassigned: list[AssignmentDTO] = []
        committed_tech_ids: set[int] = set()  # techs locked into carryover work

        with get_session() as session:

            # ── Step 1: In-progress carryover ────────────────────────────────
            prev_shifts = ShiftRepository.find_previous_shift(session, schedule_date)
            if prev_shifts:
                prev_date = prev_shifts[0].shift_date
                in_progress = (
                    session.query(ScheduleAssignment)
                    .options(
                        joinedload(ScheduleAssignment.production_order)
                        .joinedload(ProductionOrder.product),
                        joinedload(ScheduleAssignment.technician),
                    )
                    .filter_by(schedule_date=prev_date, status='In Progress')
                    .all()
                )
                for a in in_progress:
                    if a.technician_id in working_tech_ids:
                        # Tech is working today — assignment continues unchanged.
                        carried_in_progress.append(DailyOrderPoolService._to_dto(a))
                        committed_tech_ids.add(a.technician_id)
                    else:
                        # Tech is absent — find a replacement.
                        class_code = DailyOrderPoolService._class_code(a)
                        replacement = DailyOrderPoolService._find_replacement_technician(
                            class_code, working_techs, committed_tech_ids
                        )
                        if replacement:
                            new_a = ScheduleAssignment(
                                production_order_id=a.production_order_id,
                                technician_id=replacement.technician_id,
                                schedule_date=schedule_date,
                                sequence_number=0,
                                status='In Progress',
                                routing_time_minutes=a.routing_time_minutes,
                                remaining_time_minutes=a.remaining_time_minutes,
                                remark=(
                                    f"Tech absent {prev_date} — "
                                    f"replaced by {replacement.matricule}"
                                ),
                            )
                            session.add(new_a)
                            session.flush()
                            carried_in_progress.append(DailyOrderPoolService._build_dto(
                                new_a.id, a, replacement.technician_id,
                                replacement.matricule, schedule_date, 'In Progress',
                            ))
                            committed_tech_ids.add(replacement.technician_id)
                        else:
                            a.status = 'Blocked'
                            a.remark = "No qualified tech available today"
                            session.flush()
                            newly_blocked.append(DailyOrderPoolService._to_dto(a))

            # ── Step 2: Manager-unblocked order carryover ─────────────────────
            blocked = (
                session.query(ScheduleAssignment)
                .options(
                    joinedload(ScheduleAssignment.production_order)
                    .joinedload(ProductionOrder.product),
                    joinedload(ScheduleAssignment.technician),
                )
                .filter(
                    ScheduleAssignment.schedule_date < schedule_date,
                    ScheduleAssignment.status == 'Blocked',
                    ScheduleAssignment.was_unblocked_by_manager == True,  # noqa: E712
                )
                .all()
            )
            for a in blocked:
                preferred_tech_id = a.technician_id
                if preferred_tech_id in working_tech_ids:
                    tech_id = preferred_tech_id
                    matricule = a.technician.matricule if a.technician else ""
                else:
                    class_code = DailyOrderPoolService._class_code(a)
                    replacement = DailyOrderPoolService._find_replacement_technician(
                        class_code, working_techs, committed_tech_ids
                    )
                    if not replacement:
                        continue  # leave blocked, no available tech
                    tech_id = replacement.technician_id
                    matricule = replacement.matricule

                new_a = ScheduleAssignment(
                    production_order_id=a.production_order_id,
                    technician_id=tech_id,
                    schedule_date=schedule_date,
                    sequence_number=0,
                    status='Planned',
                    routing_time_minutes=a.routing_time_minutes,
                    remaining_time_minutes=a.remaining_time_minutes,
                    remark=f"Unblocked by manager — continued from {a.schedule_date}",
                )
                session.add(new_a)
                session.flush()
                unblocked_reassigned.append(DailyOrderPoolService._build_dto(
                    new_a.id, a, tech_id, matricule, schedule_date, 'Planned',
                ))

            # ── Step 3 & 4: Build assignable pool inside session ──────────────
            today_orders = ProductionOrderRepository.find_by_date(session, schedule_date)
            today_dtos = [OrderService._order_to_dto(o) for o in today_orders]

        # Late orders open their own session.
        late_orders = OrderService.get_late_orders(schedule_date)
        assignable_pool = today_dtos + late_orders

        summary = {
            'carried_in_progress': len(carried_in_progress),
            'newly_blocked': len(newly_blocked),
            'unblocked_reassigned': len(unblocked_reassigned),
            'late_orders': len(late_orders),
            'today_orders': len(today_dtos),
            'total_assignable': len(assignable_pool),
        }

        return DailyPoolResult(
            carried_in_progress=carried_in_progress,
            newly_blocked=newly_blocked,
            unblocked_reassigned=unblocked_reassigned,
            assignable_pool=assignable_pool,
            summary=summary,
        )

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _find_replacement_technician(
        class_code: int | None,
        working_techs: list[WorkingTechnicianDTO],
        excluded_tech_ids: set[int],
    ) -> WorkingTechnicianDTO | None:
        candidates = [
            t for t in working_techs
            if t.technician_id not in excluded_tech_ids
            and (class_code is None or t.expertise_class >= class_code)
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda t: (t.expertise_class, t.working_time_minutes))

    @staticmethod
    def _to_dto(a: ScheduleAssignment) -> AssignmentDTO:
        order = a.production_order
        return AssignmentDTO(
            assignment_id=a.id,
            erp_order_id=order.erp_order_id if order else "",
            sap_number=order.product.sap_number if (order and order.product) else "",
            technician_id=a.technician_id,
            technician_matricule=a.technician.matricule if a.technician else "",
            schedule_date=a.schedule_date,
            status=a.status,
            routing_time_minutes=float(a.routing_time_minutes),
            remaining_time_minutes=float(a.remaining_time_minutes),
            is_expertise_override=a.is_expertise_override,
            remark=a.remark,
        )

    @staticmethod
    def _build_dto(
        assignment_id: int,
        source: ScheduleAssignment,
        tech_id: int,
        matricule: str,
        schedule_date: Date,
        status: str,
    ) -> AssignmentDTO:
        """Build a DTO for a newly created assignment whose relationships aren't loaded."""
        order = source.production_order
        return AssignmentDTO(
            assignment_id=assignment_id,
            erp_order_id=order.erp_order_id if order else "",
            sap_number=order.product.sap_number if (order and order.product) else "",
            technician_id=tech_id,
            technician_matricule=matricule,
            schedule_date=schedule_date,
            status=status,
            routing_time_minutes=float(source.routing_time_minutes),
            remaining_time_minutes=float(source.remaining_time_minutes),
            is_expertise_override=False,
            remark=source.remark,
        )

    @staticmethod
    def _class_code(a: ScheduleAssignment) -> int | None:
        try:
            rt = float(a.production_order.product.routing_time_minutes)
            _, code = OrderService.classify(rt)
            return code
        except Exception:
            return None
