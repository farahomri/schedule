# Architecture Changelog: V1 → V2

**Document:** Comparison of `TARGET_ARCHITECTURE.md` (V1) and `TARGET_ARCHITECTURE_V2.md` (V2)  
**Date:** 2026-06-23  
**Purpose:** Record every architectural decision made during the V1 → V2 revision, with the
original design, the revised design, the reason for the change, its benefits, and its
trade-offs.

---

## Index of Changes

| # | Change | Category |
|---|---|---|
| 1 | Authentication: JWT replaced with bcrypt + DB session | Auth |
| 2 | Computed columns removed from the database | Data Model |
| 3 | "Order" split into `products` and `production_orders` | Data Model |
| 4 | Technician skill levels normalized into a junction table | Data Model |
| 5 | Natural keys demoted to indexed unique columns; surrogate PKs introduced | Data Model |
| 6 | `WorkSessions` JSON column replaced with a `work_sessions` table | Data Model |
| 7 | `ScheduleRow` split into `schedule_assignments` and `work_sessions` | Data Model |
| 8 | `Shift` entity gains a `shift_date` column | Data Model |
| 9 | Phase 3 expertise bypass becomes a boolean flag, not a freetext remark | Scheduling |
| 10 | `users` table introduced | Data Model |
| 11 | `schedule_locks` table introduced | Concurrency |
| 12 | Repository layer given explicit interface contract | Architecture |
| 13 | Service layer made explicitly stateless | Architecture |
| 14 | Department represented as a string field, not an entity | Architecture |
| 15 | Transaction strategy explicitly defined | Architecture |
| 16 | CSV → PostgreSQL migration strategy defined | Operations |
| 17 | Phase 0 introduced before database migration | Process |
| 18 | Security considerations section added | Security |
| 19 | Known constraints and open questions documented | Process |

---

## Change 1 — Authentication: JWT Replaced with bcrypt + DB Session

### Original Design (V1)

V1 specified "JWT-hardened" authentication as a Phase 1 requirement, listing it in the stack
table as the upgrade from the current plaintext dictionary lookup.

> *"Auth: AuthService (basic) ✅ → JWT-hardened"*

No implementation details were given about how the JWT would be issued, stored, or validated
within the Streamlit runtime.

### Revised Design (V2)

Phase 1 uses bcrypt-hashed passwords stored in a `users` database table. On successful login,
the user's `id`, `username`, and `role` are written to `st.session_state`. This is exactly
what Streamlit's session model already provides — the change from V1 is the backend (DB table
instead of hardcoded dictionary) and the password storage (bcrypt instead of plaintext).

JWT is deferred to Phase 2, where it is implemented at the FastAPI HTTP layer when real
stateless endpoints exist.

### Reason for the Change

JWTs are designed for stateless HTTP authentication. The client sends a signed token in an
`Authorization` header on every HTTP request. The server validates it without consulting a
session store. This model is appropriate for REST APIs and fits FastAPI perfectly.

Streamlit does not work this way. Every user interaction travels over a persistent WebSocket
connection. There is no HTTP request per action. `st.session_state` is server-side and
survives across reruns within a session. If a JWT is implemented in Streamlit, the token must
be stored somewhere between reruns — which means `st.session_state` or a browser cookie
managed by a third-party library. At that point the JWT is just a value in server memory,
giving the same security profile as the current session-state approach but with added
complexity: key management, token expiry, refresh token handling, and clock skew concerns.

The statelessness benefit of JWT — the reason it is valuable — does not materialise in a
Streamlit-only deployment because the session is already stateful.

### Benefits

- Eliminates unnecessary infrastructure (JWT signing keys, expiry/refresh logic) from Phase 1.
- bcrypt + DB session is well-understood, easy to test, and correct for the runtime.
- The `users` table is the natural prerequisite for role enforcement, which V1 lacked entirely.
- When FastAPI arrives in Phase 2, JWT is added at the HTTP routing layer only. The `users`
  table and bcrypt validation are reused unchanged — no business logic migration required.

### Potential Trade-offs

- Phase 1 auth is session-bound, not token-bound. A user cannot be authenticated across
  multiple independent Streamlit sessions simultaneously (e.g. desktop and mobile browser)
  with a shared token — each session re-authenticates independently. For Phase 1 this is
  acceptable; it becomes addressable when FastAPI + JWT is introduced.
- Streamlit's session is tied to a browser tab. If the tab is closed and reopened, the user
  must log in again. This is expected behavior but may feel less polished than a persistent
  "remember me" token. A "remember me" cookie approach is deferred to Phase 2.

---

## Change 2 — Computed Columns Removed from the Database

### Original Design (V1)

V1's data model stored four derived values directly in database columns:

- `Classification` (Basic Knowledge / Above Average / Good / Advanced) on `technicians`
- `Expertise Class` (1–4) on `technicians`
- `Class` (Low / Medium / High / Very High) on `orders` / `products`
- `Class Code` (1–4) on `orders` / `products`

These were listed in the data model schema without any note that they were derived.

### Revised Design (V2)

None of these values are stored in the database. They are computed by service layer functions
at read time:

- `TechnicianService.compute_expertise_class()` derives `Classification` and `Expertise Class`
  from the `technician_skills` rows for that technician.
- `ProductService.classify()` derives `Class` and `Class Code` from `routing_time_minutes`
  using the thresholds defined in `config.py`.
- `ShiftService.compute_working_time()` derives `working_time_minutes` from `break_minutes`
  and `extra_time_minutes`.

The classification thresholds and expertise mappings remain in `config.py` as the single
authoritative source.

### Reason for the Change

Derived values stored in the database create a synchronisation problem. The stored value is
correct only at the moment it was written. If the source data changes — a technician's skill
score is updated, a product's routing time is corrected — the derived column must also be
updated, or it becomes wrong. This requires either an application-level update in the same
transaction (easy to forget or get wrong) or a database trigger (hidden logic, harder to test).

The more serious risk is rule changes. If the routing time thresholds shift (e.g. the boundary
between Low and Medium moves from 160 to 180 minutes), every stored `Class` and `Class Code`
value in the database is now wrong. Correcting it requires a data migration script, a backfill
run, and verification — all of which are operational risk on a production system.

By computing derived values in the service layer, a threshold change requires updating one
function and redeploying. No data migration, no stale rows, no verification step.

### Benefits

- Single source of truth: the threshold lives in `config.py`, not partly in the code and
  partly in stored DB values.
- Eliminates an entire class of data inconsistency bugs.
- The classification logic is in Python where it can be unit tested directly.
- Schema is simpler: fewer columns, less confusion about which columns are authoritative.

### Potential Trade-offs

- Computed values are not directly queryable in SQL. You cannot write
  `SELECT * FROM products WHERE class = 'High'` — you must filter by
  `routing_time_minutes BETWEEN 320 AND 480`. For this application's query patterns
  (filtering by class in the schedule UI) this is a minor inconvenience, not a performance
  problem. If raw-SQL reporting is needed later, PostgreSQL generated columns
  (`GENERATED ALWAYS AS`) can be added as an index-friendly computed column without
  storing them in the application's data model.
- Service layer functions must be called consistently. If a repository returns raw ORM
  objects and a caller forgets to call the classification function, the object has no
  `class_code` attribute. Mitigation: domain objects always include computed fields,
  populated by the service layer before they are returned to the presentation layer.

---

## Change 3 — "Order" Split Into `products` and `production_orders`

### Original Design (V1)

V1 defined a single `Order` entity:

```
Order (Products Classified)
  SAP (material number, string PK)
  Material Description
  routing time (minutes)
  Class (Low / Medium / High / Very High)
  Class Code (1-4)
```

This entity was described as "the product catalogue" but was also used to represent individual
work instructions in the scheduling algorithm. The `ScheduleRow` stored both product properties
(routing time, class code) and order-instance properties (Order ID, priority, date) together.

### Revised Design (V2)

Two separate entities:

**`products`** — stable SAP master data. One row per material number. Exists permanently.
Contains `sap_number`, `description`, `routing_time_minutes`.

**`production_orders`** — a dated work instruction from the ERP. References a `product` via
foreign key. Contains `erp_order_id`, `product_id`, `priority`, `order_date`, `department`.
Many production orders can reference the same product.

### Reason for the Change

The original design conflated two things with fundamentally different lifecycles:

A product in the catalogue is a reference record. SAP 500245821 exists because Draexlmaier
manufactures that part. It was created once and changes only when the routing time is
renegotiated with engineering. It should survive indefinitely.

A production order is a work instruction for a specific day. ERP order 2001514763 was issued
for a specific date and consumed in one scheduling run. Tomorrow there may be a new order for
the same product, with a different ERP order number and possibly a different priority.

Without this separation:
- You cannot ask "how many times was SAP 500245821 scheduled this month?" because there is no
  stable product record to join against.
- You cannot have two orders for the same SAP number on the same day (valid in production:
  two batches of the same part).
- The "Manage Orders" page and the "Initial Scheduling" page are operating on different things
  that share a name.
- Deleting a product from the catalogue would destroy its scheduling history.

### Benefits

- Correct relational model: products and orders have the right cardinality (one-to-many).
- Historical queries become natural: join `production_orders` to `products` on `product_id`,
  filter by date range.
- Product catalogue management (add/modify/delete SAP entries) is cleanly separated from
  schedule generation (uploading today's work orders).
- The `UNIQUE(erp_order_id, order_date)` constraint on `production_orders` prevents the
  algorithm from scheduling the same ERP order twice — a silent bug in the current system.

### Potential Trade-offs

- Adds a join to every schedule-related query. Instead of reading `routing_time_minutes` from
  the schedule row, you join through `production_orders → products`. This is standard
  relational practice and not a performance concern at this data volume.
- The "Manage Orders" page UI needs to clarify which entity it manages. Currently it manages
  the product catalogue (adding SAP numbers and routing times). This page name should be
  updated to "Manage Products" to avoid confusion.
- Bulk upload of orders (the existing Excel upload feature) now performs two steps: upsert
  into `products` (new SAP number or updated routing time) and insert into
  `production_orders` (the dated work instruction). This is more correct but slightly more
  complex to implement.

---

## Change 4 — Technician Skill Levels Normalized Into a Junction Table

### Original Design (V1)

V1 preserved the existing four horizontal columns on the `Technician` entity:

```
Niveau 4 / 3 / 2 / 1 (qualification counts per level)
```

These four integers represented the technician's score at each of four certification levels.
The classification logic took the maximum of the four values to determine the overall expertise
class.

### Revised Design (V2)

A `technician_skills` junction table replaces the four columns:

```
technician_skills (technician_id, skill_level, score)
UNIQUE (technician_id, skill_level)
```

One row per `(technician, level)` pair. A technician with four skill levels has four rows.

### Reason for the Change

Four horizontal columns encoding a one-to-many relationship is a relational antipattern known
as "repeating groups." The problem is extensibility: if a fifth certification level is ever
introduced, the schema requires a migration (`ALTER TABLE ADD COLUMN niveau_5`), followed by
updating every query that references skill levels, every ORM model, and every form in the UI.

With a junction table, adding a fifth level is an application-level change only — no schema
migration, no column added, no existing rows touched.

The four levels are also currently unqueryable as data. Asking "how many technicians have a
Level 3 score above 20?" requires a `CASE` expression against four named columns. With the
junction table it is a simple `WHERE skill_level = 3 AND score > 20`.

### Benefits

- Schema is closed to skill-level changes. New levels require no migration.
- Skill level queries are natural SQL: `WHERE skill_level = ? AND score > ?`.
- The ORM model is simpler: one `TechnicianSkill` model with a foreign key rather than four
  typed columns.
- Aggregate queries (average score per level, technicians above a threshold) are standard
  aggregation, not column arithmetic.

### Potential Trade-offs

- Loading a technician's full skill profile now requires a join or eager loading of the
  `technician_skills` relationship, instead of reading four columns from one row. This is a
  minor additional query cost — negligible at the data volumes of this application (15
  technicians currently).
- The UI forms for adding and modifying technicians currently have four fixed text inputs
  for Niveau 1–4. These will continue to work with the junction table behind them; the form
  structure does not need to change because the domain has exactly four levels. The
  normalization future-proofs the schema without changing the current UI.

---

## Change 5 — Natural Keys Demoted to Indexed Unique Columns; Surrogate PKs Introduced

### Original Design (V1)

V1 used external identifiers as primary keys:

- `Matricule` (badge number, string) as PK for technicians
- `SAP` (material number, string) as PK for orders

### Revised Design (V2)

Every table uses a surrogate integer primary key (`id SERIAL PRIMARY KEY`). External
identifiers become unique indexed columns:

- `technicians.matricule` — `UNIQUE NOT NULL`, indexed
- `products.sap_number` — `UNIQUE NOT NULL`, indexed

### Reason for the Change

External identifiers are assigned by systems outside the application's control (HR systems,
SAP ERP). These systems have historically reassigned identifiers in edge cases — a badge
number reused after a long absence, a SAP number corrected after an entry error. If an
external identifier is also the database primary key, changing it cascades to every foreign
key in every related table. With 15 technicians and a growing schedule history, a single
Matricule correction could require updating thousands of `schedule_assignments` rows.

A surrogate integer PK means the database has its own identity that is entirely internal.
The external identifier is still unique and indexed for fast lookups — it just carries no
relational weight. A Matricule correction becomes a single-row UPDATE on `technicians` with
no cascade.

String primary keys also have a practical performance cost on B-tree indexes compared to
integer keys, particularly for foreign key joins. At this application's scale this is not
measurable, but the pattern is correct regardless.

### Benefits

- FK cascades are eliminated as a concern for external identifier changes.
- Integer PK joins are marginally faster than string PK joins.
- The database identity is independent of any external system. The application owns its own
  primary keys.
- Natural keys remain queryable and unique — the lookup behavior is identical to V1.

### Potential Trade-offs

- Every lookup by external identifier becomes a two-step conceptual operation: "find the
  internal id by matricule, then use the id for joins." In practice SQLAlchemy handles this
  transparently through relationships and the ORM — the application code rarely sees raw IDs.
- The UUID `schedule_row_id` on `schedule_assignments` is preserved for backward compatibility
  with existing saved schedule CSV files during the data migration. This means
  `schedule_assignments` temporarily has both an integer PK and a UUID natural key, which is
  slightly redundant. The UUID column can be dropped after the migration is verified complete.

---

## Change 6 — `WorkSessions` JSON Column Replaced with a `work_sessions` Table

### Original Design (V1)

V1 preserved the existing `WorkSessions` column: a JSON-encoded array of session objects
stored as text in the schedule row:

```
WorkSessions  TEXT  -- JSON: [{"start": "ISO", "stop": "ISO"}, ...]
```

### Revised Design (V2)

A normalized `work_sessions` table:

```
work_sessions (id, assignment_id FK, started_at TIMESTAMPTZ, stopped_at TIMESTAMPTZ)
CHECK (stopped_at IS NULL OR stopped_at > started_at)
```

One row per work session. The JSON column is removed entirely.

### Reason for the Change

Storing structured data as JSON in a relational column is appropriate only when the data is
truly schemaless or when you never need to query inside it. Work sessions are neither. They
have a fixed schema (`start`, `stop`) and there are several queries the application needs to
make:

- "What is the total time spent on this assignment?" — requires summing session durations.
- "Is there an open session right now?" — requires checking for a row where `stopped_at IS NULL`.
- "Did this technician have overlapping sessions?" — requires comparing timestamps across rows.
- "What were all sessions between 09:00 and 10:00 today?" — requires indexing on `started_at`.

None of these queries are possible with a JSON column without either parsing the JSON in
application code (slow, error-prone) or using PostgreSQL's JSON operators (non-standard,
not portable, and bypasses the ORM).

The JSON column also offers no integrity guarantees. The database cannot enforce that
`stopped_at > started_at` inside a JSON value. It cannot enforce that there is at most one
open session per assignment. These constraints are the responsibility of the application code,
which is exactly where the current bugs occur — the state machine allows starting a new session
without verifying the previous one was closed.

### Benefits

- `CHECK (stopped_at IS NULL OR stopped_at > started_at)` is enforced by the database.
  No application code can accidentally write a session that ends before it starts.
- Total time spent is a standard SQL aggregate: `SUM(EXTRACT(EPOCH FROM (stopped_at - started_at)) / 60)`.
- "Is there an open session?" is a `WHERE stopped_at IS NULL` query with an index.
- Overlapping session detection is a self-join on `assignment_id` with timestamp comparison.
- The `started_at` column is indexable, enabling time-range queries for reports.
- The ORM model for a session is a first-class object with type safety.

### Potential Trade-offs

- Loading an assignment's full session history requires a join (or eager loading) instead of
  parsing a string column. This is a minor cost — assignments rarely have more than a handful
  of sessions.
- The `TotalTimeSpent` and `RemainingRoutingTime` snapshot values on `schedule_assignments`
  become redundant in principle (derivable from `work_sessions`) but are retained as cached
  values for UI performance. The rule is: `work_sessions` is the source of truth; the snapshot
  columns on `schedule_assignments` are updated on each stop/end action and must never be
  independently modified.
- The existing `current_schedule.csv` encodes sessions as JSON text. The data migration script
  must parse these JSON strings and insert individual `work_sessions` rows. This adds
  complexity to the one-time migration script but does not affect ongoing operations.

---

## Change 7 — `ScheduleRow` Split Into `schedule_assignments` and `work_sessions`

### Original Design (V1)

V1 preserved the existing 22-column `ScheduleRow` as a single database entity containing:

- Assignment data (technician, order, sequence, status)
- Denormalized product data (Material Description, Routing Time copied in)
- Denormalized technician data (Technician Name copied in)
- Execution tracking (StartTime, StopTime, EndTime, RealSpentTime)
- Work session history (WorkSessions JSON)
- Priority, Class Code, Remark

### Revised Design (V2)

Two entities:

**`schedule_assignments`** — static assignment data. Set at generation time, changed rarely.
Contains: `production_order_id` (FK), `technician_id` (FK), `schedule_date`, `sequence_number`,
`status`, `routing_time_minutes` (snapshot), `remaining_time_minutes` (cached), `remark`,
`is_expertise_override`.

**`work_sessions`** — dynamic execution records. Created/updated throughout the workday.
Contains: `assignment_id` (FK), `started_at`, `stopped_at`.

Denormalized names (`Technician Name`, `Material Description`) are removed. They are read
by joining to `technicians` and `products` respectively.

### Reason for the Change

The 22-column `ScheduleRow` violated the Single Responsibility Principle at the data model
level. It was simultaneously:

1. An assignment record (who does what, in what order)
2. A real-time execution log (when did they start, when did they stop)
3. A denormalized product catalogue entry (material description, routing time)
4. A denormalized technician record (name)

Assignment data is written once at schedule generation and changes only when a manager
reassigns an order or changes a priority — rare events. Execution data changes continuously
throughout the workday as technicians start, pause, and complete orders. Mixing these
in one table creates write contention and makes the two concerns harder to reason about
independently.

Denormalized names create a consistency risk. If a technician's name is corrected in the
master (`technicians.full_name`), every `schedule_assignments` row retaining the old name
becomes stale. A join on the foreign key eliminates this permanently.

### Benefits

- Assignment queries (who is assigned to what, in what sequence, with what status) are clean
  and focused on the `schedule_assignments` table.
- Execution queries (total time spent, session history) operate on `work_sessions` without
  touching assignment columns.
- Denormalized names are eliminated. Schedule displays always show the current name from the
  master record.
- `routing_time_minutes` is kept as a snapshot on the assignment because the UI allows
  per-assignment time modification that should not alter the product catalogue. This is
  intentional and documented.
- Write contention is reduced: technician status updates (frequent) and manager reassignments
  (rare) no longer compete for the same row lock when the execution data is in a separate table.

### Potential Trade-offs

- Displaying the full schedule view requires joining `schedule_assignments` → `production_orders`
  → `products` and `schedule_assignments` → `technicians`. This is two joins per row in the
  schedule. At the data volumes expected (hundreds of assignments per day), this is not a
  performance concern. SQLAlchemy's eager loading (`joinedload`) handles this cleanly.
- The migration from the existing CSV to the new schema requires mapping the 22-column flat
  row to its normalized form. This is handled once in the data migration script.

---

## Change 8 — `Shift` Entity Gains a `shift_date` Column

### Original Design (V1)

V1's `Shift` entity had no date field:

```
Shift: Matricule, Technician Name, Working, Holiday, Break, Extra Time,
       To another, Working Time
```

### Revised Design (V2)

```
shifts (id, technician_id FK, shift_date DATE, is_working, is_transferred,
        break_minutes, extra_time_minutes)
UNIQUE (technician_id, shift_date)
```

`shift_date` is required. `working_time_minutes` is not stored (computed). `Technician Name`
is removed (read by join to `technicians`).

### Reason for the Change

Without a date, the `shifts` table can store at most one shift record per technician — the
current day's. There is no way to:

- Store historical shifts for reporting (did this technician work last Tuesday?)
- Compare utilisation across days
- Pre-enter shift data for the coming week
- Replay a past schedule using the correct shift data from that day

The `UNIQUE(technician_id, shift_date)` constraint enforces that each technician has exactly
one shift record per day. Uploading a new shifts file for the same date overwrites the existing
records (upsert), which is the correct behavior.

`Technician Name` is removed from `shifts` for the same reason as in Change 7 — it is a
denormalized copy of data that lives authoritatively in `technicians.full_name`. The application
joins to `technicians` to read the name.

### Benefits

- Full shift history is stored, enabling utilisation reports across days or weeks.
- Pre-entering shift data for upcoming days becomes possible.
- Historical schedule replay uses the correct shift data from the actual date.
- `UNIQUE(technician_id, shift_date)` prevents duplicate shift entries — a category of
  data entry error that is silent in the current CSV approach.

### Potential Trade-offs

- The shifts Excel file upload now requires associating each row with a specific date. If the
  user uploads the file without specifying a date, the application must either infer it
  (assume today) or ask the user to confirm. V2 chooses to prompt the user for the shift date
  before processing the file. This is a minor UX addition.

---

## Change 9 — Phase 3 Expertise Bypass Becomes a Boolean Flag

### Original Design (V1)

V1 preserved the existing Phase 3 behavior: when the algorithm assigns an order to a
technician who does not meet the expertise requirement (capacity fill), it writes the string
`"Capacity fill - may not match expertise"` to the `Remark` column. No other signal was emitted.

### Revised Design (V2)

A dedicated boolean column `is_expertise_override BOOLEAN DEFAULT false` is added to
`schedule_assignments`. Phase 3 assignments set this to `true`. The remark text may also be
set, but the flag is the primary signal.

The UI renders expertise-override assignments with a visible warning indicator. The schedule
summary reports the count of override assignments as a separate metric. The manager must
acknowledge any override assignments before the schedule is considered finalized (a
confirmation step in the UI, not a hard block of generation).

The scheduling algorithm behavior is otherwise unchanged.

### Reason for the Change

A freetext remark buried in a column is not a reliable signal for a factory production
environment. A manager reviewing the schedule — possibly on a printed version, possibly by
scanning the Streamlit table — will not naturally notice a remark string among dozens of rows.
A potential expertise mismatch in manufacturing is a quality risk: the wrong technician
assigned to a high-complexity order may produce defects.

Making the override a first-class boolean column enables:
- Filtering the schedule view to show only override assignments.
- Displaying a count of overrides in the schedule summary header.
- Querying historically: "how often does Phase 3 run for each technician?"
- A UI confirmation prompt that forces explicit acknowledgement before the schedule is committed.

### Benefits

- Expertise mismatches are surfaced visibly, not hidden in freetext.
- The override flag is queryable and indexable. Historical analysis is possible.
- The confirmation step creates a documented management decision rather than a silent system action.
- The algorithm behavior is unchanged — Phase 3 still runs and still ignores expertise. The
  change is in the visibility and traceability of the outcome.

### Potential Trade-offs

- The confirmation UI step adds friction to schedule generation. A manager generating a
  schedule with many Phase 3 assignments must actively acknowledge them. This is intentional —
  the friction is proportional to the risk. A schedule with no Phase 3 assignments requires
  no confirmation.
- If the factory routinely produces schedules where Phase 3 is unavoidable (insufficient
  expert technicians for the order volume), the confirmation step will feel repetitive.
  In that case the correct long-term response is to expand the technician pool, not to remove
  the confirmation.

---

## Change 10 — `users` Table Introduced

### Original Design (V1)

V1 did not define a `users` table. Multi-user support was listed as a goal. Credentials were
stored in `Config.CREDENTIALS`, a Python dictionary in `config.py` with three hardcoded
entries.

### Revised Design (V2)

A `users` table is introduced:

```
users (id, username UNIQUE, password_hash, role, is_active, created_at, updated_at)
```

Credentials are removed from `config.py`. Passwords are bcrypt-hashed (cost factor ≥ 12).
Role is stored per user. The three initial users (`admin`, `manager`, `user`) are seeded
at first deployment via a migration script.

Role enforcement: each page checks `st.session_state.role` against a required role list
before rendering.

### Reason for the Change

Multi-user support cannot be built without a user identity store. The hardcoded dictionary
in `config.py`:

1. Cannot be modified at runtime without redeploying the application.
2. Stores passwords in plaintext, committed to version control.
3. Has no concept of disabling a user account (e.g. when an employee leaves).
4. Enforces no role-based access (three roles exist in the dict but are never checked against
   pages or actions).

A database table solves all four problems and is a prerequisite for every future auth
enhancement, including JWT in Phase 2.

### Benefits

- Passwords are never in source code or version control.
- Users can be added, disabled, or have their role changed without redeployment.
- Role-based page access can be enforced consistently.
- The `users` table is the anchor for future per-user audit logging.
- bcrypt's adaptive cost factor means password hashing difficulty scales with hardware
  improvements without schema changes.

### Potential Trade-offs

- The initial deployment requires seeding the `users` table. This must be done before the
  first login attempt. The process (a one-time script run by an administrator) must be
  documented clearly.
- There is no self-service password reset in Phase 1. A forgotten password requires an
  administrator to update the hash directly in the database or via an admin page. A
  password reset flow is deferred to Phase 2.

---

## Change 11 — `schedule_locks` Table Introduced

### Original Design (V1)

V1 did not address concurrent schedule generation. The architecture diagram showed services
calling the database directly with no mention of what happens when two users generate a
schedule for the same date simultaneously.

### Revised Design (V2)

A `schedule_locks` table provides a lightweight advisory lock at the application layer:

```
schedule_locks (id, schedule_date UNIQUE, locked_by FK users, locked_at, released_at)
```

Before generating a schedule, the `SchedulingService` checks for an unreleased lock on
that date. If one exists, generation is rejected with an informative error message. If not,
a lock row is inserted (within the same transaction as schedule generation) and released on
completion or failure. Stale locks are cleaned up on application startup.

### Reason for the Change

Schedule generation is a multi-step write: the algorithm computes all assignments for a day
and then inserts them in bulk. If two managers trigger generation simultaneously for the same
date, both algorithms run on the same input data, compute (different or identical) assignments,
and attempt to insert them. The result is interleaved writes or a unique constraint violation
on `UNIQUE(production_order_id, schedule_date)` — which would surface as a confusing error
message, not a clear "someone else is generating the schedule" warning.

The `schedule_locks` table makes this a first-class, user-visible situation. The second
manager sees "A schedule for [date] is currently being generated by [username]. Please wait."

### Benefits

- Concurrent generation attempts produce a clear user-facing message rather than a database
  error.
- The lock record provides an audit trail: who generated which schedule and when.
- The lock is released automatically on failure, preventing a deadlock where a crashed
  generation permanently blocks future generations for that date.
- Stale lock cleanup on startup handles the edge case where the application crashed mid-generation.

### Potential Trade-offs

- This is an application-level advisory lock, not a database-level lock. It relies on the
  application respecting the lock before doing work. A database-level `SELECT FOR UPDATE` on
  the lock row would be strictly stronger, but for a Streamlit application with a small
  number of concurrent users, the advisory approach is sufficient and easier to reason about.
- If the application is deployed as multiple Streamlit instances (horizontal scaling), the
  advisory lock must be checked against the shared database, not in-process memory. The table
  approach naturally handles this — all instances see the same `schedule_locks` table. This
  is a benefit, not a trade-off.

---

## Change 12 — Repository Layer Given Explicit Interface Contract

### Original Design (V1)

V1 showed a "Repository Layer" box in the architecture diagram labeled
*"SQLAlchemy queries replacing all CSV read/write calls"* but defined no repository
interfaces, no method signatures, and no contract between the service layer and repositories.

### Revised Design (V2)

The repository contract is defined:

- One repository class per aggregate root: `TechnicianRepository`, `ProductRepository`,
  `ProductionOrderRepository`, `ScheduleRepository`, `ShiftRepository`, `UserRepository`.
- Repositories receive a SQLAlchemy `session` argument passed by the service layer.
  They never open, commit, or close sessions themselves.
- Repositories return SQLAlchemy ORM instances or typed domain objects. Never raw SQL results.
- Repositories contain only database operations: `get`, `get_all`, `save`, `delete`,
  `find_by_*`. No business logic, no classification, no scheduling decisions.

### Reason for the Change

Without a defined contract, developers will implement repositories inconsistently — some will
commit sessions internally, some will accept DataFrames, some will contain business logic.
Over time the layer becomes indistinguishable from the service layer and the separation
provides no benefit.

The specific rule that repositories receive a session but never commit it is critical. It
allows the service layer to wrap multiple repository calls in a single transaction. If
repositories committed internally, a service calling two repositories could produce partial
commits when the second fails.

### Benefits

- Service layer can compose multiple repository operations in one atomic transaction.
- Repository behavior is predictable: same inputs always produce the same DB operations.
- Repositories are independently testable by providing a test session connected to an
  in-memory SQLite database.
- The boundary between "what talks to the DB" and "what contains business rules" is unambiguous.

### Potential Trade-offs

- Passing a `session` argument to every repository method is more verbose than a repository
  that manages its own connection. This verbosity is intentional — it makes the transaction
  boundary explicit in the calling code rather than hidden inside the repository.
- If a developer forgets to commit in the service layer, writes are silently rolled back when
  the session context exits. This is correct behavior but can be surprising during development.
  Mitigation: integration tests that verify data is persisted after service calls.

---

## Change 13 — Service Layer Made Explicitly Stateless

### Original Design (V1)

V1 stated that services should be "independent of Streamlit" so FastAPI can be added later.
It did not define what this means concretely. The existing services accept and return
`pd.DataFrame` objects. No constraint was placed on `st.session_state` usage in service code.

### Revised Design (V2)

Two explicit rules are added:

1. No service method may read from or write to `st.session_state`.
2. No service method may accept or return a `pd.DataFrame` as its interface contract.

Services receive typed domain objects or primitive arguments. They return typed domain objects
or result objects. `st.session_state` is a Streamlit-layer concern only. The database is
always the source of truth; session state is a UI cache.

### Reason for the Change

The claim "Streamlit-First, FastAPI-Ready" is only true if services do not depend on Streamlit
state. The current service layer is not FastAPI-ready because:

1. Every `ScheduleService` method takes a DataFrame that comes from `st.session_state`. FastAPI
   has no session state. Every method would need to be rewritten to read from the database first.

2. DataFrames are a pandas concept that carries no type information about what the rows mean.
   A function that takes `df: pd.DataFrame` has no contract. A function that takes
   `assignment: ScheduleAssignment` has a contract that is enforceable by the type checker
   and understandable to the reader.

If these rules are not enforced in Phase 1, Phase 2 will require rewriting every service
method, not just adding HTTP routing. The "FastAPI-ready" goal will not be met.

### Benefits

- Services are independently runnable in a test environment without starting a Streamlit server.
- FastAPI integration in Phase 2 requires adding routing only — service logic is unchanged.
- Domain objects carry type information. Errors like passing an order where a technician is
  expected are caught by the type checker rather than at runtime.
- The data flow is explicit: Streamlit page reads from DB via service, caches in session state
  for UI performance, calls service again when user takes an action.

### Potential Trade-offs

- Migrating the existing DataFrame-based services to domain-object-based services is a
  substantial refactoring effort. Every page that currently reads a DataFrame from session
  state and passes it to a service must be updated. This is the correct cost to pay now
  rather than paying a larger cost in Phase 2.
- Domain objects must be defined for every entity. This adds code (dataclasses or SQLAlchemy
  models) that did not exist before. The benefit is that this code is explicit documentation
  of the data model that a DataFrame is not.

---

## Change 14 — Department Represented as a String Field, Not an Entity

### Original Design (V1)

V1 did not mention departments or production lines. The system implicitly assumed a single
global schedule namespace.

### Revised Design (V2)

A `department` string field is added to `technicians` and `production_orders`. No `Department`
table is created in Phase 1. Multi-department schedule isolation is deferred to Phase 2.

### Reason for the Change

The architecture review identified that a factory almost certainly has multiple production
lines or departments. Without any department field, multi-department isolation requires a
schema migration later that touches every table that needs a department scope (`technicians`,
`production_orders`, `schedule_assignments`). Adding a `department` string field costs nothing
now and preserves the option to promote it to a proper entity later.

A full `Department` entity (with its own table, foreign keys, and page) is not built in Phase 1
because there is no evidence from the existing codebase, data, or product vision that the
factory currently uses multi-department scheduling. Building the entity before the need is
confirmed adds join complexity and migration risk with no immediate benefit.

### Benefits

- The schema retains department information from the first day of DB operation. No future
  migration needs to backfill department data from scratch.
- Promoting a string field to a FK-referenced entity later is a straightforward migration:
  create `departments` table, populate from distinct values, add FK column, drop string column.
- No unnecessary complexity in Phase 1.

### Potential Trade-offs

- String fields are not enforced for consistency — typos produce orphaned department values
  (`"assembly"`, `"Assembly"`, `"ASSEMBLY"` are three different values). Mitigation: validate
  the field against a config-level list of allowed department names in the service layer, even
  without a DB-level FK. When the entity is promoted, the FK replaces this validation.
- Until department isolation is built, all users see all schedules regardless of their
  department field. This is an accepted Phase 1 limitation.

---

## Change 15 — Transaction Strategy Explicitly Defined

### Original Design (V1)

V1 mentioned that `PersistenceService.save_schedule()` writes CSV files and that these calls
should be replaced with DB writes. No transaction model was defined. There was no mention of
what happens when a write fails partway through a multi-step operation.

### Revised Design (V2)

The transaction strategy is defined:

- One SQLAlchemy `Session` per top-level service operation.
- The service layer opens the session, calls repositories, and commits or rolls back.
- Repositories receive the session and never manage transaction state themselves.
- Schedule generation wraps all writes (lock acquisition, bulk assignment insert) in a single
  transaction. If any write fails, the entire day's schedule is rolled back — no partial
  schedules are committed.

### Reason for the Change

Without a defined transaction strategy, two common bugs emerge:

1. **Partial commits:** Service A calls Repository 1 (succeeds, commits internally) then
   Repository 2 (fails). The system is now in an inconsistent state — some data was written,
   some was not, with no record of which.

2. **Transaction leakage:** A repository opens a session and forgets to close it. Under load,
   the connection pool is exhausted.

Defining the transaction boundary at the service layer and making it explicit in code makes
both bugs impossible by construction.

### Benefits

- Schedule generation is atomic: either the entire day's schedule is committed or nothing is.
- Developers reading service code can see exactly where the transaction boundary is.
- Repository code is simpler — no session lifecycle management.
- Consistent behavior under failure: partial state never reaches the database.

### Potential Trade-offs

- Passing a `session` argument through service → repository adds boilerplate. This is the
  standard cost of explicit transaction management in SQLAlchemy's synchronous ORM and is
  considered acceptable in this application's architecture.
- Long-running transactions (e.g. schedule generation with hundreds of assignments) hold a
  DB connection for the duration of the computation. Mitigation: the algorithm runs as a pure
  computation on loaded data before writing, keeping the write transaction short. The data
  load phase and the write phase use separate short-lived sessions.

---

## Change 16 — CSV to PostgreSQL Migration Strategy Defined

### Original Design (V1)

V1 stated that CSV reads and writes should be replaced with DB calls and named Alembic as
the migration tool. No data migration strategy was defined — there was no plan for moving
the existing CSV data into the new database.

### Revised Design (V2)

A concrete migration strategy is defined:

1. Alembic manages schema (DDL) only. It does not move data.
2. A separate one-time data migration script runs once at first deployment, in a fixed order:
   `users` → `technicians` + `technician_skills` → `products` → `production_orders` +
   `schedule_assignments` + `work_sessions` (from CSV) → `reclamations` (deferred).
3. After migration, the application runs both CSV and DB paths in parallel for one shift
   to verify row counts and key fields match before the CSV path is removed.
4. Alembic migrations run manually before deployment, not automatically on startup.

### Reason for the Change

The original document named Alembic as if it solves all migration concerns. Alembic manages
schema evolution (add a column, create a table, drop an index). It does not load data. The
data migration from 15 technicians and hundreds of schedule rows in CSV format is a separate,
one-time operation that must be scripted, tested, and verified independently of Alembic.

The order of migration matters. `technician_skills` cannot be inserted before `technicians`
because of the foreign key dependency. `schedule_assignments` cannot be inserted before both
`production_orders` and `technicians`. Getting the order wrong produces FK constraint errors
that are painful to debug mid-migration.

The "run both paths in parallel" verification step is a safety net. The CSV is not deleted
until the migrated data is confirmed correct. This makes the migration reversible: if
discrepancies are found, the application reverts to CSV mode while the migration script is
fixed.

### Benefits

- No data loss during transition: CSV files remain until verification passes.
- The migration is reproducible: the same script run against a fresh database produces the
  same result every time.
- The order of operations is explicit and documented.
- Alembic's role is clearly scoped — it does not attempt to do what it is not designed for.

### Potential Trade-offs

- The parallel-run verification step requires keeping both code paths (CSV and DB) alive
  simultaneously during the migration period. This is a short-term increase in code complexity.
  The CSV path is deleted immediately after verification.
- The data migration script must handle the `WorkSessions` JSON parsing. This is a one-time
  cost but requires careful testing with the actual CSV data before running in production.

---

## Change 17 — Phase 0 Introduced Before Database Migration

### Original Design (V1)

V1 described Phase 1 (database migration) as the immediate next step. It did not define any
pre-database work.

### Revised Design (V2)

Phase 0 is introduced as a prerequisite to Phase 1:

**Phase 0 — Stabilise (no database work):**
1. Fix the Reclamations page crash (`generate_recommendations` undefined).
2. Fix `add_reclamation` / `modify_reclamation` / `delete_reclamation` path and signature bugs.
3. Move credentials out of `config.py`.
4. Collapse `FileService` and `PersistenceService` into one save path.
5. Remove `st.warning()` calls from `models/initial_scheduling.py`.
6. Remove dead commented-out algorithm code.
7. Extract inline page functions from `app.py` into `pages/` classes.

**Exit criterion:** The application runs end-to-end with no runtime crashes on any page.

### Reason for the Change

Starting the database migration before the application is functionally stable is risky. The
Reclamations page crashes at runtime — any developer working on the migration who visits that
page gets an unhandled exception that has nothing to do with the database. The duplicate save
paths (FileService and PersistenceService both writing the same CSV) would be translated into
two DB write paths, doubling the confusion rather than resolving it.

Phase 0 produces a clean baseline: a functioning application with a single save path, no dead
code, no runtime crashes, and no credentials in source. Phase 1 then adds the database to a
system that is already correct, making it much easier to verify that the DB migration did not
break anything.

The product vision explicitly states: "make the application work correctly from beginning to
end." Phase 0 fulfills that objective for the CSV-based system before Phase 1 replaces it.

### Benefits

- The database migration begins from a known-good baseline, not a partially broken codebase.
- Each Phase 0 fix is independently verifiable by running the application.
- Developers working on Phase 1 do not encounter unrelated bugs that obscure migration issues.
- Phase 0 changes are low-risk (no schema changes, no new dependencies) and can be reviewed
  and merged quickly.

### Potential Trade-offs

- Phase 0 delays the start of database work. For a team eager to get to PostgreSQL, this
  may feel like the wrong priority. The counter-argument is that a broken codebase going into
  a migration produces a broken codebase on PostgreSQL — the database does not fix application
  bugs.

---

## Change 18 — Security Considerations Section Added

### Original Design (V1)

V1 mentioned JWT auth as a security improvement but had no dedicated security section.
Specific risks (plaintext credentials in VCS, no rate limiting, no input sanitisation,
no DB privilege separation, no PII considerations) were not addressed.

### Revised Design (V2)

A security section defines:

- **Secrets:** No credentials in source code. DB connection string in environment variable.
  Streamlit secrets for local development (excluded from git).
- **DB privileges:** Application DB user has DML only (SELECT / INSERT / UPDATE / DELETE).
  No DDL. No TRUNCATE. Migration user is separate.
- **Input validation:** File uploads validated with try/except. Text inputs validated against
  length limits and character whitelists before reaching the repository. SQLAlchemy
  parameterised queries prevent SQL injection — raw string interpolation into SQL is prohibited.
- **Rate limiting:** Session-level brute-force mitigation (5 failures → 30-second delay).
  IP-level rate limiting delegated to reverse proxy.
- **PII:** Technician names and matricules are PII. Manage Technicians restricted to `admin`.
  Names not logged in application logs. Data retention policy required before production.

### Reason for the Change

Security considerations that are not documented before implementation are not implemented.
Each item in this section addresses a specific, identified risk in the current codebase.
The plaintext credentials in `config.py` are a critical vulnerability — they are committed
to a git repository accessible to anyone with repo access.

### Benefits

- Security controls are defined before they are needed, not retrofitted after a breach.
- The DB privilege separation limits the blast radius of a SQL injection vulnerability: even
  if an attacker executes arbitrary SQL through the application connection, they cannot drop
  tables or modify schema.
- PII handling and data retention decisions are on the record before personal data enters
  the production database.

### Potential Trade-offs

- The data retention policy decision is deferred but must be made before production. This
  is explicitly flagged as an open question in V2 rather than silently omitted.

---

## Change 19 — Known Constraints and Open Questions Documented

### Original Design (V1)

V1 did not document known constraints or open questions. The working-time formula anomaly
(`480 + 30 − Break` producing 510 minutes) was reproduced without comment.

### Revised Design (V2)

**Known constraints are documented** (single-day scheduling, no order splitting, no real-time
push, single department, no schedule history UI) with their planned resolution phase.

**Four open questions are raised** that require product owner confirmation before
implementation begins:

1. The working-time formula — is 510 minutes the intended base, or is it a bug?
2. Phase 3 override — hard block or soft confirmation?
3. Data retention — how long are completed schedules kept?
4. Initial user seeding — who creates the first `admin` user and how?

### Reason for the Change

Undocumented constraints become surprises during development. A developer implementing the
scheduling service discovers that schedules can only be generated for one day at a time and
assumes it is an oversight, spending time designing a date-range solution that was never
requested.

The working-time formula is the highest-risk open question. If the formula is wrong
(`510 min base` instead of `480 min base`), the scheduling algorithm has been assigning
incorrect capacity to every technician since the system was built. Fixing it after Phase 1
requires a data migration to recalculate all stored `working_time_minutes` values. Confirming
the intended behavior before coding `ShiftService` costs nothing.

### Benefits

- Developers know which constraints are intentional and which are future work.
- Product owner is given a concrete list of questions to answer before development begins,
  rather than discovering ambiguity during code review.
- The working-time formula question is on the record. If it is confirmed wrong, it can be
  fixed before the formula is encoded in a service method.

### Potential Trade-offs

- Raising open questions before implementation begins requires the product owner to engage
  with technical details. This is appropriate — these questions have business consequences
  that only the product owner can resolve.

---

## Summary of All Changes

| # | Area | V1 | V2 | Primary Driver |
|---|---|---|---|---|
| 1 | Auth | JWT (Phase 1) | bcrypt + DB session (Phase 1); JWT deferred to Phase 2 | JWT doesn't fit Streamlit runtime |
| 2 | Derived values | Stored in DB | Computed at service layer | Stale data risk on rule changes |
| 3 | Order entity | Single "Order" | `products` + `production_orders` | Different lifecycles conflated |
| 4 | Skill levels | 4 horizontal columns | `technician_skills` junction table | Relational antipattern; extensibility |
| 5 | Primary keys | Natural keys (string) | Surrogate integer PKs | External ID reassignment risk |
| 6 | Work sessions | JSON column | `work_sessions` table | Unqueryable, unenforceable in JSON |
| 7 | Schedule row | 22-column god-object | `schedule_assignments` + `work_sessions` | Mixed concerns, denormalized names |
| 8 | Shift entity | No date field | `shift_date` column, `UNIQUE(tech, date)` | Cannot store historical shifts |
| 9 | Phase 3 signal | Freetext remark | `is_expertise_override` boolean | Remark is invisible in production |
| 10 | Users | Hardcoded dict | `users` DB table, bcrypt | Multi-user support prerequisite |
| 11 | Concurrency | Not addressed | `schedule_locks` table | Concurrent generation produces corrupt state |
| 12 | Repository layer | Named but undefined | Explicit interface contract | Inconsistent implementation without a contract |
| 13 | Service layer | DataFrame-based | Stateless, typed domain objects | DataFrames block FastAPI migration |
| 14 | Departments | Not addressed | String field on tables | Retrofitting is harder; full entity deferred |
| 15 | Transactions | Not defined | Service-layer boundary, explicit commits | Partial commits risk |
| 16 | Data migration | Alembic (incomplete) | Separate data migration script + verification | Alembic is for schema, not data |
| 17 | Phase structure | Phase 1 = DB migration | Phase 0 = stabilise first | Broken baseline makes migration harder |
| 18 | Security | JWT mentioned only | Full section: secrets, privileges, input, PII | Undocumented risks are unmitigated risks |
| 19 | Constraints | Not documented | Documented with resolution phase | Developer surprises and the formula bug |
