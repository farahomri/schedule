from __future__ import annotations

from datetime import datetime

import pandas as pd
import streamlit as st

from db.database import get_session
from db.models import ScheduleAssignment
from repositories.schedule_repository import ScheduleRepository
from services.auth_service import AuthService
from services.schedule_service import ScheduleService
from services.scheduling_service import SchedulingService
from services.shift_service import ShiftService
from utils.session_manager import SessionManager
from utils.ui_components import UIComponents


class SchedulePage:

    @staticmethod
    def render():
        if not AuthService.require_role('manager', 'admin'):
            return

        UIComponents.page_header(
            "📅 Schedule Management",
            f"Current Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        )

        # ── Date picker ───────────────────────────────────────────────────────
        selected_date = st.date_input(
            "Schedule date",
            value=datetime.today().date(),
            key="schedule_mgmt_date",
        )

        # ── Load data ─────────────────────────────────────────────────────────
        try:
            assignments = SchedulingService.get_schedule(selected_date)
            unscheduled = SchedulingService.get_unscheduled(selected_date)
        except Exception as e:
            st.error(f"Error loading schedule: {e}")
            return

        if not assignments:
            UIComponents.info_message(
                "No schedule generated for this date yet. "
                "Go to Initial Scheduling to upload orders and generate one.",
                "info",
            )
            return

        # ── Statistics ────────────────────────────────────────────────────────
        st.markdown("### 📊 Statistics")
        stats = ScheduleService.get_statistics(selected_date)
        stat_keys = ['Planned', 'In Progress', 'Partially Completed', 'Completed', 'Blocked', 'Total']
        UIComponents.metric_cards({k: stats.get(k, 0) for k in stat_keys if k in stats})

        # ── Delete schedule ───────────────────────────────────────────────────
        st.markdown("---")
        with st.expander("🗑️ Delete Schedule", expanded=False):
            st.warning(
                f"This will permanently delete **all {len(assignments)} assignment(s)** "
                f"for **{selected_date}**, including any In Progress or Completed records. "
                "This cannot be undone."
            )
            confirmed = st.checkbox(
                "I understand this is irreversible", key=f"del_confirm_{selected_date}"
            )
            if st.button(
                "🗑️ Delete entire schedule for this date",
                type="primary",
                disabled=not confirmed,
                key=f"del_btn_{selected_date}",
            ):
                with get_session() as session:
                    deleted = ScheduleRepository.delete_all_by_date(session, selected_date)
                st.success(f"✅ Deleted {deleted} assignment(s) for {selected_date}.")
                st.rerun()

        st.markdown("---")

        # ── Edit section ──────────────────────────────────────────────────────
        planned = [a for a in assignments if a.status == 'Planned']
        with st.expander("✏️ Modify Schedule (Planned Orders)", expanded=False):
            if not planned:
                st.info("No Planned orders available for editing.")
            else:
                SchedulePage._render_technician_change(planned, selected_date)

        st.markdown("---")

        # ── Filters ───────────────────────────────────────────────────────────
        st.markdown("### 🔍 Filters")
        all_statuses = sorted({a.status for a in assignments})
        all_techs = sorted({a.technician_matricule for a in assignments})

        col1, col2 = st.columns(2)
        with col1:
            status_filter = st.multiselect("Status", all_statuses, default=[], key="status_f")
        with col2:
            tech_filter = st.multiselect("Technician", all_techs, default=[], key="tech_f")

        filtered = assignments
        if status_filter:
            filtered = [a for a in filtered if a.status in status_filter]
        if tech_filter:
            filtered = [a for a in filtered if a.technician_matricule in tech_filter]

        # ── Orders list ───────────────────────────────────────────────────────
        st.markdown(f"### 📋 Orders ({len(filtered)} shown)")
        if not filtered:
            st.info("No orders match the current filters.")
        else:
            for a in filtered:
                label = (
                    f"{'🔴' if a.status == 'Blocked' else '🟡' if a.status == 'In Progress' else '🟢' if a.status == 'Completed' else '⚪'} "
                    f"Order {a.erp_order_id} — {a.sap_number} | {a.technician_matricule}"
                )
                with st.expander(label, expanded=False):
                    SchedulePage._render_order_card(a)

        # ── Unscheduled section ───────────────────────────────────────────────
        st.markdown("---")
        SchedulePage._render_unscheduled(unscheduled, selected_date)

    # ── Technician reassignment ───────────────────────────────────────────────

    @staticmethod
    def _render_technician_change(planned, selected_date):
        st.markdown("**Reassign a Planned order to a different technician**")

        order_options = {
            f"{a.erp_order_id} — {a.sap_number} (currently: {a.technician_matricule})": str(a.assignment_id)
            for a in planned
        }

        try:
            working_techs = ShiftService.get_working_technicians(selected_date)
        except Exception as e:
            st.error(f"Could not load working technicians: {e}")
            return

        if not working_techs:
            st.warning("No working technicians found for this date.")
            return

        col1, col2 = st.columns(2)
        with col1:
            selected_order_label = st.selectbox(
                "Order to reassign", list(order_options.keys()), key="reassign_order"
            )
            selected_assignment_id = int(order_options[selected_order_label])

        with col2:
            tech_options = {
                f"{t.full_name} ({t.matricule}) — Level {t.expertise_class}, {t.working_time_minutes} min": t.technician_id
                for t in working_techs
            }
            selected_tech_label = st.selectbox(
                "New technician", list(tech_options.keys()), key="reassign_tech"
            )
            selected_tech_id = tech_options[selected_tech_label]

        if st.button("🔄 Reassign", key="btn_reassign", type="primary"):
            # Look up the schedule_row_id for this assignment_id
            with get_session() as session:
                a = ScheduleRepository.find_by_id(session, selected_assignment_id)
                row_uuid = str(a.schedule_row_id) if a else None

            if not row_uuid:
                st.error("Assignment not found.")
                return

            result = ScheduleService.change_technician(row_uuid, selected_tech_id)
            if result.success:
                st.success(f"✅ {result.message}")
                st.rerun()
            else:
                st.error(f"❌ {result.message}")

    # ── Order card ────────────────────────────────────────────────────────────

    @staticmethod
    def _render_order_card(a):
        col1, col2, col3 = st.columns([3, 2, 2])

        with col1:
            st.markdown(f"**Order ID:** {a.erp_order_id}")
            st.markdown(f"**SAP:** {a.sap_number}")
            st.markdown(f"**Technician:** {a.technician_matricule}")
            if a.remark:
                st.caption(f"Remark: {a.remark}")
            if a.is_expertise_override:
                st.warning("⚠️ Expertise override — tech may not fully match order class.")

        with col2:
            st.markdown(f"**Routing time:** {a.routing_time_minutes:.0f} min")
            st.markdown(f"**Remaining:** {a.remaining_time_minutes:.0f} min")

        with col3:
            st.markdown("**Status:**")
            st.markdown(UIComponents.status_badge(a.status), unsafe_allow_html=True)

        # ── Action buttons ────────────────────────────────────────────────────
        st.markdown("**Actions:**")
        row_uuid = str(a.assignment_id)

        # We need the schedule_row_id UUID for service calls. Store it via assignment_id lookup.
        def _uuid():
            with get_session() as session:
                rec = ScheduleRepository.find_by_id(session, a.assignment_id)
                return str(rec.schedule_row_id) if rec else None

        if a.status == 'Planned':
            col_a, col_b = st.columns(2)
            with col_a:
                if st.button("▶️ Start", key=f"start_{row_uuid}"):
                    r = ScheduleService.start_order(_uuid())
                    st.success(r.message) if r.success else st.error(r.message)
                    if r.success:
                        st.rerun()
            with col_b:
                if st.button("🚫 Block", key=f"block_btn_{row_uuid}"):
                    SessionManager.set(f'blocking_{row_uuid}', True)

        elif a.status == 'In Progress':
            col_a, col_b, col_c = st.columns(3)
            with col_a:
                if st.button("⏸️ Pause", key=f"stop_{row_uuid}"):
                    r = ScheduleService.stop_order(_uuid())
                    st.success(r.message) if r.success else st.error(r.message)
                    if r.success:
                        st.rerun()
            with col_b:
                if st.button("✅ Complete", key=f"end_{row_uuid}"):
                    r = ScheduleService.end_order(_uuid())
                    st.success(r.message) if r.success else st.error(r.message)
                    if r.success:
                        st.rerun()
            with col_c:
                if st.button("🚫 Block", key=f"block_btn_{row_uuid}"):
                    SessionManager.set(f'blocking_{row_uuid}', True)

        elif a.status == 'Partially Completed':
            col_a, col_b, col_c = st.columns(3)
            with col_a:
                if st.button("▶️ Resume", key=f"resume_{row_uuid}"):
                    r = ScheduleService.start_order(_uuid())
                    st.success(r.message) if r.success else st.error(r.message)
                    if r.success:
                        st.rerun()
            with col_b:
                if st.button("✅ Complete", key=f"end_p_{row_uuid}"):
                    r = ScheduleService.end_order(_uuid())
                    st.success(r.message) if r.success else st.error(r.message)
                    if r.success:
                        st.rerun()
            with col_c:
                if st.button("🚫 Block", key=f"block_btn_p_{row_uuid}"):
                    SessionManager.set(f'blocking_{row_uuid}', True)

        elif a.status == 'Blocked':
            if st.button("🔓 Unblock (carry to next shift)", key=f"unblock_{row_uuid}"):
                r = ScheduleService.unblock_order(_uuid())
                st.success(r.message) if r.success else st.error(r.message)
                if r.success:
                    st.rerun()

        elif a.status == 'Completed':
            st.success("✅ Completed")

        # ── Block form (shown after clicking Block button) ─────────────────
        if SessionManager.get(f'blocking_{row_uuid}'):
            with st.form(key=f'block_form_{row_uuid}'):
                st.markdown("**Mark as Blocked**")
                reason = st.text_input("Block reason", key=f'reason_{row_uuid}')
                time_spent = st.number_input(
                    "Time already spent (min)", min_value=0.0, step=1.0, key=f'time_{row_uuid}'
                )
                submitted = st.form_submit_button("Confirm Block")
                cancelled = st.form_submit_button("Cancel")

            if submitted:
                if not reason.strip():
                    st.error("Block reason is required.")
                else:
                    r = ScheduleService.mark_blocked(_uuid(), reason.strip(), time_spent)
                    SessionManager.set(f'blocking_{row_uuid}', False)
                    st.success(r.message) if r.success else st.error(r.message)
                    if r.success:
                        st.rerun()
            if cancelled:
                SessionManager.set(f'blocking_{row_uuid}', False)
                st.rerun()

    # ── Unscheduled orders ────────────────────────────────────────────────────

    @staticmethod
    def _render_unscheduled(unscheduled, selected_date):
        st.markdown("### 📦 Unscheduled Orders")

        if not unscheduled:
            st.success("✅ All orders have been scheduled!")
            return

        st.warning(f"⚠️ {len(unscheduled)} order(s) could not be automatically scheduled.")

        with st.expander("📋 View & Manually Assign", expanded=False):
            st.dataframe(
                pd.DataFrame([{
                    'Order ID': o.erp_order_id,
                    'SAP': o.sap_number,
                    'Effective time (min)': o.effective_time_minutes,
                    'Priority': o.priority or '—',
                    'Class': o.class_code,
                } for o in unscheduled]),
                hide_index=True,
                use_container_width=True,
            )

            st.markdown("---")
            st.markdown("#### Manually assign an order")

            try:
                working_techs = ShiftService.get_working_technicians(selected_date)
            except Exception as e:
                st.error(f"Could not load technicians: {e}")
                return

            if not working_techs:
                st.info("No working technicians found for this date.")
                return

            col1, col2 = st.columns(2)

            with col1:
                order_options = {
                    f"{o.erp_order_id} — {o.sap_number} ({o.effective_time_minutes:.0f} min, class {o.class_code})": o
                    for o in unscheduled
                }
                chosen_label = st.selectbox(
                    "Select order", list(order_options.keys()), key="unsch_order_sel"
                )
                chosen_order = order_options[chosen_label]

            with col2:
                tech_options = {
                    f"{t.full_name} ({t.matricule}) — Level {t.expertise_class}, {t.working_time_minutes} min": t
                    for t in working_techs
                }
                chosen_tech_label = st.selectbox(
                    "Select technician", list(tech_options.keys()), key="unsch_tech_sel"
                )
                chosen_tech = tech_options[chosen_tech_label]

            # Qualification indicator
            if chosen_order.class_code and chosen_tech.expertise_class < chosen_order.class_code:
                st.warning(
                    f"⚠️ Tech level {chosen_tech.expertise_class} < order class {chosen_order.class_code}. "
                    "Assignment will be flagged as an expertise override."
                )
            else:
                st.success("✅ Technician meets the order expertise requirement.")

            if st.button("✅ Assign", type="primary", key="btn_manual_assign"):
                is_override = bool(
                    chosen_order.class_code and chosen_tech.expertise_class < chosen_order.class_code
                )
                try:
                    with get_session() as session:
                        # Get the next sequence number for this tech today
                        existing = ScheduleRepository.find_by_date(session, selected_date)
                        max_seq = max(
                            (a.sequence_number for a in existing if a.technician_id == chosen_tech.technician_id),
                            default=0,
                        )
                        session.add(ScheduleAssignment(
                            production_order_id=chosen_order.id,
                            technician_id=chosen_tech.technician_id,
                            schedule_date=selected_date,
                            sequence_number=max_seq + 1,
                            status='Planned',
                            routing_time_minutes=chosen_order.routing_time_minutes,
                            remaining_time_minutes=chosen_order.effective_time_minutes,
                            is_expertise_override=is_override,
                            remark='Manually assigned from unscheduled orders',
                        ))
                    st.success(
                        f"✅ Order {chosen_order.erp_order_id} assigned to {chosen_tech.matricule}."
                    )
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ {e}")
