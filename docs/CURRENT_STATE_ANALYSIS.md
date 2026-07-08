# Current State Analysis — Draexlmaier Scheduling System

**Date:** 2026-06-23  
**Analyst:** Claude Sonnet 4.6  
**Repository:** `draexlmaier_scheduling`  

---

## 1. Current Architecture

### Overview

The application is a single-user, single-process Streamlit web app. All pages are rendered from one entry point (`app.py`) using a sidebar radio-button navigation pattern. There is no REST API, no database, and no background worker — everything runs in the Streamlit request/response cycle.

### Directory Structure

```
draexlmaier_scheduling/
├── app.py                        # Entry point; hosts 4 of 5 pages as inline functions
├── config.py                     # Centralised constants and credentials
├── requirements.txt              # 3 dependencies: streamlit, pandas, openpyxl
├── .devcontainer/devcontainer.json
│
├── data/                         # Flat-file data store (CSV + XLSX)
│   ├── technicians_file.csv      # Master technician records (15 rows)
│   ├── products_classified.csv   # Product/SAP catalogue with routing times
│   ├── reclamations_file.xlsx    # Quality reclamation records
│   ├── blocked_orders.csv        # Empty — never written to
│   ├── current_schedule.csv      # Active schedule (persisted between sessions)
│   ├── unscheduled_orders.csv    # Orders that could not be auto-assigned
│   └── working_technicians.csv   # Snapshot of technicians for the current shift
│
├── models/                       # Data-access and domain objects
│   ├── orders.py                 # Order CRUD + `classify_order()`
│   ├── technicians.py            # Technician class + CRUD
│   ├── reclamations.py           # Reclamation class + CRUD
│   └── initial_scheduling.py     # Core scheduling algorithm (+ dead code)
│
├── services/                     # Business-logic layer
│   ├── auth_service.py           # Login / logout
│   ├── schedule_service.py       # Schedule mutations (status, reassign, priority)
│   ├── persistence_service.py    # Save/load CSV snapshots
│   └── file_service.py           # File initialisation + thin save/load wrappers
│
├── pages/
│   └── schedule_page.py          # `SchedulePage` class — the only extracted page
│
└── utils/
    ├── session_manager.py        # Wrapper around `st.session_state`
    ├── ui_components.py          # Shared Streamlit widgets
    └── validators.py             # Input validation helpers
```

### Layer Responsibilities

| Layer | Role | Coupling |
|---|---|---|
| `app.py` | Navigation shell + 4 inline page functions | Tightly coupled to every model and service |
| `models/` | Data-access: read/write flat files; domain classification logic | Depend only on `config.py` |
| `services/` | Business logic: scheduling algorithm coordination, auth, persistence | Depend on `models/` and `config.py` |
| `pages/` | One extracted Streamlit page class | Depends on `services/`, `utils/`, `config.py` |
| `utils/` | Cross-cutting: session state, UI helpers, validators | Depend on `config.py` and `streamlit` |

### Dependency Graph (simplified)

```
app.py
  ├── config.py
  ├── utils/session_manager.py → services/persistence_service.py
  ├── services/auth_service.py → utils/session_manager.py
  ├── services/file_service.py → config.py
  ├── services/schedule_service.py → config.py
  ├── models/orders.py
  ├── models/technicians.py
  ├── models/reclamations.py
  └── models/initial_scheduling.py → config.py
      └── (calls st.* directly — UI coupling in a model)
```

---

## 2. Existing Scheduling Algorithm

### Entry Point

`models/initial_scheduling.py` — `create_initial_schedule(technicians_df, orders_df)`

### Pre-processing Steps

1. **Priority normalisation** — `Priority` column values (`Urgent`, `A`, `B`, `C`, `None`) are mapped to integers (`0, 1, 2, 3, 999`). Orders are sorted ascending by priority integer, then descending by routing time within each priority bucket.
2. **Working-time calculation** (`calculate_working_time`) — Reads the master technician CSV and a per-shift Excel file. Technicians flagged `Working=yes` and `To another=no` are included. Available time formula: `480 + 30 − Break + Extra Time` (minutes). The `+30` adds the lunch break back in, though the intent is debatable.
3. **SAP validation** (`find_missing_sap_numbers`) — Checks every order's Material Number against `products_classified.csv`. If any are missing, the schedule generation is aborted and the user is asked to add them manually.
4. **Order enrichment** (`merge_orders_with_class_code`) — Joins the orders file with `products_classified.csv` to attach `routing time`, `Class` (Low/Medium/High/Very High), and `Class Code` (1–4).

### Three-Phase Assignment (active algorithm)

#### Phase 1 — Round-Robin Seeding
- Iterates orders in priority order.
- For each order, finds the first unassigned technician who has both sufficient expertise (`Expertise Class ≥ Class Code`) and sufficient remaining time.
- Stops when every technician has been assigned at least one order.
- Goal: prevent one technician from being overloaded while others sit idle.

#### Phase 2 — Balanced Priority Assignment
- Processes all orders not scheduled in Phase 1, maintaining priority order.
- For each order, collects all qualified technicians who still have time.
- Selects the technician with the **least total assigned time** (load-balancing), breaking ties by preferring an exact expertise match, then by most available time.
- Orders with no qualified technician are skipped (moved to unscheduled).

#### Phase 3 — Capacity Fill
- Processes remaining unscheduled orders.
- **Ignores expertise** — assigns to any technician with sufficient remaining time.
- Marks filled rows with `Remark = 'Capacity fill - may not match expertise'`.
- Goal: maximise schedule utilisation at the cost of expertise matching.

### Key Constraints

| Constraint | Enforcement |
|---|---|
| Expertise check | `technician_expertise[mat] >= order['Class Code']` (Phases 1 & 2 only) |
| Capacity check | `remaining_time >= order['routing time']` (all phases) |
| Priority ordering | Pre-sort before loop; not re-sorted during assignment |
| Single-day scope | `current_date = datetime.now().strftime('%Y-%m-%d')` — one schedule per run |

### In-Flight Schedule Mutations (`services/schedule_service.py`)

After the initial schedule is generated, the following mutations are available:

- **Status transitions** — `Planned → In Progress → Partially Completed → Completed` and `→ Blocked`. Each transition is guarded (e.g. cannot start a Completed order).
- **Work session tracking** — Timestamps are stored as a JSON array (`WorkSessions`) on each row: `[{"start": "ISO", "stop": "ISO"}, ...]`. `TotalTimeSpent` and `RemainingRoutingTime` are recalculated on each stop/end.
- **Technician reassignment** — Only for `Planned` orders; expertise check re-applied.
- **Priority change** — Re-sorts entire DataFrame; supports Urgent (0) with manual technician selection.
- **Routing time modification** — Only for `Planned` orders.
- **Blocked-order reassignment** (`initial_scheduling.py:reassign_blocked_order`) — Marks order blocked, tries to pull from unscheduled pool.

### Dead / Commented-Out Code

`initial_scheduling.py` lines 345–525 contain an older two-pass algorithm (Pass 1: exact expertise match; Pass 2: higher-or-equal expertise; Pass 3: any technician) wrapped in a multi-line `'''...'''` string. It is never executed. The active function above it replaced it.

---

## 3. Existing Data Storage Approach

### Storage Medium

**Flat files only** — no database. All data lives in the `data/` directory.

### File Inventory

| File | Format | Schema | Mutability |
|---|---|---|---|
| `technicians_file.csv` | CSV | `Matricule, Nom et prénom, Niveau 1–4, Classification, Expertise Class` | Full CRUD via UI |
| `products_classified.csv` | CSV | `SAP, Material Description, routing time, Class, Class Code` | Full CRUD + bulk upload via UI |
| `reclamations_file.xlsx` | Excel (openpyxl) | `Date, Ordre, SAP, Description, Qty, Reclamation, Remarque, Technicien, Decision, QS` | Full CRUD via UI |
| `blocked_orders.csv` | CSV | Empty — no schema defined | Never written |
| `current_schedule.csv` | CSV | 22 columns including `ScheduleRowID`, `WorkSessions` (JSON), timestamps | Written on every status change |
| `unscheduled_orders.csv` | CSV | Subset of orders schema | Written at schedule generation time |
| `working_technicians.csv` | CSV | `Matricule, Technician Name, Working, ..., Working Time, Expertise Class` | Written at schedule generation time |

### Read/Write Pattern

Every write is a **full DataFrame overwrite** — there is no append, patch, or transaction. For example, `save_orders()` does `df.to_csv(file_path, index=False)` which rewrites the entire file.

### In-Memory State

Streamlit's `st.session_state` acts as a runtime cache. The `SessionManager` class wraps it with typed getters/setters. Key session keys:

| Key | Content |
|---|---|
| `logged_in` | Boolean |
| `username` | String |
| `initial_schedule_df` | The active schedule DataFrame |
| `unscheduled_orders_df` | Unscheduled orders DataFrame |
| `working_technicians` | Working technicians DataFrame/list |
| `merged_orders` | Enriched orders after SAP merge |
| `bulk_results` | Last bulk-upload result dict |

### Persistence on Startup

`SessionManager._auto_load_schedule()` is called on every Streamlit cold start. It reads `current_schedule.csv`, `unscheduled_orders.csv`, and `working_technicians.csv` and populates session state, giving the appearance of persistence across page refreshes.

### Duplicate Save Logic

`FileService.save_schedule()` and `PersistenceService.save_schedule()` both write `current_schedule.csv`. `FileService` handles only the schedule; `PersistenceService` handles all three files. Both are called in different code paths, creating confusion about which is canonical.

---

## 4. Existing Authentication Implementation

### Mechanism

HTTP-session-based login using Streamlit's `st.session_state`. There are no tokens, cookies, JWTs, or server-side session stores.

### Credential Storage

Credentials are stored **in plain text** inside `config.py` as a Python dictionary:

```python
CREDENTIALS = {
    "admin": "app2024",
    "manager": "manager123",
    "user": "user123"
}
```

There is no hashing, no salting, and no `.env` or secrets file.

### Login Flow (`services/auth_service.py`)

1. `AuthService.require_login()` is called at the top of `main()`.
2. If `st.session_state.logged_in` is `False`, a login form is rendered and the rest of the app does not execute.
3. On form submission, `AuthService.login()` does a direct dictionary lookup: `Config.CREDENTIALS[username] == password`.
4. On success, `logged_in = True` and `username` are written to session state, then `st.rerun()` is called.

### Role System

Three named roles exist (`admin`, `manager`, `user`) but they are **not enforced anywhere in the UI**. All roles see the same pages and can perform the same actions.

### Security Issues

- Credentials are committed to version control in `config.py`.
- The help expander on the login page shows credentials publicly (`admin / draex2024` — note this differs from the actual configured password `app2024`, a copy-paste inconsistency).
- No brute-force protection, rate limiting, or account lockout.
- Session state is not signed — any user with developer tools can manipulate `st.session_state`.
- No HTTPS enforcement at the application level.

---

## 5. Existing Streamlit Pages

### Navigation

A sidebar `st.sidebar.radio()` with five options drives page selection. Four pages are inline functions in `app.py`; one is an extracted class in `pages/schedule_page.py`.

---

### Page 1 — Schedule Management (`pages/schedule_page.py`)

**Purpose:** View and interact with the active day's schedule.

**Sections:**
- **Edit Schedule** (expander): Three tabs — Change Technician, Change Priority, Modify Routing Time. All restricted to `Planned` orders.
- **Filters**: Multi-select widgets for Status, Technician, and Priority.
- **Statistics**: Metric cards showing counts per status.
- **Orders**: One `st.expander` per order showing details (material, technician, priority, work sessions), time tracking (planned vs. spent vs. remaining), status badge, and action buttons (Start / Stop / End / Resume).
- **Detailed Table**: Optional full DataFrame view.
- **Unscheduled Orders**: Shows orders not auto-assigned with a real-time technician availability table and manual assignment interface.

**Auto-save:** Every status change and edit calls `FileService.save_schedule()` immediately.

---

### Page 2 — Initial Scheduling (`app.py: render_initial_scheduling_page`)

**Purpose:** Upload input files and generate a new schedule.

**Flow:**
1. User uploads an Orders Excel file and a Shifts Excel file.
2. On "Generate Schedule", SAP numbers are validated against the products catalogue.
3. If validation passes, `merge_orders_with_class_code()` and `calculate_working_time()` run, then `create_initial_schedule()` produces the schedule.
4. Results are saved to session and to CSV via both `PersistenceService` and `FileService`.
5. A summary (scheduled count, unscheduled count, technician count, total time) is displayed.

**State:** If a schedule already exists in session or on disk, a preview is shown with a "Clear Schedule" button.

---

### Page 3 — Manage Technicians (`app.py: render_technicians_page`)

**Purpose:** CRUD operations on the technician master list.

**Sections:**
- Optional technician list display (checkbox-gated).
- Add, Modify, Delete sections in `st.expander` widgets.
- Statistics: bar chart of classification counts and `df.describe()`.

**Notable issue:** The page contains a placeholder comment: `"Copy your full manage_technicians() function code here from your old app.py"`, indicating this page was not fully migrated.

---

### Page 4 — Manage Orders (`app.py: render_orders_page`)

**Purpose:** CRUD on the products/SAP catalogue + bulk upload.

**Sections:**
- **Bulk Upload** (expander): Upload an Excel or CSV file. Processes rows: adds new products, updates changed routing times, skips unchanged. Results displayed in four tabs (Added / Modified / Skipped / Errors).
- **Current Products**: Searchable table (first 100 rows by default).
- **Manage Products**: Three tabs — Add, Modify (two-step: load then edit), Delete (checkbox-confirmed).
- **Statistics**: Metrics and bar chart of classification distribution.

**Classification logic:** Routing time thresholds → `Low (0–160 min)`, `Medium (160–320 min)`, `High (320–480 min)`, `Very High (480+ min)`. Classification is auto-computed on save.

---

### Page 5 — Manage Reclamations (`app.py: render_reclamations_page`)

**Purpose:** CRUD on quality reclamation records.

**Sections:**
- Toggle to show/hide the reclamations table.
- Add, Modify, Delete sections in expanders.
- Recommendations section.

**Critical bug:** The `render_reclamations_page()` function calls `generate_recommendations(reclamations)` at line 847 of `app.py`, but this function is **never defined or imported** anywhere in the codebase. This will raise a `NameError` at runtime whenever the Reclamations page is visited. Additionally, `add_reclamation`, `modify_reclamation`, and `delete_reclamation` in `models/reclamations.py` have hardcoded relative paths (`'../data/reclamations_file.xlsx'`) and mismatched function signatures — the model functions take fewer arguments than the UI passes.

---

## 6. Technical Debt

### Critical (Will Cause Runtime Errors)

| Issue | Location | Impact |
|---|---|---|
| `generate_recommendations()` undefined | `app.py:847` | `NameError` crash on Reclamations page visit |
| `add_reclamation` / `modify_reclamation` / `delete_reclamation` in `models/reclamations.py` use hardcoded relative paths and differ in signature from how `app.py` calls them | `models/reclamations.py:51–79`, `app.py:811,831,841` | Reclamation CRUD operations fail |
| `blocked_orders.csv` is defined in `Config` and initialised as empty but never written | `config.py:11`, `services/file_service.py` | Blocked-order persistence is silently dropped |

### High (Functional Gaps / Silent Failures)

| Issue | Location | Impact |
|---|---|---|
| Credentials stored in plain text in version control | `config.py:19–23` | Security exposure |
| Login help expander displays wrong password (`draex2024` vs actual `app2024`) | `services/auth_service.py:50–55` | User confusion |
| `find_missing_sap_numbers()` calls `st.warning()` / `st.write()` inside a model function | `models/initial_scheduling.py:22–26` | Model layer is coupled to Streamlit; untestable |
| `calculate_working_time()` uses deprecated `fillna(inplace=True)` | `models/initial_scheduling.py:56–57` | FutureWarning; will break in future pandas |
| Working-time formula `480 + 30 - Break + Extra Time` adds 30 minutes unexpectedly | `models/initial_scheduling.py:58` | Technicians appear to have 510 min base capacity instead of 480 |
| Duplicate save code: both `FileService` and `PersistenceService` write `current_schedule.csv` | `services/file_service.py:27–33`, `services/persistence_service.py:14–16` | Race conditions possible; unclear which is authoritative |
| Phase 3 of scheduling ignores expertise and can assign high-complexity orders to unqualified technicians with no UI warning | `models/initial_scheduling.py:253–301` | Incorrect assignments silently enter the schedule |

### Medium (Maintainability / Code Quality)

| Issue | Location | Impact |
|---|---|---|
| 180 lines of dead algorithm code in a `'''...'''` string | `models/initial_scheduling.py:345–525` | Reader confusion; accidental reactivation risk |
| Four of five pages are inline functions in `app.py` (855 lines total) | `app.py` | File is difficult to navigate and test |
| `Technician.classify_technician()` returns wrong class when two skill levels are equal (takes `max` then compares equality) | `models/technicians.py:16–29` | Skill misclassification for edge cases |
| `process_bulk_orders()` is a 100-line pure-processing function defined at module level inside `app.py` with `from models.orders import ...` inside a loop | `app.py:22–103` | Should be in a service; repeated imports per row are expensive |
| Session state keys are untyped string literals scattered across multiple files | Throughout | No central registry; typos cause silent `None` returns |
| `Validators` class exists but is only used once (`utils/validators.py`) | Throughout | Validation is largely ad-hoc inline |
| `modules/__init__.py` and `data/__init__.py` are empty; `pages/__init__.py` is present — Python packaging is inconsistent | Package files | Confusion about whether this is a package or scripts |
| `working_technicians.csv` stores a snapshot at generation time; it is never refreshed when technician data changes | `services/persistence_service.py` | Stale technician records used in reassignment UI |
| Schedule is scoped to a single date (`datetime.now()`) with no date selection; re-generating on a different day silently overwrites the previous day | `models/initial_scheduling.py:103` | No historical record keeping |
| UTF-8 encoding issue in `technicians_file.csv` — names appear with garbled characters (`Nom et prÃ©nom`) | `data/technicians_file.csv` | Display corruption for accented characters |

### Low (Style / Minor)

| Issue | Location |
|---|---|
| `print()` statements used for logging throughout (30+ occurrences) | `models/initial_scheduling.py`, `services/` |
| Comments like `# ✅ ADD THIS NEW LINE` and `# ⚠️ CHANGE THESE PASSWORDS!` left in production code | `config.py` |
| `cumulative_scheduled_orders` global variable declared but never used | `models/initial_scheduling.py:8` |
| `Schedule_page.py` has a second `render()` method body commented out with `'''...'''` | `pages/schedule_page.py:54–90` |
| Inconsistent French/English column naming (`Nom et prénom`, `Matricule` vs English elsewhere) | Throughout |

---

## 7. Missing Components

### Functional Gaps

| Missing Feature | Evidence of Gap |
|---|---|
| **`generate_recommendations()`** — called but never implemented | `app.py:847` |
| **Blocked-order tracking** — `blocked_orders.csv` exists in config but is never written; `mark_as_blocked()` exists in `ScheduleService` but the UI has no "Block" button in the order cards | `config.py:11`, `services/schedule_service.py:244` |
| **Role-based access control** — three roles exist but no page or action checks the current user's role | `config.py:19–23` |
| **Date-range scheduling** — the system only schedules for "today"; there is no multi-day view or calendar | `models/initial_scheduling.py:103` |
| **Schedule export** — no download button for the generated schedule (PDF, Excel, etc.) | Throughout |
| **Audit trail** — no log of who changed what and when; `username` is in session but never recorded on mutations | Throughout |
| **Reclamation CRUD** — effectively non-functional due to path and signature bugs | `models/reclamations.py:51–79` |
| **Historical schedule archive** — overwriting the same CSV means previous days' schedules are lost | `services/persistence_service.py` |
| **Technician availability from multiple shifts** — the shift file is uploaded fresh each time with no stored shift history | `models/initial_scheduling.py:50–59` |

### Infrastructure Gaps

| Missing Component | Current State |
|---|---|
| **Real database** | Flat CSV/XLSX files; no ACID guarantees, no concurrent access |
| **Secrets management** | Passwords in `config.py`; no `.env`, no Streamlit secrets |
| **Test suite** | Zero test files exist in the repository |
| **CI/CD pipeline** | No GitHub Actions or other automation |
| **Logging framework** | `print()` only; no structured logging, no log rotation |
| **Error monitoring** | No Sentry or equivalent integration |
| **Docker / deployment config** | Only a `.devcontainer` config (Codespaces/dev use); no production deployment manifest |

### UX Gaps

| Missing Feature | Current State |
|---|---|
| **Confirmation dialogs** before irreversible actions (delete technician, clear schedule) | Delete technician has no confirmation; clear schedule has a button with no confirmation |
| **Undo / revert** | No mechanism to undo a schedule change |
| **Technician workload visualisation** | No Gantt chart or utilisation bar chart on the schedule page |
| **Search in schedule** | Orders can only be filtered; no free-text search |
| **Notifications** | No alerts when an order is overdue or a technician exceeds capacity |

---

## Summary Scorecard

| Area | Status |
|---|---|
| Core scheduling algorithm | Functional, but has expertise-bypass in Phase 3 and no multi-day support |
| Data persistence | Works for single-user, single-session use; not production-safe |
| Authentication | Functional but critically insecure (plaintext passwords in VCS) |
| Schedule Management page | Most complete page; auto-save works |
| Initial Scheduling page | Functional end-to-end |
| Technicians page | Partially migrated; functional CRUD but incomplete |
| Orders page | Fully functional including bulk upload |
| Reclamations page | **Non-functional** — crashes at runtime due to missing function and path bugs |
| Test coverage | 0% |
| Production readiness | Not production-ready — requires database, secrets management, and test coverage at minimum |
