# DASS — Target Architecture V2

**DASS:** Draexlmaier Automated Scheduling System  
**Version:** 2.1  
**Date:** 2026-06-23  
**Last amended:** 2026-06-23  
**Status:** Approved for implementation — this document is the single source of truth.  
**Supersedes:** `TARGET_ARCHITECTURE.md` (V1, May 2026)

> **What changed from V1 and why:** V1 was a correct directional document but incomplete as a
> design specification. This version incorporates a full architectural review that identified
> structural problems in the data model, an auth decision that does not fit the Streamlit runtime,
> a missing Repository layer definition, missing entities, and unaddressed scalability and security
> concerns. Every change is explained inline. Nothing in the scheduling algorithm or business rules
> has changed.
>
> **Amendment 2026-06-23 — product owner clarifications incorporated:**
> (1) `production_orders` gains a `quantity` column. A production order can require one or many
> units of the same product. Effective scheduling time is `routing_time_minutes × quantity`. All
> capacity checks use this effective time, not the per-unit routing time alone.
> (2) Reclamations are **fully deferred to advanced level**. No Phase 1 stabilisation. The page
> is removed from sidebar navigation until advanced-level work begins.
>
> **Amendment 2026-06-30 — scheduling algorithm and infrastructure decisions confirmed:**
> (1) **Working-time formula resolved:** `working_time_minutes = 480 − break_minutes +
> extra_time_minutes`. The previous `+30` constant is removed (see Section 18, Decision 1).
> (2) **Phase 3 capacity fill confirmed as originally designed:** ignoring expertise as a
> last-resort fallback is intentional, not a defect. An order left unscheduled while a
> technician is idle blocks production — a worse outcome than a flagged expertise mismatch.
> Assignment is automatic; the manager-facing confirmation is an informational notice after
> generation, not a gate (see Section 18, Decisions 2 and 6, and Section 9).
> (3) `schedule_assignments` gains a `was_unblocked_by_manager` column to track
> manager-initiated unblocking of previously blocked orders (see Section 5).
> (4) `DailyOrderPoolService` is added to the service layer (Section 7) to resolve
> in-progress, blocked, and late-order carryover before each day's scheduling run (see
> Section 17).

---

## 1. Business Objectives (Unchanged)

These are preserved verbatim from `PRODUCT_VISION.md` and must not be compromised by any
architectural decision.

- Replace manual technician scheduling with an intelligent scheduling system.
- Make the application work correctly from beginning to end, especially the scheduling logic.
- Build a cleanly architected, easy-to-maintain codebase.
- Prefer incremental refactoring over rewriting.
- Optimize for **correctness and maintainability**, not speed.
- Support PostgreSQL, SQLAlchemy, Alembic, layered architecture, and Streamlit frontend.
- Remain ready for a future FastAPI backend and AI chatbot.
- Support multi-user access.

---

## 2. Architectural Approach

**Layered Monolith — Streamlit-First, FastAPI-Ready.**

The application remains a single deployable unit with four distinct layers:
Streamlit → Service → Repository → Database. Layers communicate downward only.
No layer skips another. This is not a microservices architecture.

FastAPI is not introduced in Phase 1. The service layer is written to be
fully independent of Streamlit so that FastAPI can be placed in front of it in
Phase 2 without rewriting business logic.

---

## 3. Revised Stack

| Layer | Current State | Phase 1 Target | Phase 2+ |
|---|---|---|---|
| Frontend | Streamlit | Streamlit | Streamlit or React (optional) |
| Backend | Embedded in Streamlit | Service layer (stateless) | FastAPI microservices |
| Database | CSV / XLSX flat files | PostgreSQL 15 | PostgreSQL (scaled) |
| ORM | None | SQLAlchemy 2.x (ORM mode) | Same |
| Migrations | None | Alembic | Same |
| Auth | Dict lookup, plaintext | bcrypt + DB `users` table | JWT (with FastAPI) |
| Scheduling | `initial_scheduling.py` | `SchedulingService` (refactored) | Same |
| AI / Chatbot | None | **DEFERRED** | Claude API |
| Audit logs | None | **DEFERRED** (WorkSessions cover ops tracking) | Full audit log table |
| Reclamations | Broken (runtime crash) | **DEFERRED — advanced level only.** Page removed from navigation. | Full module |

---

## 4. Key Architectural Decisions

Each decision below explains what V1 proposed, what this version changes, and the reason.

---

### 4.1 Authentication: bcrypt + DB Session, Not JWT (Phase 1)

**V1 proposed:** JWT-hardened authentication in Phase 1.

**V2 changes:** Defer JWT to Phase 2. Use bcrypt-hashed passwords stored in a `users` database
table, validated on login. Rely on Streamlit's server-side session for authenticated state.

**Why:** JWTs are stateless bearer tokens designed for HTTP request authentication — every request
carries a signed token and the server validates it without storing session state. Streamlit does
not issue HTTP requests per interaction. It maintains a persistent WebSocket connection and
`st.session_state` is already server-side. Storing a JWT inside `st.session_state` adds the
complexity of token issuance, expiry, and refresh logic while gaining none of the statelessness
benefit, because Streamlit's session is already stateful and server-managed.

JWT becomes genuinely useful in Phase 2 when FastAPI exposes real HTTP endpoints that need
stateless authentication for API clients. Implementing it prematurely in Streamlit creates
unnecessary infrastructure with no practical security gain over a properly hashed password in a
database.

**Phase 1 auth contract:**
1. Credentials stored in `users` table, passwords hashed with bcrypt (cost factor ≥ 12).
2. Login validates against DB. On success, write `user_id`, `username`, `role` to
   `st.session_state`.
3. Every page checks `st.session_state.logged_in` before rendering.
4. Role is stored in session and used for access control checks (see Section 5).
5. No credentials anywhere in source code or `config.py`.
6. Credentials loaded from environment variables or Streamlit secrets at runtime.

---

### 4.2 No Computed Columns Stored in the Database

**V1 proposed:** Store `Classification`, `Expertise Class` on `technicians`; store `Class`,
`Class Code` on orders.

**V2 changes:** Do not store any derived value in the database. Compute at the service layer.

**Why:** Derived values become stale when the source data or the derivation rule changes. If the
routing time classification thresholds shift (e.g. the boundary between Low and Medium moves from
160 to 180 minutes), every stored `Class` and `Class Code` value becomes wrong. A migration or
backfill script would be required. By computing these values in the service layer on read, a
threshold change requires updating one function — no data migration, no stale rows.

**Affected values and where they are computed:**

| Derived Value | Source | Computed in |
|---|---|---|
| `Classification` (Basic Knowledge / Good / Advanced) | `technician_skills` max score | `TechnicianService.classify()` |
| `Expertise Class` (1–4) | `Classification` | `TechnicianService.classify()` |
| `Class` (Low / Medium / High / Very High) | `routing_time_minutes` | `ProductService.classify()` |
| `Class Code` (1–4) | `Class` | `ProductService.classify()` |
| `working_time_minutes` | `break_minutes`, `extra_time_minutes` | `ShiftService.compute_working_time()` |

The classification thresholds and expertise mappings remain in `config.py` as the single source
of truth. The service layer reads them from there, not from the database.

---

### 4.3 Product and ProductionOrder Are Two Different Entities

**V1 proposed:** A single "Order" entity covering both the product catalogue and the scheduled
work instance.

**V2 changes:** Introduce two separate entities: `Product` (catalogue) and `ProductionOrder`
(work instance).

**Why:** The current system conflates two things with different lifecycles:

- A **Product** is a stable master-data record: an SAP number with a description and a routing
  time. It exists in the system permanently. Many production orders can reference the same product.
- A **ProductionOrder** is a work instruction from the ERP for a specific scheduling period
  (day or week). It has an ERP Order ID, a priority, a date, and a **quantity** — the number
  of units of that product to be produced. The same product can appear in multiple production
  orders on the same day (e.g. two separate batches of the same part number). Each order is
  consumed in a single scheduling run and assigned to one technician as an atomic unit.

Without this separation, you cannot answer: "How many times was SAP 500245821 scheduled this
month?" You cannot distinguish between "we know this product" and "we have a current order for
it." You also cannot have two orders for the same SAP number on the same day with different
quantities and priorities — which is a valid real-world scenario.

---

### 4.4 WorkSessions Must Be a Normalized Table, Not JSON

**V1 proposed:** Store work sessions as a JSON array in a `WorkSessions` column on the schedule
row.

**V2 changes:** Replace with a `work_sessions` table with a foreign key to `schedule_assignments`.

**Why:** JSON in a relational column is a dead end for any non-trivial query. You cannot:
- Index individual sessions for time-range queries
- Enforce that a session's `stopped_at` is after `started_at` with a check constraint
- Sum time across all sessions for a technician in a day with a SQL aggregate
- Prevent overlapping sessions for the same technician
- Join sessions to other tables

A `work_sessions` table makes all of these straightforward SQL queries. The semantic content is
identical — each session has a start timestamp and an optional stop timestamp — but now the
database can enforce integrity and you can query it.

The current `TotalTimeSpent` and `RemainingRoutingTime` columns on the schedule row are
derivable from the sessions table by summing closed session durations. They can be kept as a
cached/snapshot value on the assignment row for UI performance, but the `work_sessions` table
is the source of truth.

---

### 4.5 ScheduleRow Splits Into ScheduleAssignment + WorkSession

**V1 proposed:** A single 22-column `ScheduleRow` entity.

**V2 changes:** Split into `schedule_assignments` (static assignment data) and `work_sessions`
(dynamic execution tracking).

**Why:** The original row carries assignment data (who does what, in what sequence, with what
status) and execution data (when did they start, how long did it take, session history)
in the same record. These have different change frequencies and different consumers.

Assignment data is set at schedule generation time and changes rarely (only on reassignment or
priority change). Execution data changes constantly throughout the workday as technicians start
and stop orders. Mixing them in one table creates lock contention and makes the two concerns
harder to reason about separately.

Denormalized names (`Technician Name`, `Material Description` copied into the row) are also
removed. These are read through foreign key joins. If a technician's name is corrected, the
schedule display updates automatically.

---

### 4.6 Service Layer Must Be Stateless

**V1 proposed:** Services can be called from Streamlit and later from FastAPI with minimal
change.

**V2 adds explicit rule:** No service method may read from or write to `st.session_state`. No
service method may accept or return a `pd.DataFrame` as its interface contract. Services receive
typed domain objects or primitive arguments and return typed domain objects or result objects.

**Why:** The current `ScheduleService` methods all accept DataFrames and return modified
DataFrames. This works in Streamlit where DataFrames live in `st.session_state` across reruns.
It does not work in FastAPI where there is no session state and every request is independent.

If services remain DataFrame-based, the "FastAPI-ready" claim is false. The DataFrames will
need to be replaced anyway in Phase 2, at the cost of rewriting every service method.

By enforcing stateless services now — services read from the database via repositories, compute,
write back, return a result — the migration to FastAPI in Phase 2 requires only adding the
HTTP routing layer. The business logic is untouched.

`st.session_state` is a Streamlit-layer concern only. Pages read from the database (via
services) and cache results in session state for UI responsiveness. Session state is never
the source of truth — the database is.

---

### 4.7 Skill Levels Normalized Into a Junction Table

**V1 proposed:** Four columns `Niveau 1`, `Niveau 2`, `Niveau 3`, `Niveau 4` on `technicians`.

**V2 changes:** Introduce a `technician_skills` table with one row per `(technician, level)`.

**Why:** The four horizontal columns mean that adding a fifth skill level requires a schema
migration. A junction table makes skill levels extensible without schema changes. It also allows
querying across levels cleanly: "find all technicians with a Level 3 score above 15" becomes a
simple `WHERE` clause rather than a `CASE` expression.

The four levels (1–4) map to a real certification system and are unlikely to change in the
short term. This normalization is not over-engineering — it is the correct relational model for
a one-to-many relationship between a technician and their scored skill levels.

---

### 4.8 Natural Keys Are Indexed but Not the Primary Key

**V1 proposed:** `Matricule` as string PK for technicians, `SAP` as string PK for orders.

**V2 changes:** Use surrogate integer PKs everywhere. Treat `matricule` and `sap_number` as
unique indexed natural keys.

**Why:** `Matricule` and SAP numbers are external identifiers assigned by HR and ERP systems.
External systems have reassigned identifiers before. If a `Matricule` is ever reused or
corrected, a natural PK cascades the change to every foreign key in every related table. A
surrogate integer PK means the database has its own identity independent of external systems.
Natural keys remain unique and indexed for lookups but carry no relational weight.

---

### 4.9 Phase 3 Expertise Override Is a First-Class Flag

**V1 proposed:** Mark Phase 3 (expertise-bypassing) assignments with the string
"Capacity fill - may not match expertise" in a `Remark` column.

**V2 changes:** Add a boolean `is_expertise_override` column to `schedule_assignments`. The
Remark text can still be set, but the override is queryable and the UI must surface it visibly.

**Why:** A remark string buried in a column is not visible to a manager reviewing a printed or
filtered schedule. An expertise mismatch in a factory production context is a real quality risk.
It must be surfaced as a distinct, filterable status — not hidden in freetext. The flag also
allows the application to prompt for manager confirmation before generating a schedule that
contains overrides, rather than silently accepting them.

---

### 4.10 Rejected Recommendation: Full Department Entity in Phase 1

**My review recommended:** Add a `Department` or `ProductionLine` entity for schedule isolation.

**V2 rejects this for Phase 1.** Add a `department` string field on `technicians` and
`production_orders` instead.

**Why rejected:** The factory currently operates as a single scheduling unit. There is no
evidence from the codebase, data files, or product vision that multi-department isolation is
needed in Phase 1. Introducing a full `Department` entity with foreign keys before the need
is proven adds join complexity and migration risk with no immediate benefit.

The `department` string field preserves the data for future promotion to a proper entity.
When the need arises, a migration creates the `departments` table and replaces the string column
with a foreign key.

---

### 4.11 Rejected Recommendation: Order Splitting

**My review flagged:** Orders cannot be split across technicians or days.

**V2 does not implement order splitting.** This constraint is acknowledged and documented.

**Why rejected:** Order splitting changes the fundamental unit of the scheduling algorithm.
It would require redesigning how the three-phase assignment works, how progress is tracked,
and how completion is reported. The product vision explicitly says correctness first, and the
scheduling algorithm is the heart of the system. Introducing splitting before the core is
stable and tested would be premature. This is deferred to Phase 3+ and documented as a known
constraint.

---

## 5. Complete Database Schema

### Table: `users`

Stores application users for authentication and role enforcement.

```
users
─────────────────────────────────────────────────────
id                INTEGER         PRIMARY KEY (serial)
username          VARCHAR(100)    UNIQUE NOT NULL
password_hash     VARCHAR(255)    NOT NULL          -- bcrypt output
role              VARCHAR(20)     NOT NULL          -- admin | manager | user
is_active         BOOLEAN         NOT NULL DEFAULT true
created_at        TIMESTAMPTZ     NOT NULL DEFAULT now()
updated_at        TIMESTAMPTZ     NOT NULL DEFAULT now()
```

**Rationale:** V1 had no `users` table despite multi-user support being a stated goal. Roles
are enforced at the application layer by checking `session_state.role` against page-level
permission lists. Three roles: `admin` (full access), `manager` (schedule management + reports),
`user` (read-only + status updates for their own orders).

---

### Table: `technicians`

Master technician records. Only identity and metadata — skills are in `technician_skills`.

```
technicians
─────────────────────────────────────────────────────
id                INTEGER         PRIMARY KEY (serial)
matricule         VARCHAR(50)     UNIQUE NOT NULL    -- external badge number
full_name         VARCHAR(200)    NOT NULL
department        VARCHAR(100)    NULL               -- simple field, not FK (Phase 1)
is_active         BOOLEAN         NOT NULL DEFAULT true
created_at        TIMESTAMPTZ     NOT NULL DEFAULT now()
updated_at        TIMESTAMPTZ     NOT NULL DEFAULT now()

INDEX: idx_technicians_matricule ON (matricule)
```

**Rationale:** `Classification` and `Expertise Class` are not stored here — they are computed
by `TechnicianService` from `technician_skills` at read time.

---

### Table: `technician_skills`

Normalized skill scores per technician per certification level.

```
technician_skills
─────────────────────────────────────────────────────
id                INTEGER         PRIMARY KEY (serial)
technician_id     INTEGER         NOT NULL REFERENCES technicians(id) ON DELETE CASCADE
skill_level       INTEGER         NOT NULL          -- 1, 2, 3, or 4
score             INTEGER         NOT NULL DEFAULT 0
updated_at        TIMESTAMPTZ     NOT NULL DEFAULT now()

UNIQUE (technician_id, skill_level)
INDEX: idx_tech_skills_tech_id ON (technician_id)
```

**Rationale:** Replaces the four horizontal `Niveau 1`–`Niveau 4` columns. One row per
`(technician, level)` pair. The classification algorithm reads all four rows for a technician,
finds the one with the highest score, and maps it to `Basic Knowledge / Above Average / Good /
Advanced`. This logic lives in `TechnicianService.compute_expertise_class()`, not in the DB.

---

### Table: `products`

SAP product catalogue. Stable reference data.

```
products
─────────────────────────────────────────────────────
id                INTEGER         PRIMARY KEY (serial)
sap_number        VARCHAR(100)    UNIQUE NOT NULL    -- external SAP material number
description       VARCHAR(500)    NOT NULL
routing_time_minutes  NUMERIC(8,2) NOT NULL
created_at        TIMESTAMPTZ     NOT NULL DEFAULT now()
updated_at        TIMESTAMPTZ     NOT NULL DEFAULT now()

INDEX: idx_products_sap ON (sap_number)
```

**Rationale:** `Class` and `Class Code` are not stored — derived from `routing_time_minutes`
by `ProductService.classify()` using thresholds from `config.py`. Formerly named "Orders" in
V1, renamed to `products` to eliminate the ambiguity between catalogue entries and work orders.

---

### Table: `production_orders`

Work instruction instances from the ERP system, uploaded per shift.

```
production_orders
─────────────────────────────────────────────────────
id                INTEGER         PRIMARY KEY (serial)
erp_order_id      VARCHAR(100)    NOT NULL           -- ERP Order ID (e.g. 2001514763)
product_id        INTEGER         NOT NULL REFERENCES products(id)
priority          VARCHAR(20)     NULL               -- Urgent | A | B | C | null
order_date        DATE            NOT NULL
quantity          INTEGER         NOT NULL DEFAULT 1  -- number of units to produce
department        VARCHAR(100)    NULL
created_at        TIMESTAMPTZ     NOT NULL DEFAULT now()

UNIQUE (erp_order_id, order_date)
INDEX: idx_prod_orders_date ON (order_date)
INDEX: idx_prod_orders_product ON (product_id)
```

**Rationale:** A `ProductionOrder` is a dated work instruction for a specific `Product`. The
`UNIQUE(erp_order_id, order_date)` constraint prevents duplicate scheduling of the same ERP
order on the same day — a bug that exists in the current algorithm. The same ERP order ID
can legitimately recur across different days.

`quantity` is the number of units of the product to be produced for this order. It is a
first-class field, not a note. The **effective scheduling time** for the order is
`product.routing_time_minutes × quantity`. All capacity checks, workload calculations, and
schedule display use the effective time. A production order is treated as atomic: its full
quantity is assigned to a single technician. Splitting a quantity across technicians is
deferred to Phase 3 (see Open Question 5 and Known Constraints).

---

### Table: `shifts`

Daily availability record per technician, uploaded from the shifts Excel file.

```
shifts
─────────────────────────────────────────────────────
id                INTEGER         PRIMARY KEY (serial)
technician_id     INTEGER         NOT NULL REFERENCES technicians(id)
shift_date        DATE            NOT NULL
is_working        BOOLEAN         NOT NULL DEFAULT false
is_transferred    BOOLEAN         NOT NULL DEFAULT false  -- "To another"
break_minutes     INTEGER         NOT NULL DEFAULT 30
extra_time_minutes INTEGER        NOT NULL DEFAULT 0
created_at        TIMESTAMPTZ     NOT NULL DEFAULT now()

UNIQUE (technician_id, shift_date)
INDEX: idx_shifts_date ON (shift_date)
```

**Rationale:** V1 had no `date` field on `Shift`, making it impossible to store historical
shifts or query utilisation across days. `UNIQUE(technician_id, shift_date)` prevents duplicate
shift records for the same technician on the same day. `working_time_minutes` is not stored —
it is computed by `ShiftService.compute_working_time()` as
`480 - break_minutes + extra_time_minutes`. The workday is 8 hours (480 minutes); the 30-minute
break is already inside those 480 minutes and is subtracted via `break_minutes`, so no
additional `+30` offset is applied. Confirmed by the product owner 2026-06-30 (resolves
Section 18, Decision 1). `Technician Name` is not stored here — it is read by joining to
`technicians`.

---

### Table: `schedule_assignments`

The primary scheduling output: which technician is assigned to which production order.

```
schedule_assignments
─────────────────────────────────────────────────────
id                    INTEGER         PRIMARY KEY (serial)
schedule_row_id       UUID            UNIQUE NOT NULL DEFAULT gen_random_uuid()
production_order_id   INTEGER         NOT NULL REFERENCES production_orders(id)
technician_id         INTEGER         NOT NULL REFERENCES technicians(id)
schedule_date         DATE            NOT NULL
sequence_number       INTEGER         NOT NULL      -- position within the day
status                VARCHAR(30)     NOT NULL DEFAULT 'Planned'
                                                  -- Planned | In Progress |
                                                  -- Partially Completed |
                                                  -- Completed | Blocked
routing_time_minutes  NUMERIC(8,2)    NOT NULL      -- snapshot at scheduling time
                                                  -- may differ from product if modified
remaining_time_minutes NUMERIC(8,2)   NOT NULL      -- updated on each stop/end
remark                TEXT            NULL
is_expertise_override BOOLEAN         NOT NULL DEFAULT false  -- Phase 3 assignment
was_unblocked_by_manager BOOLEAN      NOT NULL DEFAULT false  -- manager-initiated unblock
created_at            TIMESTAMPTZ     NOT NULL DEFAULT now()
updated_at            TIMESTAMPTZ     NOT NULL DEFAULT now()

UNIQUE (production_order_id, schedule_date)         -- one assignment per order per day
INDEX: idx_assignments_date ON (schedule_date)
INDEX: idx_assignments_technician ON (technician_id, schedule_date)
INDEX: idx_assignments_status ON (status)
```

**Rationale:** Splits the original 22-column `ScheduleRow` into its assignment-specific
columns. Denormalized names are removed — read from `technicians` and `products` via joins.
`routing_time_minutes` is kept as a snapshot because the UI allows per-assignment routing time
modification that should not alter the product catalogue. `is_expertise_override` replaces the
freetext "Capacity fill" remark and makes Phase 3 assignments queryable and visually distinct.
`schedule_row_id` is a UUID preserved for backward compatibility with existing saved schedules
during the migration. `was_unblocked_by_manager` records whether a `Blocked` assignment was
re-opened by a manager action (as opposed to becoming eligible automatically);
`DailyOrderPoolService` reads this flag to decide whether a blocked order re-enters the
assignable pool (see Section 7).

**Status constraint** should be enforced as a PostgreSQL `CHECK` constraint:
```
CHECK (status IN ('Planned', 'In Progress', 'Partially Completed', 'Completed', 'Blocked'))
```

---

### Table: `work_sessions`

Individual start/stop intervals for an assignment. Replaces the `WorkSessions` JSON column.

```
work_sessions
─────────────────────────────────────────────────────
id                INTEGER         PRIMARY KEY (serial)
assignment_id     INTEGER         NOT NULL REFERENCES schedule_assignments(id) ON DELETE CASCADE
started_at        TIMESTAMPTZ     NOT NULL
stopped_at        TIMESTAMPTZ     NULL              -- NULL means currently in progress
created_at        TIMESTAMPTZ     NOT NULL DEFAULT now()

INDEX: idx_work_sessions_assignment ON (assignment_id)

CHECK (stopped_at IS NULL OR stopped_at > started_at)
```

**Rationale:** Replaces the JSON column entirely. Each row is one contiguous work interval.
Integrity is enforced: `stopped_at` must be after `started_at`. Overlapping sessions for the
same technician can be detected with a query — not possible with JSON.

`TotalTimeSpent` on the old schedule row is derivable as
`SUM(EXTRACT(EPOCH FROM (stopped_at - started_at)) / 60)` over closed sessions for an
assignment. This value can be cached on `schedule_assignments.remaining_time_minutes` for UI
performance, but `work_sessions` is the source of truth.

`FirstStartTime` on the old row is `MIN(started_at)` for an assignment's sessions.
`EndTime` is the `stopped_at` of the last session where the assignment status became Completed.

---

### Table: `schedule_locks` *(Phase 1 — lightweight concurrency guard)*

Prevents two users from generating a schedule for the same date simultaneously.

```
schedule_locks
─────────────────────────────────────────────────────
id                INTEGER         PRIMARY KEY (serial)
schedule_date     DATE            UNIQUE NOT NULL
locked_by         INTEGER         NOT NULL REFERENCES users(id)
locked_at         TIMESTAMPTZ     NOT NULL DEFAULT now()
released_at       TIMESTAMPTZ     NULL
```

**Rationale:** The scheduling algorithm runs as a long computation that produces many rows.
Without a lock, two managers clicking "Generate Schedule" simultaneously produce interleaved
writes to `schedule_assignments`. This table provides a simple advisory lock at the application
layer. Before generating a schedule, the service checks for an unreleased lock on that date.
If one exists, the generation is rejected with an informative error. The lock is released when
generation completes or fails. Stale locks (released_at IS NULL and locked_at is old) are
cleaned up on startup.

---

## 6. Entity Relationship Summary

```
users
  │
  └── (created_by, optional future)

technicians ──── technician_skills (1:many, one row per skill level)
     │
     └── shifts (1:many, one per date)
     └── schedule_assignments (1:many, one per assigned order per date)

products ──── production_orders (1:many, one product → many orders)
                    │
                    └── schedule_assignments (1:1 per date)
                              │
                              └── work_sessions (1:many)

schedule_locks (independent, keyed by date)
```

---

## 7. Layer Definitions

### Layer 1 — Streamlit Frontend (Presentation)

**Responsibility:** Render UI, collect user input, display data, manage session state.

**Rules:**
- May call Service layer methods only. Never calls Repository layer directly.
- May read/write `st.session_state` freely.
- May not contain business logic (classification, scheduling decisions).
- May not write to the database directly.
- Session state caches data for UI performance. The database is always the source of truth.

**Files:** `app.py`, `pages/*.py`, `utils/ui_components.py`, `utils/session_manager.py`

---

### Layer 2 — Service Layer (Business Logic)

**Responsibility:** Enforce business rules, orchestrate multi-step operations, compute derived
values, manage transactions.

**Rules:**
- Stateless. No method reads from `st.session_state`. No method returns a `pd.DataFrame`.
- Receives domain objects or primitives. Returns domain objects or result objects.
- Manages transaction boundaries. Wraps multi-table writes in a single SQLAlchemy session.
- Contains all classification logic, expertise matching, priority sorting, and scheduling phases.
- May raise domain exceptions (e.g. `ExpertiseConflictError`, `ScheduleLockError`).

**Target files:**
- `services/scheduling_service.py` — scheduling algorithm (refactored from `initial_scheduling.py`)
- `services/daily_pool_service.py` — `DailyOrderPoolService`: resolves in-progress carryover,
  blocked-order carryover, and late-order collection before each day's scheduling run
- `services/technician_service.py` — technician CRUD + expertise computation
- `services/order_service.py` — product CRUD + production order management + bulk upload
- `services/shift_service.py` — shift parsing, working time computation
- `services/schedule_service.py` — assignment mutations (status, reassign, priority, block)
- `services/auth_service.py` — login, logout, role checking

---

### Layer 3 — Repository Layer (Data Access)

**Responsibility:** Translate between domain objects and database rows using SQLAlchemy.

**Rules:**
- One repository per aggregate root (Technician, Product, ProductionOrder, ScheduleAssignment, etc.).
- Contains only database operations: `get`, `get_all`, `save`, `delete`, `find_by_*`.
- No business logic. No classification. No scheduling decisions.
- Returns SQLAlchemy model instances or typed domain objects. Never raw SQL results to callers.
- Does not manage transactions — receives a `session` argument from the service layer.

**Target files:**
- `repositories/technician_repository.py`
- `repositories/product_repository.py`
- `repositories/production_order_repository.py`
- `repositories/schedule_repository.py`
- `repositories/shift_repository.py`
- `repositories/user_repository.py`

---

### Layer 4 — Database (PostgreSQL 15)

**Responsibility:** Durable storage, integrity enforcement, indexing.

**Rules:**
- Schema managed exclusively by Alembic migrations. No manual DDL in production.
- Check constraints enforce valid status values and temporal ordering in `work_sessions`.
- Unique constraints enforce business rules (one assignment per order per day, etc.).
- Application DB user has: `SELECT`, `INSERT`, `UPDATE`, `DELETE` on application tables.
  No `DROP`, `CREATE`, `TRUNCATE`, no schema privileges. Migrations run under a separate
  privileged user.

---

## 8. SQLAlchemy ORM Mode

Use SQLAlchemy 2.x **declarative ORM** throughout. Do not mix ORM and Core styles in the same
repository. ORM models live in `db/models.py`. All relationships are declared with
`relationship()` and `ForeignKey`.

Reason: The ORM provides identity map caching, lazy/eager loading control, and clean
relationship traversal — all of which are beneficial for a data model of this complexity.
The Core expression language is reserved for performance-critical bulk operations if they
arise (e.g. bulk schedule insert).

---

## 9. Scheduling Algorithm (Preserved Exactly)

The three-phase algorithm in `create_initial_schedule()` is preserved without behavioral
change. The refactoring moves it from `models/initial_scheduling.py` to
`services/scheduling_service.py` and replaces DataFrame I/O with repository calls and domain
objects. The algorithm logic itself is not modified.

### Pre-processing (unchanged)

1. Load all `ProductionOrder` records for the target date from the repository.
2. Validate that all SAP numbers exist in `products`. Abort with a list of missing SAPs if not.
3. Enrich orders with `routing_time_minutes`, `Class Code` from `products`.
4. Compute `effective_time_minutes = routing_time_minutes × quantity` per order. All
   subsequent capacity checks, workload tracking, and sort operations use
   `effective_time_minutes`. The per-unit `routing_time_minutes` is retained on the
   assignment as a snapshot for display and manager modification.
5. Load `Shift` records for the target date. Filter to `is_working=true` and
   `is_transferred=false`. Compute `working_time_minutes` per technician.
6. Sort orders: `Priority_Num` ascending (Urgent=0, A=1, B=2, C=3, None=999), then
   `effective_time_minutes` descending within each priority bucket.

### Phase 1 — Round-Robin Seeding (unchanged)

Assign one order to each working technician before any technician gets a second order.
Assignment requires: `technician.expertise_class >= order.class_code` AND
`technician.remaining_time >= order.effective_time_minutes`.

### Phase 2 — Balanced Priority Assignment (unchanged)

For each remaining order (in priority order), find all qualified technicians with sufficient
time. Select the technician with: lowest total assigned time → exact expertise match preferred
→ most remaining time as tiebreaker.

### Phase 3 — Capacity Fill (behavior preserved, visibility enhanced)

For each remaining unscheduled order, find any technician with sufficient remaining time,
ignoring expertise. Assign to the technician with the least total assigned time.

**Why expertise is ignored here:** leaving an order unscheduled while a technician sits idle
blocks production — a worse outcome than a flagged expertise mismatch. Confirmed by the
product owner 2026-06-30 (resolves Section 18, Decisions 2 and 6); this also overrides a
literal reading of `docs/FLOWCHART.md`'s "Expertise adequate" label on Rounds 2 & 3, which
applies to Round 2 only.

**Change from V1:** Set `is_expertise_override = true` on the `ScheduleAssignment` row.
Do not just write a string to `remark`. The UI renders expertise-override assignments with
a visible warning indicator. The schedule summary reports the count of override assignments
separately. The assignment happens automatically as part of schedule generation — there is
no confirmation gate that delays or withholds it. The manager acknowledgement is an
informational notice shown immediately after generation, not a precondition for finalizing
the schedule.

### Order Deduplication (new enforcement)

The `UNIQUE(erp_order_id, order_date)` constraint on `production_orders` prevents the same
ERP order from appearing twice in the scheduling input. At the service layer, the bulk upload
step deduplicates before writing — duplicate ERP order IDs in the uploaded file are reported
to the user and skipped, not silently accepted.

### Known Constraint: No Order Splitting

An order that exceeds any single technician's remaining capacity is placed in the unscheduled
list. Orders are not split across technicians or across days. This is a documented constraint
for Phase 1 and Phase 2. Order splitting is deferred to Phase 3+ and requires a redesign of
the assignment and progress-tracking model.

---

## 10. Authentication Architecture

### Phase 1 (Streamlit + DB)

```
Login form (Streamlit)
    │
    ▼
AuthService.login(username, password)
    │
    ├── UserRepository.find_by_username(username)
    │       └── SELECT * FROM users WHERE username = ? AND is_active = true
    │
    ├── bcrypt.checkpw(password, user.password_hash)
    │
    └── On success: write user_id, username, role to st.session_state
```

**Password requirements:** bcrypt cost factor 12 minimum. No plaintext storage. No credentials
in source code, `config.py`, or environment variables baked into Docker images. Use Streamlit
Secrets (`secrets.toml`, not committed) or environment variables for the DB connection string.

**Role enforcement:** Each page function checks `st.session_state.role` against a required
role. Pages that require `manager` or `admin` redirect to an "Access Denied" view if the
role does not match. This is explicit per-page, not a decorator — Streamlit does not support
decorators on page functions in a way that prevents rendering.

**Brute-force mitigation:** Track failed login attempts in `st.session_state`. After 5
consecutive failures from the same session, add a 30-second delay before the next attempt is
processed. This is a session-level guard, not IP-level. IP-level rate limiting is delegated
to the reverse proxy (nginx or Streamlit Cloud infrastructure).

### Phase 2 (FastAPI)

When FastAPI is introduced, JWT is implemented at the HTTP layer. The `AuthService` business
logic does not change — only the transport mechanism changes. FastAPI issues a signed JWT on
successful login. Streamlit calls FastAPI endpoints with the token in the `Authorization`
header. The `users` table and bcrypt validation remain unchanged.

---

## 11. Transaction Strategy

The service layer manages all transaction boundaries. Repositories receive a `session`
argument and do not commit or rollback themselves.

**Rule:** One SQLAlchemy `Session` per top-level service operation. The service opens a
session, calls one or more repositories, and commits if all succeed or rolls back if any fail.

**Critical transaction: schedule generation**

Schedule generation writes `N` rows to `schedule_assignments` and potentially `N` rows to
`production_orders` in a single operation. If any write fails, the entire schedule for that
date is rolled back. Partial schedules are not committed.

```
SchedulingService.generate_schedule(date):
    with db.session() as session:
        acquire_lock(session, date)          # write to schedule_locks
        orders = order_repo.find_by_date(session, date)
        shifts = shift_repo.find_by_date(session, date)
        assignments = algorithm.run(orders, shifts)  # pure computation, no DB calls
        assignment_repo.bulk_insert(session, assignments)
        session.commit()
        release_lock(session, date)
```

The algorithm runs as a pure computation (no I/O) on domain objects. Only the load and save
steps touch the database. This makes the algorithm testable without a database.

---

## 12. Migration Strategy: CSV to PostgreSQL

This is a one-time operation performed when the application is first deployed with the
database backend. It is not an Alembic migration — Alembic manages schema, not data.

**Order of migration:**

1. `users` — seed the three initial users (`admin`, `manager`, `user`) with bcrypt-hashed
   versions of the existing passwords. Delete from `config.py` after seeding.

2. `technicians` + `technician_skills` — read `data/technicians_file.csv`, insert one
   `technicians` row per record and four `technician_skills` rows per technician (Niveau 1–4).

3. `products` — read `data/products_classified.csv`, insert one `products` row per SAP number.
   Do not migrate `Class` or `Class Code` — these are computed.

4. `production_orders` + `schedule_assignments` + `work_sessions` — read
   `data/current_schedule.csv` if it exists. Reconstruct `ProductionOrder` rows from the
   schedule data. Insert `ScheduleAssignment` rows. Reconstruct `WorkSession` rows from the
   `WorkSessions` JSON column before discarding it.

5. `reclamations` — fully deferred to advanced level. Not migrated in Phase 1 or Phase 2.

**Verification:** After migration, the application runs both the CSV read path and the DB read
path in parallel for one shift (read from DB, compare counts and key fields against CSV) before
the CSV path is removed.

**Alembic:** Manages schema creation and evolution only. The initial `alembic revision --autogenerate`
produces the baseline schema. All subsequent schema changes go through Alembic revisions.
Migrations run manually by an operator before deployment, not automatically on application
startup. This prevents accidental migrations on restart.

---

## 13. Security Considerations

### Credentials and Secrets

- No credentials, passwords, or connection strings in source code or version control.
- DB connection string in environment variable `DATABASE_URL`.
- Streamlit secrets (`secrets.toml`) for local development, excluded from git via `.gitignore`.
- Application DB user has minimum necessary privileges (no DDL, no `TRUNCATE`).
- Migration user (DDL privileges) is separate and never used by the running application.

### Input Validation

- File uploads (Excel, CSV) are parsed in a try/except with openpyxl. The maximum file size
  should be limited at the Streamlit or reverse proxy level.
- All text inputs (SAP numbers, matricules, descriptions) are validated against length limits
  and character whitelists before reaching the repository layer. SQL injection is mitigated
  by SQLAlchemy's parameterised queries — raw string interpolation into SQL is prohibited.

### Personal Data (GDPR consideration)

Technician records contain names and badge numbers (PII). At minimum:
- Restrict the Manage Technicians page to `admin` role.
- Do not log full names in application logs.
- Document a data retention policy for schedule history (how long are completed schedules kept?).
  This decision is deferred to Phase 1 completion but must be made before production deployment.

### Session Security

- `st.session_state` is server-side in Streamlit. It is not exposed to the client.
- On logout, clear all session state keys, not just `logged_in`.
- Do not expose the role or user_id in URL parameters.

---

## 14. Known Constraints and Accepted Limitations

These are not bugs. They are deliberate Phase 1 constraints that must be documented and
communicated to users.

| Constraint | Details | Future resolution |
|---|---|---|
| Single-day scheduling | Schedules are generated for one date at a time. No multi-day view. | Phase 2: date-range scheduling |
| No order splitting | An order that no single technician can complete is unscheduled. | Phase 3: split orders |
| No real-time push | Status changes are visible only after page refresh. | Phase 2: polling or SSE |
| Single department | All technicians and orders share one schedule namespace. | Phase 2: promote `department` field to entity |
| No schedule history | Previous days' schedules are kept in DB but there is no historical report UI. | Phase 2: reporting page |
| Reclamations | Fully deferred to advanced level. Page removed from sidebar navigation. | Advanced level |

---

## 15. Deferred Items

| Item | Reason for deferral |
|---|---|
| FastAPI backend | Not needed until multi-client or mobile access is required |
| JWT authentication | Depends on FastAPI HTTP endpoints |
| AI chatbot | Requires stable core and a separate product decision |
| Full audit log table | `work_sessions` covers operational tracking. Full audit (who changed what, when, by whom) is deferred until multi-user accountability becomes a compliance requirement |
| Reclamations | Fully deferred to advanced level. Not in Phase 1 or Phase 2 scope. Page is removed from sidebar navigation. |
| React frontend | Optional, long-term only |
| Multi-department isolation | Requires promoting `department` field to a proper entity and redesigning the schedule page |
| Gantt / workload visualisation | Nice to have, not core scheduling correctness |
| Order splitting | Requires algorithm redesign |

---

## 16. Phase Roadmap

### Phase 0 — Stabilise (pre-database, current codebase)

Fix everything that causes runtime errors or incorrect behavior in the existing CSV-based system.
No database work. No new features.

1. Remove the Reclamations page from the sidebar navigation in `app.py`. It is fully deferred
   and must not be accessible. Do not fix its internal code.
2. Move credentials out of `config.py` into environment variables / Streamlit secrets.
3. Collapse `FileService` and `PersistenceService` into one save path.
4. Remove `st.warning()` / `st.write()` calls from `models/initial_scheduling.py`.
5. Remove dead commented-out algorithm code.
6. Remove unused `cumulative_scheduled_orders` global.
7. Extract the four inline page functions in `app.py` into `pages/` classes.

**Exit criterion:** All active pages (Schedule Management, Initial Scheduling, Manage
Technicians, Manage Orders) run without runtime errors. Reclamations page is not reachable.

---

### Phase 1 — Database Migration

Introduce PostgreSQL, SQLAlchemy, Alembic, and the Repository layer. Migrate all data.
Replace all CSV I/O with DB repository calls. Add role enforcement.

1. Write SQLAlchemy models for all tables defined in Section 5.
2. Write Alembic baseline migration.
3. Write Repository layer (one file per aggregate root).
4. Refactor services to be stateless: receive domain objects, return domain objects.
5. Migrate CSV data to DB (migration script, not Alembic).
6. Implement `users` table, bcrypt auth, and role-based page access.
7. Implement `is_expertise_override` flag and UI surfacing.
8. Implement `schedule_locks` for concurrent generation guard.
9. Remove all CSV files from the application's operational path.

**Exit criterion:** Application runs identically to Phase 0 but reads/writes PostgreSQL.
No CSV files needed to run the app.

---

### Phase 2 — Reliability and Operations

Add FastAPI, JWT auth, historical reporting, real-time refresh, multi-department support,
monitoring, and deployment infrastructure.

---

### Phase 3 — Advanced Features

Order splitting, AI scheduling assistance, chatbot, mobile interface.

---

## 17. Architecture Diagram

```
┌──────────────────────────────────────────────────────────────┐
│                  STREAMLIT FRONTEND                          │
│                                                              │
│  app.py (navigation) + pages/ (one class per page)          │
│  utils/session_manager.py  utils/ui_components.py           │
│                                                              │
│  Rule: reads DB via services; caches results in             │
│  st.session_state; no direct repository calls               │
└──────────────────────────┬───────────────────────────────────┘
                           │ domain objects / result objects
                           │ (no DataFrames, no st.session_state)
┌──────────────────────────▼───────────────────────────────────┐
│                   SERVICE LAYER                              │
│                                                              │
│  SchedulingService   — 3-phase algorithm (stateless)        │
│  DailyOrderPoolService — in-progress/blocked/late carryover  │
│  ScheduleService     — assignment mutations, status FSM      │
│  TechnicianService   — CRUD + expertise computation          │
│  OrderService        — product CRUD + bulk upload            │
│  ShiftService        — shift parsing + working time          │
│  AuthService         — login, logout, role check             │
│                                                              │
│  Rule: opens DB session; manages transactions;              │
│  calls repositories; commits or rolls back                  │
└──────────────────────────┬───────────────────────────────────┘
                           │ SQLAlchemy session + domain objects
┌──────────────────────────▼───────────────────────────────────┐
│                 REPOSITORY LAYER                             │
│                                                              │
│  TechnicianRepository    ProductRepository                   │
│  ProductionOrderRepository  ScheduleRepository               │
│  ShiftRepository         UserRepository                      │
│                                                              │
│  Rule: receives session; never commits; returns ORM          │
│  instances; no business logic                                │
└──────────────────────────┬───────────────────────────────────┘
                           │ SQLAlchemy ORM queries
┌──────────────────────────▼───────────────────────────────────┐
│                   PostgreSQL 15                              │
│                                                              │
│  users              technicians       technician_skills      │
│  products           production_orders shifts                 │
│  schedule_assignments  work_sessions  schedule_locks         │
│                                                              │
│  Schema managed by Alembic.                                  │
│  App user: SELECT / INSERT / UPDATE / DELETE only.           │
└──────────────────────────────────────────────────────────────┘

                    (Phase 2 addition)
┌──────────────────────────────────────────────────────────────┐
│                    FastAPI (future)                          │
│  Sits between Streamlit and Service layer.                   │
│  Services unchanged. JWT auth added at HTTP layer.           │
└──────────────────────────────────────────────────────────────┘
```

---

## 18. Decisions Confirmed and Open Questions Remaining Before Phase 1 Begins

Decisions 1, 2, and 6 below were flagged as open questions and have since been confirmed by
the product owner. Decisions 3, 4, and 5 remain open.

### Confirmed (2026-06-30)

1. **Working-time formula — RESOLVED.** `working_time_minutes = 480 − break_minutes +
   extra_time_minutes`. No `+30` offset; the 30-minute break is already inside the 480-minute
   workday and is subtracted via `break_minutes`. Use this formula in
   `ShiftService.compute_working_time()`.

2. **Phase 3 expertise override — RESOLVED.** The system keeps the original design: Phase 3
   ignores expertise and assigns automatically to any technician with sufficient remaining
   time. There is no hard block and no confirmation gate that withholds the assignment —
   leaving an order unscheduled while a technician is idle blocks production, which the
   product owner judged worse than a flagged expertise mismatch. `is_expertise_override =
   true` is set on the resulting row; the manager sees a summary count immediately after
   generation as an informational notice, not an approval step.

6. **Rounds 2 & 3 vs. the flowchart's "Expertise adequate" label — RESOLVED.**
   `docs/FLOWCHART.md` labels both capacity-fill rounds "Expertise adequate," which read
   literally would mean Phase 3 should also enforce expertise. The product owner confirmed
   this is not the intent: the label describes Round 2 (the preferred, expertise-matched
   path); Round 3 remains the expertise-ignoring last resort described in Decision 2 above
   and in Section 9. `IMPLEMENTATION_ROADMAP.md` has been corrected to match.

### Still open

3. **Data retention:** How long should completed schedule records be kept in the database?
   This determines whether `schedule_assignments` ever needs archiving or partitioning.

4. **Initial user credentials:** Who creates the initial `admin` user in the `users` table?
   A seed script run once at deployment? If so, what is the initial password and how is it
   communicated securely?

5. **Quantity and capacity splitting:** A production order with `quantity > 1` is treated as
   atomic in Phase 1 — one technician completes all units. Should the algorithm ever allow
   splitting a quantity across multiple technicians (e.g. Technician A produces 3 units,
   Technician B produces 2 units of the same order with `quantity = 5`)? This would change
   the capacity check, the assignment model, and the completion tracking significantly.
   Confirm the intended behavior before implementing `SchedulingService`. Until confirmed,
   the atomic assumption holds.
