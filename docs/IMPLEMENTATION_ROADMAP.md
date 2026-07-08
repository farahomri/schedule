# DASS — Implementation Roadmap

**Project:** Draexlmaier Automated Scheduling System  
**Date:** 2026-06-23  
**Architecture reference:** `TARGET_ARCHITECTURE_V2.md` (single source of truth)  
**Supersedes:** Phase Roadmap in `TARGET_ARCHITECTURE_V2.md` Section 16

---

## How to Read This Document

Each phase is broken into numbered milestones. Each milestone is broken into concrete tasks.
Every task states what to do, why it is needed, what it depends on, and how to verify it is
complete. No task is optional within its phase unless marked **[optional]**.

**Golden rule:** every milestone must end with the application in a fully working state.
New code is written alongside old code, verified to produce identical results, and then old
code is removed. The application is never in a broken intermediate state between milestones.

**Scope discipline:** The product vision says the priority is making what exists work correctly,
not adding features. Tasks that go beyond this are marked **[Phase 2+]** and excluded from
the current roadmap.

---

## Guiding Principles

1. **Working application first.** A running app with CSV storage is better than a half-migrated
   app with a broken DB layer. Complete each milestone fully before starting the next.

2. **Preserve algorithm behavior.** The three-phase scheduling algorithm must produce identical
   results before and after every refactoring step. If the output changes, the refactoring is
   wrong.

3. **Resolve open questions before coding.** The five open questions in V2 Section 18 are
   listed at the end of this document. The questions blocking a milestone must be answered
   before that milestone begins.

4. **One direction of communication per layer.** Streamlit calls services. Services call
   repositories. Repositories call the database. No layer skips another. No service reads
   `st.session_state`. This is enforced from the first line of Phase 1 code.

5. **Incremental, not rewrite.** Files are edited in place. Behaviour is preserved. The word
   "replace" means: write the new version, verify it works, then delete the old version.

---

## Flowchart Alignment

The full system behavior is defined in `docs/FLOWCHART.md`. Every element in the flowchart
is mapped below to its implementation phase. Elements not listed here are out of scope for
all phases in this roadmap.

| Flowchart Element | Phase | Notes |
|---|---|---|
| Weekly cycle: Monday start (new orders) vs. daily continuation | Phase 1 | Two-mode `InitialSchedulingPage` (Task 1.5.7) |
| Upload orders file + merge late/unstarted orders from previous days | Phase 1 | `OrderService.get_late_orders()` (Task 1.5.3) |
| In-progress order carryover (same tech or replacement) | Phase 1 | New `DailyOrderPoolService` (Task 1.5.4) |
| Blocked order carryover and manager-unblock re-entry | Phase 1 | New `DailyOrderPoolService` (Task 1.5.4) |
| Shift upload OR inline edit of yesterday's displayed shift | Phase 1 | `ShiftService.get_previous_shift()` (Task 1.5.2) |
| Round 1: Round-robin, one order per technician, expertise enforced | Phase 1 | Preserved exactly in `SchedulingService` (Task 1.5.5) |
| Rounds 2 & 3: Capacity fill — "Expertise adequate" in both rounds | Phase 1 | **Resolved 2026-06-30:** label applies to Round 2 only; Round 3 ignores expertise as a last-resort fallback, matching V2's original design — see note below |
| Technician START / STOP / BLOCK / END actions | Phase 1 | Milestone 1.6 (`ScheduleService`) |
| Auto-load previous day state from database | Phase 1 | Task 1.7.4 (SessionManager) |
| End-of-day state save and daily statistics | Phase 1 | Milestones 1.6 + 1.7 |
| FST Department Interface (real-time view, comments, priority changes) | Phase 2 | Requires a new `fst` user role |
| Urgent priority interrupt process (manager stops a technician) | Phase 2 | Manager interrupt workflow |
| Weekly reports (completion rates, technician rankings, bottleneck analysis) | Phase 2 | Historical reporting page |
| Order update processing (compare new upload vs. existing pool) | Phase 1 | `OrderService.save_production_orders()` idempotent upsert (Task 1.5.3) |
| Workplace assignment (welding, assembly, paint, testing) | **Explicitly deferred** | Not in V2 schema; adds a new `workplaces` table, availability tracking, and scheduling constraint changes. When added, requires its own Alembic migration and scheduling algorithm update. |
| Order splitting (parent → child orders ORD-001-A / ORD-001-B) | **Phase 3** | V2 Open Question 5; product owner approved V2 with Phase 3 deferral. Schema preparation: `production_orders` will need `parent_order_id FK` and `is_split_child BOOLEAN` columns before Phase 3 begins — no schema change needed in Phase 1. |

**Resolved — Rounds 2 & 3 and expertise (2026-06-30):**
The flowchart's "Expertise adequate" label on the combined "ROUND 2 & 3: CAPACITY FILL" step
is read as describing Round 2 (the preferred, expertise-matched path), not a hard requirement
on Round 3. The product owner confirmed Round 3 keeps the original V2 behavior: ignore
expertise and assign automatically to any technician with sufficient remaining time. Leaving
an order unscheduled while a technician is idle blocks production, which is judged worse than
a flagged expertise mismatch. `is_expertise_override` captures and surfaces every such
assignment without gating or delaying it. This reconciles the flowchart with
`TARGET_ARCHITECTURE_V2.md` Section 9 and Section 18 (Decisions 2 and 6).

---

## Current State Summary

| Area | Status |
|---|---|
| Schedule Management page | Working |
| Initial Scheduling page | Working |
| Manage Technicians page | Working (partially migrated) |
| Manage Orders page | Working (full CRUD + bulk upload) |
| Reclamations page | **Crashes at runtime** — deferred to advanced level |
| Authentication | Works, but passwords are plaintext in `config.py` |
| Data storage | Flat CSV / XLSX files — no database |
| Service layer | Coupled to DataFrames and `st.session_state` |
| Dead code | 180-line commented-out algorithm, unused globals, duplicate save paths |
| Test coverage | Zero |

---

## Phase 0 — Stabilise

**Goal:** Eliminate all runtime crashes and structural debt from the existing CSV-based
application. No database work. No new features. Deliver a clean, stable, four-page
application as the starting baseline for Phase 1.

**Exit criterion:** All four active pages (Schedule Management, Initial Scheduling,
Manage Technicians, Manage Orders) run without runtime errors on every code path.
The Reclamations page is not reachable from the navigation.

---

### Task P0.1 — Remove Reclamations From Navigation

**What:** In `app.py`, remove `"⚠️ Manage Reclamations": render_reclamations_page` from
the `pages` dictionary. Do not delete `render_reclamations_page()` — only remove it from
the navigation map.

**Why:** The function calls `generate_recommendations()`, which is never defined anywhere
in the codebase. Any visit to this page raises a `NameError` and crashes. Since Reclamations
is fully deferred to advanced level (per product owner decision 2026-06-23), the fastest
safe fix is to make the page unreachable rather than repairing broken code that will be
rewritten later.

**Depends on:** Nothing.

**Enables:** P0.2 through P0.7 can proceed with a stable app.

**Verify:** Running the app shows exactly four navigation options. Navigating to all four
produces no error.

---

### Task P0.2 — Move Credentials Out of Source Code

**What:** Replace the `CREDENTIALS` dictionary in `config.py` with reads from environment
variables. Add `ADMIN_PASSWORD`, `MANAGER_PASSWORD`, `USER_PASSWORD` to a `.env` file
(for local development) and to Streamlit secrets (`secrets.toml`) for deployment. Add
both files to `.gitignore`. Update `AuthService.login()` to read from the environment
values instead of the dictionary.

**Why:** Three plaintext passwords are committed to version control. Anyone with repository
access can read them. This is the highest-severity security issue in the current codebase.
Additionally, the help expander on the login page displays `admin / draex2024` while the
actual configured password is `app2024` — a copy-paste inconsistency that must be corrected
at the same time.

**Depends on:** P0.1 (app must be stable before touching auth).

**Enables:** Safe to commit and share the codebase. Pre-condition for the DB users table
in Phase 1.

**Verify:** Running `grep -r "app2024\|manager123\|user123" config.py` returns no results.
Login still works for all three roles using credentials from the environment.

---

### Task P0.3 — Collapse the Duplicate Save Path

**What:** `FileService.save_schedule()` and `PersistenceService.save_schedule()` both write
`current_schedule.csv`. Designate `PersistenceService` as the single canonical save path
(it handles all three schedule files). Remove `FileService.save_schedule()` and
`FileService.load_schedule()`. Update every call site in `pages/schedule_page.py` and
`app.py` to use `PersistenceService` instead. Retain `FileService.initialize_all_files()`
and `FileService.ensure_data_directory()` — these are still needed for CSV-based Phase 0.

**Why:** Two code paths writing the same file is a maintenance hazard and creates potential
race conditions. It also means that tracing "where does the schedule get saved?" requires
reading two files. Having one authoritative path makes Phase 1's replacement of the save
layer straightforward.

**Depends on:** P0.1.

**Enables:** Clear, single point of replacement in Phase 1 Milestone 1.7.

**Verify:** Generating a schedule, modifying an order status, and restarting the app all
preserve the schedule correctly. Only `PersistenceService` writes to `current_schedule.csv`.

---

### Task P0.4 — Remove Streamlit Calls From the Model Layer

**What:** In `models/initial_scheduling.py`, `find_missing_sap_numbers()` currently calls
`st.warning()` and `st.write()` directly. Remove these calls. Return only the list of
missing SAP numbers (or `None`). Move the display logic to the caller in
`app.py` (the Initial Scheduling page function), which is the correct layer for UI output.

Also fix the deprecated `fillna(inplace=True)` calls in `calculate_working_time()`. Replace
with the assignment form: `df['column'] = df['column'].fillna(0)`.

**Why:** A model function that calls Streamlit is untestable outside of a running Streamlit
server. When services become stateless in Phase 1, this coupling would block the refactoring.
The deprecated `inplace` usage generates `FutureWarning` and will break in a future pandas
version.

**Depends on:** P0.1.

**Enables:** Model functions are unit-testable. Pre-condition for stateless services in Phase 1.

**Verify:** The Initial Scheduling page still displays the missing SAP warning correctly.
The console shows no `FutureWarning` about `fillna`.

---

### Task P0.5 — Delete Dead Code

**What:** Delete the following from `models/initial_scheduling.py`:
- The 180-line commented-out algorithm wrapped in `'''...'''` (lines 345–525).
- The unused `cumulative_scheduled_orders = set()` global variable at line 8.

Delete the following from `pages/schedule_page.py`:
- The second `render()` method body wrapped in `'''...'''` (lines 54–90).

**Why:** Commented-out code is not documentation — it is noise. It creates the risk of
accidental reactivation, confuses readers about which version is active, and inflates file
size. The old algorithm is preserved in git history if ever needed. The unused global
silently holds memory and misleads readers about the algorithm's state tracking.

**Depends on:** P0.4 (confirm the active algorithm works correctly before deleting the old one).

**Enables:** Cleaner codebase for Phase 1 refactoring.

**Verify:** Schedule generation produces the same results as before. `git diff` shows only
deletions, no behavior changes.

---

### Task P0.6 — Extract Inline Page Functions From `app.py`

**What:** `app.py` currently contains four inline page functions: `render_initial_scheduling_page()`,
`render_technicians_page()`, `render_orders_page()`, and `render_reclamations_page()` (already
disconnected in P0.1). Create the following files following the pattern of the already-extracted
`pages/schedule_page.py`:

- `pages/initial_scheduling_page.py` → class `InitialSchedulingPage` with `render()`.
- `pages/technicians_page.py` → class `TechniciansPage` with `render()`.
- `pages/orders_page.py` → class `OrdersPage` with `render()`.

**Caveat — `technicians_page.py` is not a pure extraction:** `CURRENT_STATE_ANALYSIS.md`
confirms `render_technicians_page()` is a placeholder containing the literal comment "Copy
your full manage_technicians() function code here from your old app.py" — there is no working
implementation to extract. Confirmed by the product owner 2026-06-30: this page must be
**built**, not copied. For Phase 0, create `TechniciansPage.render()` with the minimum needed
to view the technician list read-only from the existing CSV/dict source, so the page no longer
crashes. Add/edit/delete technician functionality is real implementation work and belongs in
Milestone 1.3 (`TechniciansPage` backed by `TechnicianService`, Task 1.3.4), not in this task.

Move `process_bulk_orders()` from `app.py` into `pages/orders_page.py` as a private static
method `_process_bulk_upload()`. It belongs in the page class until Phase 1 promotes it to
`OrderService`.

Update `app.py` to import these classes and call `ClassName.render()` in the navigation
dispatch. The resulting `app.py` should contain only the navigation shell, `main()`, and no
page logic.

**Why:** An 855-line entry point that contains four full page implementations is unnavigable.
`SchedulePage` already demonstrates the correct pattern. Consistency across all pages is
required before Phase 1 adds service and repository layers beneath them.

**Depends on:** P0.5 (dead code removed so the extraction is clean).

**Enables:** Each page file is independently navigable. Phase 1 can refactor one page at a
time without touching the others.

**Verify:** `InitialSchedulingPage`, `OrdersPage`, and `SchedulePage` render identically to
before. `TechniciansPage` renders a working read-only technician list (previously crashed or
was unimplemented — this is an improvement, not identical behavior). `app.py` has no inline
page rendering logic.

---

### Phase 0 Completion Checklist

Before moving to Phase 1, confirm:

- [ ] Four pages accessible, zero crashes on any page.
- [ ] Reclamations not reachable from navigation.
- [ ] No passwords in `config.py` or any tracked file.
- [ ] One save path (`PersistenceService`) for the schedule.
- [ ] No `st.*` calls in `models/`.
- [ ] No `FutureWarning` in the console.
- [ ] No commented-out code blocks.
- [ ] `app.py` contains only navigation logic.
- [ ] All page logic lives in `pages/` classes.

---

## Phase 1 — Database Migration

**Goal:** Replace all flat-file storage with PostgreSQL. Introduce the full four-layer
architecture (Streamlit → Service → Repository → Database). Add bcrypt authentication
with role enforcement. The application at the end of Phase 1 is functionally identical to
Phase 0 but reads and writes a database instead of CSV files, except for `TechniciansPage`
(Task 1.3.4), which is genuinely new since no working version exists today.

**Exit criterion:** The application runs with no CSV files present in `data/`. All pages
work correctly. All writes go to PostgreSQL. Authentication uses bcrypt against the `users`
table. Role-based access is enforced on every page.

**Prerequisite:** Of the six open questions in `TARGET_ARCHITECTURE_V2.md` Section 18,
questions 1, 2, and 6 were resolved by the product owner on 2026-06-30 (see Open Questions
section below) and no longer block any milestone. Questions 3, 4, and 5 remain open; 3 and 4
must be answered before Milestones 1.7 and 1.2 respectively, and 5 does not block coding (the
atomic default applies).

**No PostgreSQL instance exists yet.** It is provisioned from scratch in Task 1.1.0 below —
it is not a pre-existing dependency.

### Phase 1 Test Strategy

Phase 2's "comprehensive test suite" does not mean Phase 1 ships untested. Each milestone
below writes the tests for the code it introduces, scoped to what actually needs verifying
at this stage — not full coverage, not deferred entirely.

1. **Golden-output regression test for the scheduling algorithm (write before Milestone 1.5,
   run after it).** Before refactoring `models/initial_scheduling.py` into `SchedulingService`,
   run the current algorithm against a fixed, representative set of input files (existing
   orders + shifts data) and save the resulting schedule as a reference fixture
   (`tests/fixtures/golden_schedule_<date>.json` or similar — orders, technicians, and the
   resulting per-order assignment). After Task 1.5.5, run `SchedulingService` against the same
   fixed inputs and diff the output against the fixture. They must match exactly, except where
   the corrected working-time formula (Open Question 1) legitimately changes a technician's
   capacity — those differences must be enumerated and explained, not silently accepted.

2. **Repository round-trip tests, written alongside each repository.** For every repository
   introduced in Milestones 1.1–1.6 (`TechnicianRepository`, `ProductionOrderRepository`,
   `ShiftRepository`, `ScheduleAssignmentRepository`, `ScheduleLockRepository`, etc.): write a
   row against a disposable test database, read it back, assert the round trip preserves all
   fields. This is the existing "Unit verification" step in the Verification Strategy section
   below, made concrete and mandatory rather than optional.

3. **Service-layer tests for mutations with business-rule consequences.** At minimum:
   `ScheduleService` status transition guards (the Planned → In Progress → Partially Completed
   → Completed / Blocked state machine must reject invalid transitions), and
   `DailyOrderPoolService._find_replacement_technician()` (the three carryover scenarios listed
   in Task 1.5.4's Verify step). These are exactly the places where a silent bug would corrupt
   schedule data without anyone noticing in a Streamlit session.

4. **Test database.** Tests run against a real PostgreSQL instance, not mocks (consistent with
   the project's general bias toward correctness over speed) — either a disposable database on
   the local PostgreSQL instance from Task 1.1.0, or a Dockerized PostgreSQL spun up for the
   test run. Decide which when Task 1.1.0 is executed; document the choice in
   `tests/README.md`.

Phase 2 then adds CI automation and expands coverage. None of the above is deferred to Phase 2.

---

### Milestone 1.1 — Infrastructure Foundation

**Goal:** Establish the database connection, ORM models, and migration tooling. Nothing
visible to users changes. This milestone is entirely behind the scenes.

---

#### Task 1.1.0 — Provision PostgreSQL (Dev) and Plan Higher Environments

**What:** No PostgreSQL instance exists yet anywhere in this project. Provision one before any
other Phase 1 task can run.

- **Development:** Install PostgreSQL 15 locally on the development machine (native installer
  or Docker — either is fine; PostgreSQL wire compatibility is what matters for the
  application, not the hosting mechanism). Create one database (e.g. `dass_dev`) and two
  roles:
  - An **application role** with `SELECT, INSERT, UPDATE, DELETE` only on the application's
    tables — no `CREATE`, `DROP`, `ALTER`, no `TRUNCATE`. This is the role the running
    Streamlit app authenticates as.
  - A **migration role**, separate from the application role, with DDL privileges
    (`CREATE`, `ALTER`, `DROP`). Alembic runs as this role. The running application never uses
    it — this enforces the project's existing constraint that the app process cannot alter
    schema even if compromised.
  Set `DATABASE_URL` (application role) and a separate `MIGRATION_DATABASE_URL` (migration
  role) as local environment variables — never committed to version control. Document the
  setup steps (not the credentials) in a `docs/DEV_SETUP.md` or README section so a second
  developer can reproduce the environment.

- **Demo/staging:** The Streamlit app will occasionally be deployed to Streamlit Community
  Cloud for demonstrations and limited production use. Streamlit Community Cloud does not
  host PostgreSQL itself — point its `DATABASE_URL` secret at a reachable Postgres instance.
  Decide the specific instance when the first demo deployment is needed; it does not block
  Phase 1 development.

- **Production (future, not part of Phase 1):** The application will eventually migrate to
  AWS, with PostgreSQL on AWS RDS for PostgreSQL. No RDS provisioning is needed now — noted
  here so the connection module (Task 1.1.2) and credential handling (Task 1.1.3) are built
  against `DATABASE_URL` alone, with nothing environment-specific hardcoded, so the same code
  points at local Postgres, the demo instance, or RDS without modification.

**Why:** Every other task in Milestone 1.1 onward assumes a reachable `DATABASE_URL`. This
project currently has zero PostgreSQL infrastructure — confirmed by the product owner
2026-06-30. Without this task, Task 1.1.1's `pip install` succeeds but Task 1.1.2's connection
module has nothing to connect to.

**Depends on:** Nothing — this can start immediately, in parallel with Phase 0 if desired.

**Verify:** `psql $DATABASE_URL -c '\dt'` connects successfully and lists zero tables (database
exists, empty). The application role cannot run `CREATE TABLE` (permission denied). The
migration role can.

---

#### Task 1.1.1 — Add Dependencies

**What:** Add to `requirements.txt`:
- `psycopg2-binary` (PostgreSQL driver)
- `SQLAlchemy>=2.0`
- `alembic`
- `bcrypt`

**Depends on:** Phase 0 complete.

**Verify:** `pip install -r requirements.txt` succeeds. `import sqlalchemy; import alembic; import bcrypt` in a Python shell raises no errors.

---

#### Task 1.1.2 — Create Database Connection Module

**What:** Create `db/database.py`. This module reads `DATABASE_URL` from the environment
and creates the SQLAlchemy engine and a `SessionFactory`. Expose a `get_session()` context
manager that yields a session, commits on exit, and rolls back on exception. No other file
in the codebase creates a SQLAlchemy engine.

Create `db/__init__.py`.

**Depends on:** 1.1.0, 1.1.1.

**Verify:** A test script connects to a local PostgreSQL instance using `DATABASE_URL` and
executes `SELECT 1` without error.

---

#### Task 1.1.3 — Write SQLAlchemy ORM Models

**What:** Create `db/models.py` containing SQLAlchemy declarative ORM models for all nine
tables defined in `TARGET_ARCHITECTURE_V2.md` Section 5:

- `User`
- `Technician`
- `TechnicianSkill`
- `Product`
- `ProductionOrder` (includes `quantity`)
- `Shift`
- `ScheduleAssignment` (includes `is_expertise_override`)
- `WorkSession`
- `ScheduleLock`

All relationships declared with `relationship()`. All foreign keys with `ForeignKey()`.
All check constraints defined (`status IN (...)`, `stopped_at > started_at`).

**Depends on:** 1.1.2.

**Verify:** Importing `db/models.py` raises no errors. All model classes are importable.

---

#### Task 1.1.4 — Configure Alembic and Create Baseline Migration

**What:** Run `alembic init alembic` to create the Alembic directory. Configure `alembic.ini`
to read `sqlalchemy.url` from the environment variable `DATABASE_URL`. Configure `alembic/env.py`
to import `db/models.py` Base metadata.

Run `alembic revision --autogenerate -m "baseline_schema"` to generate the initial migration.
Review the generated migration file to confirm all tables, columns, constraints, and indexes
match the schema in V2.

Run `alembic upgrade head` against the local development database.

**Depends on:** 1.1.3.

**Verify:** `alembic current` shows `head`. `psql -c "\dt"` lists all nine tables. Each table
has the correct columns and constraints.

**Important:** Alembic migrations are run manually before each deployment. They are never run
automatically on application startup.

---

### Milestone 1.2 — Authentication Migration

**Goal:** Replace the hardcoded credential dictionary with a `users` table and bcrypt
password verification. Role enforcement added to all pages. This is the first milestone
where a user-visible change occurs.

---

#### Task 1.2.1 — Write UserRepository

**What:** Create `repositories/user_repository.py` containing `UserRepository` with:
- `find_by_username(session, username) → User | None`
- `create(session, username, password_hash, role) → User`
- `set_active(session, user_id, is_active) → None`

Receives a SQLAlchemy `session` argument. Never commits. Returns ORM `User` instances.

Create `repositories/__init__.py`.

**Depends on:** 1.1.4.

**Verify:** Unit test: create a user, find it by username, assert fields match.

---

#### Task 1.2.2 — Write User Seeding Script

**What:** Create `scripts/seed_users.py`. This one-time script reads credentials from the
environment (set in P0.2), hashes each password with bcrypt, and inserts the three initial
users (`admin`, `manager`, `user`) into the `users` table. Idempotent: if a username already
exists, skip it.

**Depends on:** 1.2.1.

**Verify:** Run the script against the local DB. `SELECT username, role FROM users;` returns
three rows. Plaintext passwords are not stored anywhere in the DB.

---

#### Task 1.2.3 — Refactor AuthService

**What:** Rewrite `services/auth_service.py`:
- `login(username, password)` — calls `UserRepository.find_by_username()`, then
  `bcrypt.checkpw(password, user.password_hash)`. On success, writes `user_id`, `username`,
  `role` to `st.session_state`. Tracks failed attempts in session state and enforces a
  30-second delay after 5 consecutive failures.
- `logout()` — clears all session state keys, not just `logged_in`.
- `require_login()` — unchanged contract, now backed by DB.
- `get_current_role()` — reads `st.session_state.role`.

Remove all references to `Config.CREDENTIALS`.

**Depends on:** 1.2.2.

**Verify:** Login works with the seeded users. Wrong password is rejected. After 5 failures,
a delay is enforced. Logout clears all session state.

---

#### Task 1.2.4 — Add Role Enforcement to Pages

**What:** Add a role check at the top of each page class `render()` method:
- Schedule Management — `manager` or `admin`
- Initial Scheduling — `manager` or `admin`
- Manage Technicians — `admin` only (contains PII)
- Manage Orders — `manager` or `admin`

Users with `user` role see a read-only access denied message on restricted pages. The `user`
role retains the ability to update order status (Start / Stop / End) on Schedule Management.

**Depends on:** 1.2.3.

**Verify:** Log in as `user`. Attempting to access Manage Technicians shows an access denied
message. Log in as `admin`. All pages are accessible.

---

### Milestone 1.3 — Technician Data Migration

**Goal:** Move technician data from `technicians_file.csv` to the `technicians` and
`technician_skills` tables. Build a real `TechniciansPage` backed by `TechnicianService` — the
existing `render_technicians_page()` has no working CRUD implementation to migrate (see
`CURRENT_STATE_ANALYSIS.md`), so this is new implementation work, not a like-for-like port.

---

#### Task 1.3.1 — Write TechnicianRepository

**What:** Create `repositories/technician_repository.py` containing `TechnicianRepository`:
- `find_all(session) → list[Technician]` (eager-loads `technician_skills`)
- `find_by_matricule(session, matricule) → Technician | None`
- `find_by_id(session, id) → Technician | None`
- `save(session, technician) → Technician`
- `delete(session, technician_id) → None`

**Depends on:** 1.1.4.

**Verify:** Unit test against a test database: save a technician with four skill rows, find
by matricule, assert all four skills are present.

---

#### Task 1.3.2 — Write TechnicianService

**What:** Create `services/technician_service.py` containing `TechnicianService`. All methods
are stateless (no DataFrames, no `st.session_state`):
- `get_all() → list[TechnicianDTO]` — loads from DB, computes `expertise_class` and
  `classification` from skills using the algorithm in `models/technicians.py`, returns DTOs.
- `add(matricule, full_name, skills: dict[int, int]) → TechnicianDTO`
- `modify(matricule, full_name, skills: dict[int, int]) → TechnicianDTO`
- `remove(matricule) → None`
- `compute_expertise_class(skills: dict[int, int]) → tuple[str, int]` — pure function,
  same logic as the existing `Technician.classify_technician()` and
  `Technician.convert_class_to_numeric()`. No DB access.

Define a `TechnicianDTO` dataclass in `services/technician_service.py` or a shared
`domain/` module with the fields the UI needs.

**Depends on:** 1.3.1.

**Verify:** `TechnicianService.get_all()` returns the same technicians as reading the CSV
directly.

---

#### Task 1.3.3 — Migrate Technician Data

**What:** Create `scripts/migrate_technicians.py`. Reads `data/technicians_file.csv`, inserts
one `Technician` row per record and four `TechnicianSkill` rows per technician (Niveau 1–4).
Idempotent: skip records where `matricule` already exists.

Handle the UTF-8 encoding issue in the CSV (`Nom et prénom` appears garbled). Read the file
with the correct encoding (`latin-1` or `cp1252`) and write correct names to the database.

**Depends on:** 1.3.1.

**Verify:** Row count in `technicians` matches row count in CSV. Row count in
`technician_skills` is 4× technician count. Names display correctly (no garbled characters).

---

#### Task 1.3.4 — Build TechniciansPage

**What:** `pages/technicians_page.py` currently contains only the placeholder comment
`"Copy your full manage_technicians() function code here from your old app.py"` — there is no
working implementation to port (confirmed by the product owner 2026-06-30). Build
`TechniciansPage.render()` from scratch, calling `TechnicianService` exclusively (no direct
CSV or `models/technicians.py` access):

- List view: all technicians with matricule, name, expertise class, classification.
- Add form: matricule, full name, four skill levels (Niveau 1–4) → `TechnicianService.add()`.
- Modify form: same fields, pre-filled, for an existing technician →
  `TechnicianService.modify()`.
- Delete/deactivate action with a confirmation step → `TechnicianService.remove()`.
- A statistics view (expertise class distribution) — a minimal bar/count chart, not a port of
  any existing chart since none exists in working form today.

Apply the role restriction from Task 1.2.4 (`admin` only — this page contains PII).

**Depends on:** 1.3.2, 1.3.3.

**Verify:** All four CRUD operations work end-to-end against PostgreSQL. The statistics view
displays correct counts. No CSV access remains in this page.

---

### Milestone 1.4 — Product Data Migration

**Goal:** Move product/SAP catalogue data from `products_classified.csv` to the `products`
table. Update `OrdersPage` to read from the database.

---

#### Task 1.4.1 — Write ProductRepository

**What:** Create `repositories/product_repository.py` containing `ProductRepository`:
- `find_all(session) → list[Product]`
- `find_by_sap(session, sap_number) → Product | None`
- `find_by_sap_list(session, sap_numbers: list[str]) → list[Product]` (for SAP validation)
- `save(session, product) → Product`
- `delete(session, product_id) → None`

**Depends on:** 1.1.4.

---

#### Task 1.4.2 — Write ProductService

**What:** Create `services/order_service.py` (name reflects its role as the service for both
products and production orders) containing `OrderService`:
- `get_all_products() → list[ProductDTO]`
- `add_product(sap_number, description, routing_time_minutes) → ProductDTO`
- `modify_product(sap_number, description, routing_time_minutes) → ProductDTO`
- `remove_product(sap_number) → None`
- `classify(routing_time_minutes) → tuple[str, int]` — pure function, returns
  `(class_label, class_code)` using thresholds from `config.py`.
- `bulk_upsert_products(rows: list[dict]) → BulkUploadResult` — the logic currently in
  `OrdersPage._process_bulk_upload()`, moved to the service layer.
- `validate_sap_numbers(sap_numbers: list[str]) → list[str]` — returns the list of SAP
  numbers not found in `products`. Used by the scheduling pipeline.

**Depends on:** 1.4.1.

---

#### Task 1.4.3 — Migrate Product Data

**What:** Create `scripts/migrate_products.py`. Reads `data/products_classified.csv`, inserts
one `Product` row per SAP number. Does not migrate `Class` or `Class Code` columns — these
are computed. Idempotent.

**Depends on:** 1.4.1.

**Verify:** Row count in `products` matches row count in CSV. `OrderService.classify()` returns
the same class labels as the original `classify_order()` function.

---

#### Task 1.4.4 — Update OrdersPage

**What:** Rewrite `pages/orders_page.py` to call `OrderService` instead of direct CSV access.
Move bulk upload logic from the page class to `OrderService.bulk_upsert_products()`.

**Depends on:** 1.4.2, 1.4.3.

**Verify:** All CRUD operations work. Bulk upload works. Classification preview is correct.
Statistics display correctly.

---

### Milestone 1.5 — Scheduling Pipeline Migration

**Goal:** Introduce `production_orders` and `shifts` tables. Introduce a daily order pool
resolution step (carryover from previous days). Refactor the scheduling algorithm to operate
on domain objects from the database. This is the core of the system and the largest single
milestone.

**Pre-condition:** Open Questions 1 (working-time formula), 2 (Phase 3 override), and 6
(Rounds 2 & 3 expertise) were resolved by the product owner on 2026-06-30 — see
`TARGET_ARCHITECTURE_V2.md` Section 18. Open Question 5 (quantity splitting) does not block
this milestone; the atomic default applies until resolved.

---

#### Task 1.5.1 — Write ProductionOrderRepository and ShiftRepository

**What:**

`repositories/production_order_repository.py` — `ProductionOrderRepository`:
- `find_by_date(session, date) → list[ProductionOrder]` (eager-loads `product`)
- `find_unstarted_before_date(session, date) → list[ProductionOrder]` — returns not-started
  orders from prior dates (late orders carried into today's pool)
- `find_by_erp_id_and_date(session, erp_order_id, date) → ProductionOrder | None`
- `bulk_insert(session, orders: list[ProductionOrder]) → None`
- `delete_by_date(session, date) → int` (returns count deleted, for re-generation)

`repositories/shift_repository.py` — `ShiftRepository`:
- `find_by_date(session, date) → list[Shift]` (eager-loads `technician`)
- `find_previous_shift(session, date) → list[Shift]` — returns the most recent shift before
  `date`, used by `ShiftService.get_previous_shift()` for the "displayed shift" path
- `upsert(session, shifts: list[Shift]) → None` (insert or update by `technician_id, shift_date`)

**Depends on:** 1.4.4 (products must be in DB before production orders can reference them).

---

#### Task 1.5.2 — Write ShiftService

**What:** `services/shift_service.py` — `ShiftService`:
- `parse_shifts_from_upload(shifts_df, date) → list[ShiftDTO]` — reads the uploaded Excel
  DataFrame, maps Matricule to technician IDs via DB lookup, creates `ShiftDTO` objects.
- `save_shifts(shift_dtos: list[ShiftDTO], date) → None` — writes to `shifts` table via
  `ShiftRepository.upsert()`.
- `get_working_technicians(date) → list[WorkingTechnicianDTO]` — loads shifts for a date,
  filters to `is_working=true` and `is_transferred=false`, computes `working_time_minutes`
  as `480 − break_minutes + extra_time_minutes` (Open Question 1, resolved 2026-06-30).
- `is_technician_working(date, technician_id) → bool` — point lookup used by
  `DailyOrderPoolService` to check technician availability.
- `get_previous_shift(date) → list[ShiftDTO]` — loads the most recent shift before `date`
  as the starting state for inline editing. Matches the flowchart's "View & Edit Displayed
  Shift" path: manager sees yesterday's shift by default and modifies it without uploading
  a new file.

`WorkingTechnicianDTO` carries: `technician_id`, `matricule`, `full_name`, `expertise_class`,
`working_time_minutes`.

**Depends on:** 1.5.1.

---

#### Task 1.5.3 — Write ProductionOrderService (upload side)

**What:** Add to `services/order_service.py`:
- `parse_orders_from_upload(orders_df, date) → list[ProductionOrderDTO]` — reads the uploaded
  Excel DataFrame, maps SAP numbers to product IDs, applies the quantity from the file.
- `validate_orders(order_dtos) → list[str]` — returns SAP numbers not found in `products`.
- `save_production_orders(order_dtos: list[ProductionOrderDTO], date) → None` — inserts into
  `production_orders` via `ProductionOrderRepository.bulk_insert()`. Orders with the same
  `erp_order_id` for the same date are skipped (idempotent upsert).
- `get_late_orders(date) → list[ProductionOrderDTO]` — calls
  `ProductionOrderRepository.find_unstarted_before_date()`. Returns `not_started` production
  orders from prior dates that were never scheduled. These are merged into today's assignable
  pool by `DailyOrderPoolService`.

`ProductionOrderDTO` carries: `erp_order_id`, `product_id`, `sap_number`,
`routing_time_minutes`, `quantity`, `effective_time_minutes` (computed: routing × quantity),
`class_code`, `priority`, `order_date`.

**Depends on:** 1.5.1.

**Verify:** Uploading the existing orders Excel file creates the correct `production_orders`
rows. `effective_time_minutes` = `routing_time_minutes × quantity` for every row.
Re-uploading the same file does not create duplicate rows.

---

#### Task 1.5.4 — Write DailyOrderPoolService

**What:** Create `services/daily_pool_service.py` — `DailyOrderPoolService`. This service
is called at the start of every scheduling cycle, **before** the scheduling algorithm runs.
It resolves the complete state of orders entering each day, matching the flowchart's
pre-algorithm steps.

**Step 1 — In-progress carryover** (flowchart: "Any In-Progress Orders from Yesterday?"):
For each `ScheduleAssignment` with status `In Progress` from the previous shift date:
- Call `ShiftService.is_technician_working(today, assignment.technician_id)`.
- If YES → the assignment continues unchanged. It is not re-scheduled; the technician
  simply resumes where they left off.
- If NO → find a replacement: same or higher expertise class, has available time today,
  does not already have an in-progress assignment from yesterday. Create a new
  `ScheduleAssignment` row for today, copying progress from the original. Log reason:
  "Tech absent — replaced". If no suitable replacement exists, mark the original
  assignment `Blocked` with reason "No qualified tech available today".

**Step 2 — Blocked order carryover** (flowchart: "Any Blocked Orders from Yesterday?"):
For each `ScheduleAssignment` with status `Blocked` from any prior date:
- If `was_unblocked_by_manager = False` → keep Blocked. The order does NOT enter the
  assignable pool. It is visible on the dashboard for manager action.
- If `was_unblocked_by_manager = True` → check original technician availability.
  If available, create a new `ScheduleAssignment` for today preserving prior progress.
  If not available, find a replacement using the same logic as Step 1.

**Step 3 — Late order collection** (flowchart: "Add Late Orders"):
Call `OrderService.get_late_orders(date)` to retrieve any `not_started` production orders
from prior dates. These are merged into the assignable pool alongside today's new orders.

**Step 4 — Return `DailyPoolResult`** containing:
- `carried_in_progress: list[AssignmentDTO]` — assignments continuing from yesterday
- `newly_blocked: list[AssignmentDTO]` — assignments that became blocked due to absent tech
- `unblocked_reassigned: list[AssignmentDTO]` — unblocked orders re-assigned to today
- `assignable_pool: list[ProductionOrderDTO]` — today's new + late orders, status
  `not_started`, ready for the scheduling algorithm
- `summary: dict` — counts for the manager dashboard display

`DailyOrderPoolService` methods:
- `resolve_pool(date) → DailyPoolResult`
- `_find_replacement_technician(order, working_techs, excluded_tech_ids) → WorkingTechnicianDTO | None`

**Schema addition:** Add `was_unblocked_by_manager BOOLEAN DEFAULT FALSE` to
`schedule_assignments`. Write an Alembic migration for this column. The column is set
by `ScheduleService.unblock_assignment()` in Milestone 1.6.

**Depends on:** 1.5.1, 1.5.2, 1.5.3.

**First-deployment note:** On the first day of operation, no prior assignments exist in the
DB. `resolve_pool()` returns empty carryover lists and the full uploaded order list as the
`assignable_pool`. No special handling required.

**Verify:** Unit test with three scenarios:
1. In-progress order: assigned tech IS working today → assignment continues, no new row.
2. In-progress order: assigned tech NOT working today → new assignment created for replacement.
3. Blocked order with `was_unblocked_by_manager = True` → re-assigned, new assignment for today.

---

#### Task 1.5.5 — Write SchedulingService

**What:** Create `services/scheduling_service.py` — `SchedulingService`.

The scheduling algorithm is moved verbatim from
`models/initial_scheduling.py:create_initial_schedule()` into a private method
`_run_algorithm(orders: list[ProductionOrderDTO], technicians: list[WorkingTechnicianDTO])`.
The algorithm operates on DTOs, not DataFrames. All capacity checks use
`order.effective_time_minutes`.

**Round-by-round behavior (confirmed by product owner 2026-06-30, resolves Open Questions 2
and 6):**

- **Round 1 (round-robin):** Preserved exactly as the current Phase 1. Each technician
  receives one order. Expertise check (`tech.expertise_class >= order.class_code`) is
  enforced. Orders are pre-sorted by priority (Urgent → A → B → C → None), then by
  `effective_time_minutes` descending within each priority group.

- **Round 2 (balanced priority assignment):** Preserved exactly as the current Phase 2.
  Expertise is enforced. Each remaining order goes to the qualified technician with the
  lowest total assigned time (exact expertise match preferred, most remaining time as
  tiebreaker).

- **Round 3 (capacity fill):** Preserved exactly as the current Phase 3 — expertise is
  ignored. For each order still unscheduled after Round 2, assign to any technician with
  sufficient remaining time, regardless of expertise class. This is deliberate: leaving an
  order unscheduled while a technician sits idle blocks production, which is a worse outcome
  than a flagged expertise mismatch. The assignment happens automatically inside
  `generate_schedule()` — there is no confirmation gate that could delay or withhold it.
  `is_expertise_override = true` is set on the resulting `ScheduleAssignment` row so the
  mismatch is visible and queryable. The manager sees a summary count of override
  assignments immediately after generation, as an informational notice, not an approval step.

  The flowchart's "Expertise adequate" label on the combined "Rounds 2 & 3" step describes
  Round 2 only — see the Flowchart Alignment section above.

Public methods:
- `generate_schedule(date, daily_pool: DailyPoolResult) → ScheduleGenerationResult`
  1. Acquire `ScheduleLock` via `ScheduleLockRepository`.
  2. Run `_run_algorithm(daily_pool.assignable_pool, working_technicians)`.
  3. Bulk-insert `ScheduleAssignment` rows for newly scheduled orders.
  4. Save unscheduled orders (orders in `assignable_pool` with no assignment).
  5. Release lock.
  6. Return `ScheduleGenerationResult`.
- `get_schedule(date) → list[AssignmentDTO]`
- `get_unscheduled(date) → list[ProductionOrderDTO]`

`ScheduleGenerationResult` carries: scheduled count, unscheduled count, carryover summary
(from `DailyPoolResult`), expertise-override count.

**Depends on:** 1.5.1, 1.5.2, 1.5.3, 1.5.4. Open Questions 1, 2, 6 are resolved (see
`TARGET_ARCHITECTURE_V2.md` Section 18). Open Question 5 does not block this task — the
atomic default applies.

**Verify:** Run the scheduling service against the existing orders and shifts files. Output
should match the CSV-based schedule's Phase 1/2/3 assignments exactly, except where the
corrected working-time formula (Open Question 1) changes technician capacity — document any
such difference explicitly; it is expected, not a bug.

---

#### Task 1.5.6 — Write ScheduleLockRepository

**What:** `repositories/schedule_lock_repository.py` — `ScheduleLockRepository`:
- `acquire(session, date, user_id) → bool` — inserts a lock row if none exists for that date;
  returns False if a lock already exists (concurrent generation rejected).
- `release(session, date) → None`
- `cleanup_stale(session, max_age_minutes=30) → int` — deletes unreleased locks older than
  30 minutes; called on application startup.

**Depends on:** 1.1.4.

---

#### Task 1.5.7 — Update InitialSchedulingPage

**What:** Rewrite `pages/initial_scheduling_page.py` to reflect two operating modes
matching the flowchart's "Start of Week / Fully New Orders" vs. "Continue Week" paths.
Mode is auto-detected by querying whether `schedule_assignment` rows exist for today.

**Mode A — New Schedule (no assignments exist for today):**
1. User specifies the schedule date (default: today).
2. User uploads Orders Excel file. `OrderService.parse_orders_from_upload()` →
   `OrderService.validate_orders()`. If validation fails, show missing SAPs and stop.
3. User either uploads a Shifts Excel file OR the page displays the previous shift for
   inline editing (matching the flowchart's "View & Edit Displayed Shift" path).
   `ShiftService.get_previous_shift()` provides the default; inline changes are saved via
   `ShiftService.save_shifts()`.
4. Call `DailyOrderPoolService.resolve_pool(date)`. Display the carryover summary to the
   manager:
   - X in-progress orders continuing from yesterday
   - Y blocked orders (remain blocked, visible on main dashboard)
   - Z late unstarted orders added to today's pool
5. Manager confirms → `SchedulingService.generate_schedule(date, daily_pool)` writes to DB.
6. Show summary: scheduled count, unscheduled count, per-technician utilisation.

**Mode B — Continue Week (assignments already exist for today or yesterday):**
1. Page auto-detects existing schedule, switches to continue-week view.
2. Shows carryover summary from `DailyOrderPoolService.resolve_pool(date)`.
3. Shows today's existing assignments as read-only (link to Schedule Management for editing).
4. Offers an "Upload additional orders" button. New orders are added to the pool and
   the scheduling algorithm runs only for them. Already-assigned orders are not re-scheduled.

Session state caches `schedule_date` and summary counts only — no DataFrames.

**Depends on:** 1.5.5, 1.5.6.

**Verify:**
- Empty DB → Mode A. Upload orders and shift → schedule generates correctly.
- After generation, refresh page → Mode B. Existing assignments shown.
- In Mode B, uploading new orders assigns them without disturbing existing assignments.

---

### Milestone 1.6 — Schedule Execution Migration

**Goal:** Move schedule management (status tracking, reassignment, work sessions) from
in-memory DataFrames and CSV files to the `schedule_assignments` and `work_sessions`
tables. `SchedulePage` reads from and writes to the database.

---

#### Task 1.6.1 — Write ScheduleRepository and WorkSessionRepository

**What:**

`repositories/schedule_repository.py` — `ScheduleRepository`:
- `find_by_date(session, date) → list[ScheduleAssignment]` (eager-loads production_order,
  technician, work_sessions)
- `find_by_id(session, assignment_id) → ScheduleAssignment | None`
- `find_by_row_uuid(session, schedule_row_id) → ScheduleAssignment | None`
- `save(session, assignment) → ScheduleAssignment`
- `find_unscheduled_by_date(session, date) → list[ProductionOrder]`

`repositories/work_session_repository.py` — `WorkSessionRepository`:
- `find_by_assignment(session, assignment_id) → list[WorkSession]`
- `create(session, assignment_id, started_at) → WorkSession`
- `close(session, session_id, stopped_at) → WorkSession`
- `find_open_session(session, assignment_id) → WorkSession | None`

**Depends on:** 1.5.6.

---

#### Task 1.6.2 — Refactor ScheduleService

**What:** Rewrite `services/schedule_service.py`. Remove all DataFrame parameters and return
values. Each method receives typed identifiers (assignment UUID or ID) and returns typed
result objects.

- `update_assignment_status(assignment_uuid, action: str) → StatusUpdateResult`
  - `start`: creates a `WorkSession` row (started_at = now).
  - `stop`: closes the open `WorkSession` (stopped_at = now), recalculates
    `remaining_time_minutes` from all closed sessions, updates assignment status.
  - `end`: closes open session, sets status to Completed, `remaining_time_minutes = 0`.
  - All guards (cannot start Completed, cannot stop Planned, etc.) are preserved exactly.
- `change_technician(assignment_uuid, new_matricule) → AssignmentDTO`
- `change_priority(assignment_uuid, new_priority, new_technician_matricule=None) → AssignmentDTO`
- `modify_routing_time(assignment_uuid, new_routing_time_minutes) → AssignmentDTO`
- `mark_as_blocked(assignment_uuid, block_reason) → AssignmentDTO`
- `assign_unscheduled_order(production_order_id, technician_matricule, date) → AssignmentDTO`
- `get_statistics(date) → ScheduleStats`
- `filter_assignments(date, statuses, technician_ids, priorities) → list[AssignmentDTO]`

**Depends on:** 1.6.1.

---

#### Task 1.6.3 — Migrate Existing Schedule Data

**What:** Create `scripts/migrate_schedule.py`. Reads `data/current_schedule.csv` and
`data/unscheduled_orders.csv` if they exist. Reconstructs:
1. `ProductionOrder` rows from the schedule data (if not already created in 1.5.x).
2. `ScheduleAssignment` rows from schedule rows.
3. `WorkSession` rows by parsing the `WorkSessions` JSON column.

Set `is_expertise_override = True` for rows with `Remark` containing "Capacity fill".

**Depends on:** 1.6.1.

**Verify:** Assignment count in DB matches row count in CSV. Work session rows are correctly
created for any assignments that had sessions in the JSON column.

---

#### Task 1.6.4 — Update SchedulePage

**What:** Rewrite `pages/schedule_page.py` to call `ScheduleService` and `OrderService`
instead of reading `st.session_state.initial_schedule_df`.

Session state usage after this task:
- `schedule_date` — the date being viewed (set by the user or defaulting to today).
- `last_action_message` — feedback message from the last status action.
- No DataFrames in session state. All data is read from the DB on page load.

Every `_handle_status_action()` call goes through `ScheduleService.update_assignment_status()`.
Every edit (technician change, priority change, time modification) goes through the
corresponding `ScheduleService` method.

The unscheduled orders section calls `ScheduleService.assign_unscheduled_order()`.

The urgency availability table is computed by `ScheduleService` (reading live DB data),
not by scanning a DataFrame in session state.

**Depends on:** 1.6.2, 1.6.3.

**Verify:** All status transitions work. Work sessions record correctly. Reassignment works.
Priority change with urgent assignment works. Page shows the correct data after every action
without requiring a manual page refresh.

---

### Milestone 1.7 — Cutover and Cleanup

**Goal:** Remove all CSV files from the operational path. Verify the migrated data matches
the originals. Delete all file-based persistence code. The application is now fully on
PostgreSQL.

---

#### Task 1.7.1 — Dual-Read Verification

**What:** Before removing any CSV files, run the verification procedure:
1. Load all data from the database (all pages must function correctly).
2. Compare row counts between DB and corresponding CSV files for `technicians`, `products`,
   and `schedule_assignments`.
3. Spot-check 10 random rows from each table against the CSV.
4. Run one complete scheduling cycle (upload, generate, view) and confirm output matches
   a known-good reference from the CSV era.

Document the verification results. Do not proceed to 1.7.2 until verification passes.

**Depends on:** 1.6.4.

---

#### Task 1.7.2 — Remove File-Based Persistence Code

**What:** Delete or gut the following (in order):
1. `services/persistence_service.py` — fully replaced by repositories.
2. `services/file_service.py` — all CSV read/write methods. Retain only
   `ensure_data_directory()` if still needed for non-data files.
3. All `pd.read_csv()` and `df.to_csv()` calls from `models/` and `services/`.
4. All imports of deleted code.

**Depends on:** 1.7.1.

**Verify:** `grep -r "read_csv\|to_csv\|PersistenceService\|FileService.save" --include="*.py"` 
returns no results outside of migration scripts.

---

#### Task 1.7.3 — Remove CSV Data Files

**What:** Archive `data/technicians_file.csv`, `data/products_classified.csv`,
`data/current_schedule.csv`, `data/unscheduled_orders.csv`, `data/working_technicians.csv`
to a `data/archive/` directory (do not delete immediately — keep for one deployment cycle
in case of rollback need). Remove `data/blocked_orders.csv` entirely (it was always empty).
Add `data/` to `.gitignore` except for `data/archive/`.

**Depends on:** 1.7.2.

**Verify:** Starting the application with no CSV files in `data/` works correctly.

---

#### Task 1.7.4 — Update SessionManager

**What:** Review `utils/session_manager.py`. Remove `_auto_load_schedule()` — it loaded
a schedule DataFrame from CSV on startup. Replace with a simpler auto-restore: on page load,
`SchedulePage` reads `schedule_date` from session state (or defaults to today) and calls
`ScheduleService.get_schedule(date)`. No DataFrames in session state.

Audit all session state keys. Remove any key that stored a DataFrame (`initial_schedule_df`,
`unscheduled_orders_df`, `working_technicians`, `merged_orders`). Document the remaining
keys.

**Depends on:** 1.7.3.

---

#### Task 1.7.5 — Final Code Audit

**What:** Run a final audit across the codebase:
- No `pd.read_csv()` / `df.to_csv()` outside migration scripts.
- No `st.*` calls in `services/` or `repositories/`.
- No DataFrames returned from service methods.
- No credentials in any tracked file.
- All six open questions resolved and answers reflected in code (1, 2, 6 resolved 2026-06-30; 3, 4, 5 resolved before this audit).
- `Config.CREDENTIALS` removed from `config.py`.

**Verify:** All four pages work. Authentication works. Generating a schedule, updating
statuses, and reassigning technicians all work correctly.

---

### Phase 1 Completion Checklist

- [ ] All four pages work with no CSV files present.
- [ ] `users` table populated; bcrypt login works for all three roles.
- [ ] Role enforcement active on all pages.
- [ ] `technicians` and `technician_skills` populated; Manage Technicians page reads from DB.
- [ ] `products` populated; Manage Orders page reads from DB; bulk upload writes to DB.
- [ ] Schedule generation reads from `production_orders` and `shifts`; writes to
  `schedule_assignments`.
- [ ] `is_expertise_override` flag set on Phase 3 assignments; visible in UI.
- [ ] Work sessions recorded in `work_sessions` table; total time computed from sessions.
- [ ] Schedule lock prevents concurrent generation.
- [ ] No `pd.read_csv()` / `df.to_csv()` in any operational code.
- [ ] No DataFrames in `st.session_state`.
- [ ] No credentials in tracked files.
- [ ] `data/` directory contains only archived CSVs.

---

## Phase 2 — Reliability and Operations

**Goal:** Make the application production-hardened, multi-user safe, and observable.
Phase 2 begins only after Phase 1 is stable in production for at least one full week.

The following capabilities are added in Phase 2. Internal sequencing within Phase 2 is
determined when Phase 2 is planned.

| Capability | Description |
|---|---|
| FastAPI service layer | Introduce FastAPI as an HTTP API layer between Streamlit and services. Services are already stateless, so this is additive. |
| JWT authentication | Replace bcrypt session auth with JWT tokens issued by FastAPI. The `users` table and bcrypt validation remain unchanged. |
| FST Department Interface | A dedicated real-time monitoring view for the `fst` user role (from flowchart). Shows live order statuses, technician workloads, completion rates, and blocked order alerts. Includes ability to add timestamped comments to orders and change order priority. Requires adding `fst` to the `users.role` enum and a new FST-scoped page. |
| Urgent priority interrupt process | From flowchart: when an order is escalated to Urgent priority, find the most suitable available technician (most time remaining, expertise match). If a technician is free, quick-assign immediately. If all are busy, show the manager a real-time table of current work (tech name, current order, progress %, estimated time remaining, interruptible: yes/no). Manager can choose to wait (order queued as next) or manually stop a technician (saves progress, assigns urgent order, queues paused order for resumption). |
| Historical schedule reports | A new Reporting page showing schedule history by date, technician utilisation, and expertise-override frequency. |
| Real-time status refresh | A polling mechanism (Streamlit `st.rerun` on a timer) so that status changes made by one user are visible to others without manual refresh. |
| Multi-department scheduling | Promote the `department` string field to a proper `departments` table. Add department-scoped schedule views. |
| Comprehensive test suite | Unit tests for all service methods. Integration tests for all repositories. End-to-end tests for the scheduling algorithm. |
| Monitoring and logging | Structured logging (replace `print()` with `logging`). Application health endpoint. Error tracking integration. |
| Production deployment | Docker container, environment configuration, database backup strategy, Alembic migration procedure for production. |
| Weekly reports | From flowchart end-of-week path: total orders received vs. completed, daily completion trends, technician efficiency rankings, blocked order analysis with reasons, average time per order type, bottleneck analysis. |

---

## Phase 3 — Advanced Features

**Goal:** Extend the system with capabilities that require a stable Phase 1 + Phase 2 foundation.

| Capability | Description |
|---|---|
| Reclamations module | Full CRUD, recommendations engine, linking reclamations to schedule assignments and technicians. |
| Order splitting | Allow a production order with quantity > 1 to be split across multiple technicians or days. Requires algorithm redesign. |
| AI scheduling assistance | Claude API integration. Natural language schedule queries, conflict detection, recommendation engine. |
| Chatbot interface | Conversational interface to the schedule (ask: "who is working on order X?" or "which orders are blocked?"). |
| Mobile interface | Progressive Web App or React Native client consuming the FastAPI backend. |

---

## Task Dependency Map

```
Phase 0
P0.1 → P0.2 → P0.3
P0.1 → P0.4
P0.4 → P0.5 → P0.6

Phase 1
1.1.0 (no dependency — can start anytime, even during Phase 0)
P0.6 → 1.1.1 → 1.1.2 → 1.1.3 → 1.1.4
1.1.0 → 1.1.2   [DB must exist before the connection module can be verified]

1.1.4 → 1.2.1 → 1.2.2 → 1.2.3 → 1.2.4   [Auth track]
1.1.4 → 1.3.1 → 1.3.2, 1.3.3 → 1.3.4    [Technician track]
1.1.4 → 1.4.1 → 1.4.2, 1.4.3 → 1.4.4    [Product track]

1.3.4 + 1.4.4 → 1.5.1
1.5.1 → 1.5.2
1.5.1 → 1.5.3
1.5.2 + 1.5.3 → 1.5.4 (DailyOrderPoolService)
1.5.4 → 1.5.5 (SchedulingService)
1.5.1 → 1.5.6 (ScheduleLockRepository)
1.5.5 + 1.5.6 → 1.5.7 (InitialSchedulingPage)  [Scheduling pipeline]

1.5.7 → 1.6.1 → 1.6.2, 1.6.3 → 1.6.4   [Execution track]

1.6.4 → 1.7.1 → 1.7.2 → 1.7.3 → 1.7.4 → 1.7.5  [Cutover]
```

**Parallelism opportunities:**
- Tasks 1.2.x (Auth), 1.3.x (Technicians), and 1.4.x (Products) can be worked in parallel
  after 1.1.4 completes, as they have no dependencies between them.
- Migration scripts (1.2.2, 1.3.3, 1.4.3) can be written in parallel with their repositories.

---

## Risk Register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Working-time formula was ambiguous pre-2026-06-30 | Resolved | — | Resolved: `480 − break_minutes + extra_time_minutes`, confirmed by product owner. Code `ShiftService` directly against this formula. |
| CSV data has encoding or type issues that break migration scripts | Medium | Medium — migration fails, must be re-run | Test migration scripts on a copy of production data before running on real DB. |
| Scheduling algorithm output differs after refactoring to DTOs | Low | High — breaks the core value of the system | Compare output row-by-row between old and new implementation for at least three test datasets before cutover. |
| Concurrent users expose state bugs before schedule_locks is implemented | Low | Medium — duplicate schedule generation | Implement `schedule_locks` in 1.5.5 alongside the scheduling service, not deferred. |
| Managers don't notice expertise-override assignments because the flag isn't visually prominent | Low | Medium — quality risk if a mismatched assignment goes unnoticed | `is_expertise_override` must render as a visible, filterable warning badge in the UI (Schedule Management page) and appear in the post-generation summary count. Confirmed 2026-06-30: assignment is automatic, not gated by manager confirmation. |
| `quantity > 1` orders exceed all technician capacities, inflating unscheduled list | Medium | Medium — unexpected scheduling failures | Resolve Open Question 5. Until answered, quantity is atomic and displayed prominently so managers are aware. |
| In-progress carryover finds no valid replacement technician | Low | Medium — assignment becomes blocked with no clear resolution path | `DailyOrderPoolService._find_replacement_technician()` must set status to Blocked with a clear reason. The dashboard must surface these "system-blocked" assignments prominently for manager intervention. |
| No PostgreSQL instance exists yet; local dev, demo, and production environments differ (local → Streamlit Community Cloud demo → AWS RDS production) | Medium | Medium — connection/config drift between environments, migration steps run inconsistently | `DATABASE_URL` is the only thing that changes between environments; no environment-specific code branches. Document the exact provisioning steps for each environment in Task 1.1.0. Run Alembic migrations the same way in all three. |

---

## Open Questions

These questions are from `TARGET_ARCHITECTURE_V2.md` Section 18.

### Resolved (2026-06-30)

| # | Question | Decision |
|---|---|---|
| 1 | Working-time formula | `480 − break_minutes + extra_time_minutes`. No `+30` offset. |
| 2 | Phase 3 override: confirmation step (soft) or hard-block? | Neither blocks the assignment: it happens automatically, flagged with `is_expertise_override = true`. Manager acknowledgement is an informational notice after generation, not a gate. |
| 6 | Rounds 2 & 3 expertise check (flowchart vs. current code) | Flowchart's "Expertise adequate" label describes Round 2 only. Round 3 keeps the original V2 design: ignore expertise, assign automatically, flag the override. See Flowchart Alignment section above and `TARGET_ARCHITECTURE_V2.md` Section 18. |

### Still open

| # | Question | Blocks milestone |
|---|---|---|
| 3 | **Data retention:** How long are completed schedule records kept in the database? | Milestone 1.7 (informs whether archiving or partitioning is needed at cutover) |
| 4 | **Initial admin credentials:** Who runs `scripts/seed_users.py` at first deployment, and how is the initial password communicated securely? | Milestone 1.2 |
| 5 | **Quantity splitting:** Is a production order with `quantity > 1` always atomic (one technician, all units), or can the quantity be split across technicians? | Milestone 1.5 (capacity check in algorithm); atomic default applies until resolved, does not block coding |

**How to resolve:** Raise each remaining question with the product owner before beginning the
blocking milestone. Record the answer in `TARGET_ARCHITECTURE_V2.md` Section 18 (update the
question to a decision) and in the relevant code comment.

---

## Verification Strategy

Each milestone uses the same three-step verification pattern:

1. **Unit verification:** The new code (service, repository, or page) produces correct output
   in isolation. For services: call the method and assert the return value. For repositories:
   write a row, read it back, assert it matches.

2. **Integration verification:** The page that depends on the new code works end-to-end in
   a running Streamlit session with a real database.

3. **Regression verification:** All previously working pages still work correctly after the
   milestone. No existing functionality is broken.

For milestones that migrate data from CSV to DB (1.3, 1.4, 1.5, 1.6): add a fourth step —
**parity verification** — comparing DB output to CSV content before removing the CSV path.
