import traceback
from datetime import datetime

import pandas as pd
import streamlit as st

from services.auth_service import AuthService
from services.order_service import OrderService


def _dtos_to_df(products) -> pd.DataFrame:
    return pd.DataFrame([
        {
            "SAP": p.sap_number,
            "Material Description": p.description,
            "routing time": p.routing_time_minutes,
            "Class": p.classification,
            "Class Code": p.class_code,
        }
        for p in products
    ])


class OrdersPage:

    @staticmethod
    def render():
        if not AuthService.require_role('manager', 'admin'):
            return

        st.header("📦 Manage Orders (Products)")

        products = OrderService.get_all_products()
        df_orders = _dtos_to_df(products)
        st.success(f"✅ Loaded {len(df_orders)} products")

        # ===== BULK UPLOAD SECTION =====
        st.markdown("---")
        st.markdown("### 📤 Bulk Upload Orders")

        with st.expander("📂 Upload Orders File (Excel/CSV)", expanded=False):
            st.info("""
            **📋 Required Columns:**
            - `Material Number` (or `SAP`) - Product identifier
            - `Material description` (or `Material Description`) - Product name
            - `routing time` (or `Routing Time`) - Time in minutes

            **Optional Columns:**
            - `Order` (or `Order ID`) - Order number (not stored in products file)
            - `Priority` - Order priority (not stored in products file)

            **How it works:**
            - ✅ **New products** → Added to database
            - 🔄 **Existing products with different routing time** → Updated
            - ⏭️ **Existing products with same routing time** → Skipped
            """)

            uploaded_file = st.file_uploader(
                "Upload Orders File",
                type=['xlsx', 'xls', 'csv'],
                key="bulk_orders_upload",
                help="Excel or CSV file with Material Number, Material Description, and Routing Time"
            )

            if uploaded_file:
                try:
                    if uploaded_file.name.endswith('.csv'):
                        uploaded_df = pd.read_csv(uploaded_file)
                    else:
                        uploaded_df = pd.read_excel(uploaded_file, engine='openpyxl')

                    st.success(f"✅ Loaded {len(uploaded_df)} orders from file")

                    st.markdown("#### 📋 File Preview (first 10 rows)")
                    st.dataframe(uploaded_df.head(10), use_container_width=True)

                    required_cols = ['Material Number', 'Material number', 'SAP', 'material number']
                    has_material = any(col in uploaded_df.columns for col in required_cols)

                    time_cols = ['routing time', 'Routing Time', 'Routing time']
                    has_routing_time = any(col in uploaded_df.columns for col in time_cols)

                    if not has_material:
                        st.error("❌ Missing required column: 'Material Number' or 'SAP'")
                    elif not has_routing_time:
                        st.error("❌ Missing required column: 'routing time' or 'Routing Time'")
                    else:
                        st.success("✅ File format validated")

                        st.markdown("---")
                        col1, col2, col3 = st.columns([1, 2, 1])
                        with col2:
                            if st.button("🚀 Process Orders", type="primary",
                                         use_container_width=True, key="btn_process_bulk"):
                                with st.spinner("⏳ Processing orders..."):
                                    result = OrderService.bulk_upsert_products(uploaded_df)
                                    result['timestamp'] = datetime.now()
                                    st.session_state['bulk_results'] = result
                                    st.success("✅ Processing complete! See results below.")
                                    st.rerun()

                except Exception as e:
                    st.error(f"❌ Error reading file: {str(e)}")
                    st.markdown("**Error Details:**")
                    st.code(traceback.format_exc())

        # ===== BULK UPLOAD RESULTS =====
        if 'bulk_results' in st.session_state:
            results = st.session_state['bulk_results']
            added = results['added']
            modified = results['modified']
            skipped = results['skipped']
            errors = results['errors']

            st.markdown("---")
            st.markdown("### 📊 Bulk Upload Results")
            st.info(f"Processed at: {results['timestamp'].strftime('%Y-%m-%d %H:%M:%S')}")

            col_a, col_b, col_c, col_d = st.columns(4)
            with col_a:
                st.metric("✅ Added", len(added))
            with col_b:
                st.metric("🔄 Modified", len(modified))
            with col_c:
                st.metric("⏭️ Skipped", len(skipped))
            with col_d:
                st.metric("❌ Errors", len(errors))

            if added or modified or skipped or errors:
                t1, t2, t3, t4 = st.tabs([
                    f"✅ Added ({len(added)})",
                    f"🔄 Modified ({len(modified)})",
                    f"⏭️ Skipped ({len(skipped)})",
                    f"❌ Errors ({len(errors)})",
                ])
                with t1:
                    st.dataframe(pd.DataFrame(added), use_container_width=True, hide_index=True) if added else st.info("No products were added")
                with t2:
                    st.dataframe(pd.DataFrame(modified), use_container_width=True, hide_index=True) if modified else st.info("No products were modified")
                with t3:
                    if skipped:
                        st.info("These products already exist with the same routing time")
                        display = skipped if len(skipped) <= 50 else skipped[:50]
                        st.dataframe(pd.DataFrame(display), use_container_width=True, hide_index=True)
                        if len(skipped) > 50:
                            st.write(f"Showing first 50 of {len(skipped)} skipped items.")
                    else:
                        st.info("No products were skipped")
                with t4:
                    if errors:
                        for error in errors:
                            st.error(error)
                    else:
                        st.success("No errors occurred")

            col_clear1, col_clear2, col_clear3 = st.columns([1, 1, 1])
            with col_clear2:
                if st.button("🗑️ Clear Results", key="clear_bulk_results", use_container_width=True):
                    del st.session_state['bulk_results']
                    st.rerun()

            if len(added) + len(modified) > 0:
                st.success(f"✅ Successfully processed {len(added) + len(modified)} products!")

        # ===== DISPLAY ORDERS =====
        st.markdown("---")
        st.markdown("### 📋 Current Products")

        col1, col2 = st.columns([2, 1])
        with col1:
            search_term = st.text_input("🔍 Search by SAP or Description", "")
        with col2:
            show_all = st.checkbox("Show All Products", value=False)

        if search_term:
            filtered_df = df_orders[
                df_orders['SAP'].astype(str).str.contains(search_term, case=False, na=False) |
                df_orders['Material Description'].astype(str).str.contains(search_term, case=False, na=False)
            ]
            st.info(f"Found {len(filtered_df)} matching products")
        else:
            filtered_df = df_orders

        if show_all:
            st.dataframe(filtered_df, use_container_width=True, hide_index=True)
        else:
            st.dataframe(filtered_df.head(100), use_container_width=True, hide_index=True)
            if len(filtered_df) > 100:
                st.info(f"Showing first 100 of {len(filtered_df)} products. Check 'Show All Products' to see all.")

        # ===== MANAGE PRODUCTS =====
        st.markdown("---")
        st.markdown("### ⚙️ Manage Products")

        tab1, tab2, tab3 = st.tabs(["➕ Add Product", "✏️ Modify Product", "🗑️ Delete Product"])

        # ===== ADD =====
        with tab1:
            st.markdown("#### Add New Product")
            st.info("💡 Classification is automatic: Low (0-160min), Medium (160-320min), High (320-480min), Very High (480+min)")

            col1, col2 = st.columns(2)
            with col1:
                add_sap = st.text_input("SAP Number*", key="add_sap")
                add_description = st.text_input("Material Description*", key="add_description")
            with col2:
                add_routing_time = st.number_input("Routing Time (minutes)*", min_value=1,
                                                   max_value=10000, value=60, key="add_routing_time")
                preview_class, preview_code = OrderService.classify(add_routing_time)
                st.info(f"📊 Classification Preview: **{preview_class}** (Level {preview_code})")

            st.markdown("---")
            if st.button("➕ Add Product", type="primary", use_container_width=True, key="btn_add_order"):
                if not add_sap or not add_description:
                    st.error("❌ SAP Number and Material Description are required")
                else:
                    try:
                        OrderService.add_product(add_sap.strip(), add_description.strip(), add_routing_time)
                        st.success(f"✅ Product {add_sap} added successfully!")
                        st.balloons()
                        st.rerun()
                    except ValueError as e:
                        st.error(f"❌ {e}")
                    except Exception as e:
                        st.error(f"❌ Error adding product: {e}")

        # ===== MODIFY =====
        with tab2:
            st.markdown("#### Modify Existing Product")

            col1, col2 = st.columns([1, 2])
            with col1:
                modify_sap = st.text_input("SAP Number to Modify*", key="modify_sap")
                if modify_sap and st.button("🔍 Load Product", key="btn_load_order"):
                    match = next((p for p in products if p.sap_number == str(modify_sap).strip()), None)
                    if match:
                        st.session_state['modify_loaded'] = True
                        st.session_state['modify_existing'] = match
                        st.success(f"✅ Loaded: {match.description}")
                    else:
                        st.error(f"❌ SAP {modify_sap} not found")
                        st.session_state['modify_loaded'] = False

            with col2:
                if st.session_state.get('modify_loaded', False):
                    existing = st.session_state['modify_existing']
                    st.markdown("**Current Values:**")
                    st.write(f"• Description: {existing.description}")
                    st.write(f"• Routing Time: {existing.routing_time_minutes} min")
                    st.write(f"• Class: {existing.classification} (Level {existing.class_code})")

            if st.session_state.get('modify_loaded', False):
                existing = st.session_state['modify_existing']
                st.markdown("---")
                st.markdown("**New Values:**")
                col_a, col_b = st.columns(2)
                with col_a:
                    new_description = st.text_input("New Material Description*",
                                                    value=existing.description, key="new_description")
                with col_b:
                    new_routing_time = st.number_input("New Routing Time (minutes)*", min_value=1,
                                                       max_value=10000,
                                                       value=int(existing.routing_time_minutes),
                                                       key="new_routing_time")
                    new_class, new_code = OrderService.classify(new_routing_time)
                    st.info(f"📊 New Classification: **{new_class}** (Level {new_code})")

                st.markdown("---")
                if st.button("✏️ Update Product", type="primary", use_container_width=True, key="btn_modify_order"):
                    if not new_description:
                        st.error("❌ Material Description is required")
                    else:
                        try:
                            OrderService.modify_product(existing.sap_number, new_description, new_routing_time)
                            st.success(f"✅ Product {existing.sap_number} updated successfully!")
                            st.session_state['modify_loaded'] = False
                            st.balloons()
                            st.rerun()
                        except ValueError as e:
                            st.error(f"❌ {e}")
                        except Exception as e:
                            st.error(f"❌ Error modifying product: {e}")

        # ===== DELETE =====
        with tab3:
            st.markdown("#### Delete Product")
            st.warning("⚠️ This action cannot be undone!")

            col1, col2 = st.columns([1, 2])
            with col1:
                delete_sap = st.text_input("SAP Number to Delete*", key="delete_sap")
                if delete_sap and st.button("🔍 Check Product", key="btn_check_delete"):
                    match = next((p for p in products if p.sap_number == str(delete_sap).strip()), None)
                    if match:
                        st.session_state['delete_loaded'] = True
                        st.session_state['delete_existing'] = match
                        st.info(f"Found: {match.description}")
                    else:
                        st.error(f"❌ SAP {delete_sap} not found")
                        st.session_state['delete_loaded'] = False

            with col2:
                if st.session_state.get('delete_loaded', False):
                    existing = st.session_state['delete_existing']
                    st.markdown("**Product Details:**")
                    st.write(f"• SAP: {existing.sap_number}")
                    st.write(f"• Description: {existing.description}")
                    st.write(f"• Routing Time: {existing.routing_time_minutes} min")
                    st.write(f"• Class: {existing.classification}")

            if st.session_state.get('delete_loaded', False):
                existing = st.session_state['delete_existing']
                st.markdown("---")
                col_confirm1, col_confirm2, col_confirm3 = st.columns([1, 2, 1])
                with col_confirm2:
                    confirm_delete = st.checkbox(f"⚠️ I confirm deletion of SAP {existing.sap_number}",
                                                 key="confirm_delete")
                    if confirm_delete:
                        if st.button("🗑️ DELETE PRODUCT", type="primary",
                                     use_container_width=True, key="btn_delete_order"):
                            try:
                                OrderService.remove_product(existing.sap_number)
                                st.success(f"✅ Product {existing.sap_number} deleted successfully!")
                                st.session_state['delete_loaded'] = False
                                st.rerun()
                            except ValueError as e:
                                st.error(f"❌ {e}")
                            except Exception as e:
                                st.error(f"❌ Error deleting product: {e}")

        # ===== STATISTICS =====
        st.markdown("---")
        st.markdown("### 📊 Product Statistics")

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total Products", len(df_orders))
        with col2:
            avg_time = df_orders['routing time'].mean()
            st.metric("Avg Routing Time", f"{avg_time:.1f} min")
        with col3:
            if 'Class' in df_orders.columns and not df_orders['Class'].isna().all():
                most_common = df_orders['Class'].value_counts().index[0]
                st.metric("Most Common Class", most_common)
        with col4:
            max_time = df_orders['routing time'].max()
            st.metric("Max Routing Time", f"{max_time:.0f} min")

        if 'Class' in df_orders.columns:
            st.markdown("#### 📈 Classification Distribution")
            st.bar_chart(df_orders['Class'].value_counts())
