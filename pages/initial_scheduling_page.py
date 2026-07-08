from __future__ import annotations

import traceback
from datetime import date as Date, datetime

import pandas as pd
import streamlit as st

from db.database import get_session
from repositories.user_repository import UserRepository
from services.auth_service import AuthService
from services.daily_pool_service import DailyOrderPoolService
from services.order_service import OrderService
from services.scheduling_service import SchedulingService
from services.shift_service import ShiftService
from utils.session_manager import SessionManager
from utils.ui_components import UIComponents


def _get_user_id() -> int:
    """Look up the DB id for the currently logged-in user."""
    username = SessionManager.get('username', '')
    with get_session() as session:
        user = UserRepository.get_by_username(session, username)
        return user.id if user else 1


class InitialSchedulingPage:

    @staticmethod
    def render():
        if not AuthService.require_role('manager', 'admin'):
            return

        UIComponents.page_header(
            "📊 Initial Scheduling",
            "Upload orders and shifts to generate a daily schedule"
        )

        # ── Date picker ───────────────────────────────────────────────────────
        selected_date: Date = st.date_input(
            "Schedule date",
            value=datetime.today().date(),
            key="sched_date_picker",
        )

        st.markdown("---")

        tab_gen, tab_view = st.tabs(["🆕 Generate Schedule", "📋 View Existing"])

        # ══════════════════════════════════════════════════════════════════════
        # Tab 1 — Generate
        # ══════════════════════════════════════════════════════════════════════
        with tab_gen:
            with st.expander("📖 Instructions", expanded=False):
                st.markdown("""
**How to use:**
1. Pick the **schedule date** above.
2. Upload the **Orders File** (Excel) — columns: `Order`, `Material Number`, `Material description`, `Priority`, `Order quantity (GMEIN)`.
3. Upload the **Shifts File** (Excel) — columns: `Matricule`, `Working`, `To another`, `Break`, `Extra Time`.
4. Click **Generate Schedule**.
5. Go to **Schedule Management** to view and edit the result.

> Any orders from previous dates that were never started will be automatically included as late orders.
                """)

            col1, col2 = st.columns(2)

            with col1:
                st.markdown("#### 📄 Orders File")
                uploaded_orders = st.file_uploader(
                    "Upload Orders Excel File",
                    type=['xlsx'],
                    key="init_orders_v2",
                    help="Excel file with order list for the selected date",
                )
                if uploaded_orders:
                    st.success(f"✅ {uploaded_orders.name}")

            with col2:
                st.markdown("#### 👷 Shifts File")
                uploaded_shifts = st.file_uploader(
                    "Upload Shifts Excel File",
                    type=['xlsx'],
                    key="init_shifts_v2",
                    help="Excel file with technician attendance for the selected date",
                )
                if uploaded_shifts:
                    st.success(f"✅ {uploaded_shifts.name}")

            if uploaded_orders and uploaded_shifts:
                st.markdown("---")
                col_a, col_b, col_c = st.columns([1, 2, 1])
                with col_b:
                    go = st.button(
                        "🚀 Generate Schedule",
                        type="primary",
                        use_container_width=True,
                        key="btn_generate",
                    )

                if go:
                    InitialSchedulingPage._run_generation(
                        selected_date, uploaded_orders, uploaded_shifts
                    )

        # ══════════════════════════════════════════════════════════════════════
        # Tab 2 — View existing
        # ══════════════════════════════════════════════════════════════════════
        with tab_view:
            st.markdown(f"#### Schedule for **{selected_date}**")

            try:
                assignments = SchedulingService.get_schedule(selected_date)
                unscheduled = SchedulingService.get_unscheduled(selected_date)

                if not assignments:
                    st.info("No schedule generated yet for this date.")
                else:
                    col_m1, col_m2, col_m3 = st.columns(3)
                    col_m1.metric("Scheduled", len(assignments))
                    col_m2.metric("Unscheduled", len(unscheduled))
                    col_m3.metric(
                        "Total time",
                        f"{sum(a.routing_time_minutes for a in assignments):.0f} min",
                    )

                    st.dataframe(
                        pd.DataFrame([{
                            'Technician': a.technician_matricule,
                            'Order ID': a.erp_order_id,
                            'SAP': a.sap_number,
                            'Time (min)': a.routing_time_minutes,
                            'Status': a.status,
                            'Override': '⚠️' if a.is_expertise_override else '',
                            'Remark': a.remark or '',
                        } for a in assignments]),
                        use_container_width=True,
                        hide_index=True,
                    )

                    if unscheduled:
                        with st.expander(f"⏳ {len(unscheduled)} unscheduled orders"):
                            st.dataframe(
                                pd.DataFrame([{
                                    'Order ID': o.erp_order_id,
                                    'SAP': o.sap_number,
                                    'Effective time (min)': o.effective_time_minutes,
                                    'Priority': o.priority or '—',
                                } for o in unscheduled]),
                                hide_index=True,
                            )

            except Exception as e:
                st.error(f"Error loading schedule: {e}")

    # ── Generation flow (called from Tab 1 button) ────────────────────────────

    @staticmethod
    def _run_generation(
        schedule_date: Date,
        uploaded_orders,
        uploaded_shifts,
    ):
        try:
            with st.spinner("Parsing and validating files…"):
                orders_df = pd.read_excel(uploaded_orders, engine='openpyxl')
                shifts_df = pd.read_excel(uploaded_shifts, engine='openpyxl')

            # ── 1. Parse & validate orders ────────────────────────────────────
            with st.spinner("Classifying orders…"):
                order_dtos = OrderService.parse_orders_from_upload(orders_df, schedule_date)
                missing_sap = OrderService.validate_orders(order_dtos)

            if missing_sap:
                st.error(
                    f"❌ {len(missing_sap)} SAP number(s) not found in the product catalogue. "
                    "Add them in **Manage Orders** first."
                )
                with st.expander("Missing SAP numbers"):
                    for sap in missing_sap:
                        st.write(f"• {sap}")
                return

            st.success(f"✅ {len(order_dtos)} orders parsed")

            # ── 2. Parse & validate shifts ────────────────────────────────────
            with st.spinner("Processing shifts…"):
                shift_dtos, unmatched = ShiftService.parse_shifts_from_upload(
                    shifts_df, schedule_date
                )

            if unmatched:
                st.warning(
                    f"⚠️ {len(unmatched)} matricule(s) not found in the technician list "
                    "and will be skipped: " + ", ".join(unmatched)
                )

            working = [s for s in shift_dtos if s.is_working and not s.is_transferred]
            if not working:
                st.error("❌ No working technicians found in the shifts file.")
                return

            st.success(f"✅ {len(working)} working technician(s) identified")

            # ── 3. Persist orders & shifts ────────────────────────────────────
            with st.spinner("Saving to database…"):
                OrderService.save_production_orders(order_dtos, schedule_date)
                ShiftService.save_shifts(shift_dtos, schedule_date)

            # ── 4. Resolve daily pool (carryover + late orders) ───────────────
            with st.spinner("Resolving order pool…"):
                daily_pool = DailyOrderPoolService.resolve_pool(schedule_date)

            pool_info = daily_pool.summary
            if pool_info['carried_in_progress']:
                st.info(
                    f"ℹ️ {pool_info['carried_in_progress']} in-progress order(s) carried from the previous shift."
                )
            if pool_info['newly_blocked']:
                st.warning(
                    f"⚠️ {pool_info['newly_blocked']} order(s) blocked — no qualified tech available."
                )
            if pool_info['late_orders']:
                st.info(f"ℹ️ {pool_info['late_orders']} late order(s) from previous dates added to pool.")

            if not daily_pool.assignable_pool:
                st.warning("No assignable orders in the pool. Schedule not generated.")
                return

            # ── 5. Generate schedule ──────────────────────────────────────────
            with st.spinner("Running scheduling algorithm…"):
                user_id = _get_user_id()
                scheduled, unscheduled = SchedulingService.generate_schedule(
                    schedule_date, daily_pool, user_id
                )

            # ── 6. Summary ────────────────────────────────────────────────────
            st.success("✅ Schedule generated successfully!")

            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Scheduled", len(scheduled))
            col2.metric("Unscheduled", len(unscheduled))
            col3.metric("Technicians", len(working))
            col4.metric(
                "Total time",
                f"{sum(a.routing_time_minutes for a in scheduled):.0f} min",
            )

            if unscheduled:
                with st.expander(f"⏳ {len(unscheduled)} unscheduled orders"):
                    st.dataframe(
                        pd.DataFrame([{
                            'Order ID': o.erp_order_id,
                            'SAP': o.sap_number,
                            'Effective time (min)': o.effective_time_minutes,
                            'Priority': o.priority or '—',
                            'Class': o.class_code,
                        } for o in unscheduled]),
                        hide_index=True,
                    )

            st.info("💡 Go to **Schedule Management** to view and edit the schedule.")

        except RuntimeError as e:
            st.error(f"❌ {e}")
        except Exception as e:
            st.error(f"❌ Error: {e}")
            with st.expander("Error details"):
                st.code(traceback.format_exc())
