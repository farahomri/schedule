from collections import Counter

import pandas as pd
import streamlit as st

from services.auth_service import AuthService
from services.technician_service import TechnicianService


class TechniciansPage:

    @staticmethod
    def render():
        if not AuthService.require_role('admin'):
            return

        st.header("👷 Manage Technicians")

        tab_list, tab_add, tab_stats = st.tabs(
            ["📋 Technicians", "➕ Add Technician", "📊 Statistics"]
        )

        with tab_list:
            TechniciansPage._render_list()

        with tab_add:
            TechniciansPage._render_add_form()

        with tab_stats:
            TechniciansPage._render_statistics()

    # ------------------------------------------------------------------
    # Tab 1 — list + modify + deactivate
    # ------------------------------------------------------------------

    @staticmethod
    def _render_list():
        techs = TechnicianService.get_all()

        if not techs:
            st.info("No technicians found.")
            return

        rows = [
            {
                "Matricule": t.matricule,
                "Name": t.full_name,
                "Niveau 4": t.skills.get(4, 0),
                "Niveau 3": t.skills.get(3, 0),
                "Niveau 2": t.skills.get(2, 0),
                "Niveau 1": t.skills.get(1, 0),
                "Classification": t.classification,
                "Expertise Class": t.expertise_class,
            }
            for t in techs
        ]
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

        st.markdown("---")
        st.subheader("Modify / Deactivate")

        selected_matricule = st.selectbox(
            "Select technician",
            [t.matricule for t in techs],
            format_func=lambda m: next(
                f"{m} — {t.full_name}" for t in techs if t.matricule == m
            ),
        )

        tech = next((t for t in techs if t.matricule == selected_matricule), None)
        if not tech:
            return

        with st.form("modify_form"):
            st.markdown(f"**Editing: {tech.full_name}**")
            new_name = st.text_input("Full Name", value=tech.full_name)
            new_dept = st.text_input("Department", value=tech.department or "")
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                n4 = st.number_input("Niveau 4", min_value=0, max_value=100,
                                     value=int(tech.skills.get(4, 0)))
            with c2:
                n3 = st.number_input("Niveau 3", min_value=0, max_value=100,
                                     value=int(tech.skills.get(3, 0)))
            with c3:
                n2 = st.number_input("Niveau 2", min_value=0, max_value=100,
                                     value=int(tech.skills.get(2, 0)))
            with c4:
                n1 = st.number_input("Niveau 1", min_value=0, max_value=100,
                                     value=int(tech.skills.get(1, 0)))

            if st.form_submit_button("💾 Save Changes"):
                try:
                    TechnicianService.modify(
                        selected_matricule,
                        full_name=new_name.strip() or None,
                        department=new_dept.strip() or None,
                        skills={4: n4, 3: n3, 2: n2, 1: n1},
                    )
                    st.success(f"✅ Technician {selected_matricule} updated.")
                    st.rerun()
                except ValueError as e:
                    st.error(str(e))

        st.markdown("---")
        confirm = st.checkbox(
            f"I confirm I want to deactivate **{tech.full_name}** ({selected_matricule})"
        )
        if confirm:
            if st.button("🗑️ Deactivate Technician", type="primary"):
                try:
                    TechnicianService.remove(selected_matricule)
                    st.success(f"✅ {selected_matricule} deactivated.")
                    st.rerun()
                except ValueError as e:
                    st.error(str(e))

    # ------------------------------------------------------------------
    # Tab 2 — add form
    # ------------------------------------------------------------------

    @staticmethod
    def _render_add_form():
        with st.form("add_form"):
            st.subheader("New Technician")
            matricule = st.text_input("Matricule")
            full_name = st.text_input("Full Name")
            department = st.text_input("Department (optional)")
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                n4 = st.number_input("Niveau 4", min_value=0, max_value=100, value=0)
            with c2:
                n3 = st.number_input("Niveau 3", min_value=0, max_value=100, value=0)
            with c3:
                n2 = st.number_input("Niveau 2", min_value=0, max_value=100, value=0)
            with c4:
                n1 = st.number_input("Niveau 1", min_value=0, max_value=100, value=0)

            if st.form_submit_button("➕ Add Technician"):
                if not matricule.strip():
                    st.error("Matricule is required.")
                elif not full_name.strip():
                    st.error("Full name is required.")
                else:
                    try:
                        dto = TechnicianService.add(
                            matricule=matricule.strip(),
                            full_name=full_name.strip(),
                            skills={4: n4, 3: n3, 2: n2, 1: n1},
                            department=department.strip() or None,
                        )
                        st.success(
                            f"✅ {dto.full_name} added — {dto.classification} "
                            f"(Expertise Class {dto.expertise_class})."
                        )
                    except ValueError as e:
                        st.error(str(e))

    # ------------------------------------------------------------------
    # Tab 3 — statistics
    # ------------------------------------------------------------------

    @staticmethod
    def _render_statistics():
        techs = TechnicianService.get_all()

        if not techs:
            st.info("No technicians to display.")
            return

        st.subheader("Expertise Class Distribution")

        counts = Counter(t.classification for t in techs)
        display_order = ["Advanced", "Good", "Above Average", "Basic Knowledge", "Unknown"]
        data = {cls: counts[cls] for cls in display_order if cls in counts}

        st.bar_chart(data)

        summary = [{"Classification": cls, "Count": cnt} for cls, cnt in data.items()]
        st.dataframe(pd.DataFrame(summary), use_container_width=True, hide_index=True)
