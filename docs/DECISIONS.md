# DASS — Architecture Decision Record

**Project:** Draexlmaier Automated Scheduling System  
**Date:** 2026-06-30  
**Maintainer:** Product Owner  
**Status:** Active — append new decisions as they are made; do not remove resolved entries.

This document is the permanent record of every significant architectural and technical decision
made for DASS. Each entry uses the ADR format: Decision, Context, Alternatives Considered,
Chosen Solution, Rationale, Consequences, Future Considerations.

---

## Table of Contents

| ADR | Title | Status |
|---|---|---|
| ADR-001 | Retain Streamlit as the frontend framework | Approved |
| ADR-002 | Adopt PostgreSQL 15 as the persistence layer | Approved |
| ADR-003 | Use SQLAlchemy 2.x ORM mode and Alembic for migrations | Approved |
| ADR-004 | Layered monolith — four-layer architecture | Approved |
| ADR-005 | Service layer must be stateless | Approved |
| ADR-006 | Repository pattern with session injection | Approved |
| ADR-007 | Phase 1 authentication: bcrypt + DB session; defer JWT to Phase 2 | Approved |
| ADR-008 | Separate Product (catalogue) from ProductionOrder (work instruction) | Approved |
| ADR-009 | Quantity is a first-class field; effective time drives all capacity checks | Approved |
| ADR-010 | Computed values are never stored in the database | Approved |
| ADR-011 | Surrogate integer primary keys over natural keys | Approved |
| ADR-012 | Technician skill levels normalized into a junction table | Approved |
| ADR-013 | Replace WorkSessions JSON column with a normalized work_sessions table | Approved |
| ADR-014 | Split the 22-column ScheduleRow into ScheduleAssignment and WorkSession | Approved |
| ADR-015 | Phase 3 scheduling: ignore expertise as automatic last-resort fallback | Approved |
| ADR-016 | is_expertise_override flag replaces freetext remark string | Approved |
| ADR-017 | Working-time formula: 480 − break_minutes + extra_time_minutes | Approved |
| ADR-018 | DailyOrderPoolService resolves carryover before each scheduling run | Approved |
| ADR-019 | was_unblocked_by_manager column tracks manager-initiated unblocking | Approved |
| ADR-020 | schedule_locks table guards concurrent schedule generation | Approved |
| ADR-021 | Defer reclamations to advanced level; remove from navigation immediately | Approved |
| ADR-022 | Defer order splitting to Phase 3 | Approved |
| ADR-023 | Department as a string field in Phase 1; defer full entity to Phase 2 | Approved |
| ADR-024 | Three-environment infrastructure: local → Streamlit Cloud demo → AWS RDS | Approved |
| ADR-025 | Credential and database privilege security constraints | Approved |
| ADR-026 | Incremental refactoring over rewrite | Approved |
| ADR-027 | Tests run against real PostgreSQL; no mocking the database | Approved |

---

## ADR-001 — Retain Streamlit as the Frontend Framework

**Date:** 2026-06-23  
**Status:** Approved

### Decision

Continue using Streamlit as the frontend framework throughout Phase 1 and Phase 2.

### Context

The application was built with Streamlit. The product vision calls for making the existing
application work correctly from beginning to end, not rebuilding it. The system is an internal
tool used by assembly managers and technicians — not a public-facing product — so the
constraints that typically push teams toward a JavaScript framework (SEO, mobile-first UX,
public distribution) do not apply here.

### Alternatives Considered

- **React + FastAPI**: Full separation of frontend and backend. More scalable but requires
  rebuilding the entire UI from scratch.
- **Django with server-side templates**: Python-native but not in the existing stack; introduces
  a new framework and learning curve for a team already using Streamlit.
- **Retain Streamlit with FastAPI behind it (Phase 2)**: Keeps Streamlit UI while adding a
  proper HTTP layer for API access in the future.

### Chosen Solution

Retain Streamlit for Phase 1 and Phase 2. In Phase 2, place FastAPI between the Streamlit UI
and the service layer to expose HTTP endpoints for potential future clients (mobile, AI chatbot).
The Streamlit pages continue to be the primary interface throughout.

### Rationale

The product vision explicitly states that the priority is correctness, not feature addition.
Replacing the frontend is a feature addition, not a correctness fix. Streamlit is already
deployed, the team knows it, and it is adequate for an internal single-plant scheduling tool.
The service layer is being made fully stateless (see ADR-005), which ensures that adding
FastAPI in Phase 2 is a thin HTTP routing addition — the business logic does not change.

### Consequences

- The application remains a single-process Streamlit deployment.
- Multi-user concurrent access is limited to what Streamlit's session model supports. Two
  managers can use the application simultaneously, but the scheduling algorithm uses
  `schedule_locks` (see ADR-020) to prevent concurrent generation.
- Server-push notifications (e.g. "a technician just blocked an order") are not possible in
  Phase 1 without polling. Status updates are visible after page refresh.

### Future Considerations

- Phase 2 introduces FastAPI as an intermediary layer. Streamlit remains the UI.
- If mobile access or an AI chatbot is eventually required, FastAPI endpoints already exist
  and the Streamlit frontend is optional at that point.
- A React frontend is an option in the long term but is explicitly not planned for Phase 1
  or Phase 2.

---

## ADR-002 — Adopt PostgreSQL 15 as the Persistence Layer

**Date:** 2026-06-23  
**Status:** Approved

### Decision

Replace all flat-file storage (CSV and XLSX) with PostgreSQL 15 in Phase 1.

### Context

The application currently stores all data in files under `data/`: technicians in CSV, products
in CSV, schedules in CSV, work sessions as JSON inside a CSV column, and reclamations in XLSX.
Every write is a full DataFrame overwrite — no transactions, no atomicity, no concurrent access
safety. The product vision explicitly names PostgreSQL as a target. The current design cannot
support multiple simultaneous users without data corruption risk.

### Alternatives Considered

- **SQLite**: Zero configuration, single file. Simpler than PostgreSQL but does not support
  concurrent writers, lacks advanced constraint types, and is not what the product vision
  specifies. The eventual AWS production environment would require a migration to a proper RDBMS
  anyway, making SQLite a stepping stone that adds work without value.
- **MongoDB**: Document store, no schema. Eliminates the need to normalize the data model.
  However, the scheduling data is fundamentally relational (technicians, orders, assignments,
  sessions), and the loss of referential integrity and join capabilities would make queries
  significantly harder.
- **Continue with flat files**: Avoids migration work. Not viable — flat files cannot support
  multi-user access, have no transaction guarantees, and cannot enforce referential integrity.

### Chosen Solution

PostgreSQL 15. The application database is provisioned from scratch — no instance existed
before Phase 1 began. Three environments are used (see ADR-024). Schema is managed entirely
by Alembic. The application DB user holds only DML privileges (see ADR-025).

### Rationale

PostgreSQL is named explicitly in the product vision. It supports the full feature set required:
check constraints for the status state machine, unique constraints for business rules (one
assignment per order per day), referential integrity across nine related tables, and efficient
range queries on dates for historical schedule reporting. It is the appropriate choice for a
production scheduling system that must not lose or corrupt data.

### Consequences

- Phase 1 requires a provisioning step (Task 1.1.0) that has no equivalent in the current
  CSV-based system.
- All existing CSV and XLSX data must be migrated through one-time migration scripts (not
  Alembic migrations — Alembic is schema-only).
- PostgreSQL must be available in all three environments: local development, demo, and
  production. Each uses a different `DATABASE_URL` but the same application code.

### Future Considerations

- The production environment targets AWS RDS for PostgreSQL. The application code is
  environment-agnostic by design — only `DATABASE_URL` changes between environments.
- If the schedule table grows large over time, table partitioning by `schedule_date` becomes
  an option. This is not needed in Phase 1 but the schema is designed to support it.
- Data retention policy for completed schedules (how long are old `schedule_assignments` rows
  kept) is an open question (Section 18, item 3) to be resolved before Phase 1 deployment.

---

## ADR-003 — Use SQLAlchemy 2.x ORM Mode and Alembic for Schema Migrations

**Date:** 2026-06-23  
**Status:** Approved

### Decision

Use SQLAlchemy 2.x in declarative ORM mode for all database access. Use Alembic exclusively
for schema creation and evolution. Do not mix ORM and Core styles in the same repository.

### Context

No ORM exists in the current application — all data is read and written as Pandas DataFrames
from flat files. The target architecture requires a proper data access layer that handles
identity mapping, relationship traversal, and typed objects. Schema migrations need version
control so that changes can be applied reproducibly across all environments.

### Alternatives Considered

- **SQLAlchemy Core only (no ORM)**: Closer to raw SQL. More control but more verbose.
  Relationships must be handled manually, which introduces more boilerplate in the repository
  layer.
- **Raw psycopg2 with manual SQL**: Maximum control, minimum abstraction. Too low-level for a
  data model with nine related tables and relationships; makes join queries error-prone and
  testing difficult.
- **Django ORM**: Excellent ORM but requires the full Django framework. The application is
  built on Streamlit, not Django, and introducing Django's settings, app registry, and
  management commands would be invasive and unnecessary.
- **Flyway (migrations only)**: Java-based. Not suitable in a Python project.

### Chosen Solution

SQLAlchemy 2.x declarative ORM. All ORM models live in `db/models.py`. All relationships are
declared with `relationship()` and `ForeignKey`. Alembic manages schema — the initial baseline
migration is generated with `alembic revision --autogenerate`. All subsequent schema changes go
through Alembic revisions. Migrations are run manually by an operator before deployment, never
automatically on application startup.

### Rationale

SQLAlchemy 2.x is the standard Python ORM for relational databases with an established
ecosystem, good documentation, and direct support for the data model complexity in DASS (nine
tables, multiple one-to-many relationships). The ORM mode provides identity map caching, lazy
and eager loading control, and clean relationship traversal — all useful for a data model with
this many joins. Running Alembic migrations manually prevents accidental schema changes when
the application restarts in a misconfigured environment.

### Consequences

- `db/models.py` is the single definition of the database schema in Python.
- No raw SQL strings in application code. All queries go through the ORM. The one exception
  is performance-critical bulk inserts (e.g. bulk schedule row insertion), where
  SQLAlchemy Core expressions are acceptable but must be isolated to the repository.
- Alembic is a developer tool, not an application dependency at runtime.

### Future Considerations

- If query performance on large schedule tables becomes a concern, SQLAlchemy Core expressions
  can be introduced in specific repository methods without changing the rest of the layer.
- In Phase 2, if FastAPI is added, SQLAlchemy sessions are provided per HTTP request via
  dependency injection — the same ORM models and repository classes work without modification.

---

## ADR-004 — Layered Monolith: Four-Layer Architecture

**Date:** 2026-06-23  
**Status:** Approved

### Decision

Structure the application as a layered monolith with four distinct layers that communicate
strictly downward: Streamlit → Service → Repository → Database.

### Context

The current application has no enforced layer boundaries. `app.py` calls model functions
directly. Model functions call `st.warning()`. Services read DataFrames from `st.session_state`.
The scheduling algorithm calls Streamlit UI functions mid-computation. This coupling makes the
code untestable, fragile, and impossible to extend with a future API layer.

### Alternatives Considered

- **Microservices**: Split into independent deployable services (scheduling service, technician
  service, etc.). Introduces network calls, distributed failure modes, and deployment complexity
  that is inappropriate for an internal single-plant tool at this stage.
- **Two-layer (Streamlit + DB)**: Skip the service and repository layers; call the database
  directly from Streamlit pages. Simple to write initially but produces untestable code and
  makes it impossible to add FastAPI later without rewriting all business logic.
- **Maintain the current flat structure**: No architectural change — just fix the bugs and
  add the database. Not viable because the root cause of maintainability problems is the flat
  structure itself.

### Chosen Solution

A layered monolith deployed as a single process:

1. **Streamlit frontend** — pages, navigation, session state cache.
2. **Service layer** — stateless business logic, transaction management.
3. **Repository layer** — data access, SQLAlchemy ORM operations.
4. **Database** — PostgreSQL 15, schema managed by Alembic.

Each layer may only communicate with the layer directly below it. No layer skips another.
No layer reaches upward.

### Rationale

The layered monolith gives the application clean separation of concerns without the operational
complexity of microservices. The service layer being fully stateless is the key property that
makes the architecture FastAPI-ready: placing an HTTP routing layer in front of the services in
Phase 2 requires no changes to the business logic. The repository layer makes the database
swappable and the services testable without a running database.

### Consequences

- Every new feature must decide which layer it belongs to. The rule is strict: if it touches
  `st.session_state`, it belongs in a page. If it makes a business decision, it belongs in a
  service. If it reads or writes the database, it belongs in a repository.
- The model files in `models/` are legacy artifacts. They are not a fifth layer. Their
  behavior is migrated into services and repositories; the files are then removed.

### Future Considerations

- Phase 2 places FastAPI between the Streamlit frontend and the service layer. The service
  layer is unchanged. The Streamlit pages call FastAPI HTTP endpoints instead of service
  methods directly, or they continue calling service methods directly if the use case does
  not require external API access.

---

## ADR-005 — Service Layer Must Be Stateless

**Date:** 2026-06-23  
**Status:** Approved

### Decision

No service method may read from or write to `st.session_state`. No service method may accept
or return a `pd.DataFrame` as its interface contract. Services receive typed domain objects or
primitives and return typed domain objects or result objects.

### Context

The current `ScheduleService` methods accept DataFrames and return modified DataFrames. This
works in Streamlit where DataFrames live in `st.session_state` across reruns. It does not work
in FastAPI where there is no session state and every request is independent. If services remain
DataFrame-based, the claim that the architecture is FastAPI-ready is false, and every service
method would need to be rewritten in Phase 2.

### Alternatives Considered

- **Allow DataFrames internally, require typed interfaces at service boundaries**: Accept
  DataFrames as arguments from pages, but have internal methods return typed objects.
  This is a compromise that reduces the rewrite scope but still couples the service interface
  to Pandas, making unit testing awkward.
- **Prohibit DataFrames entirely, including in migration scripts**: Too strict — migration
  scripts reading CSV files naturally produce DataFrames and there is no reason to convert
  them before processing.

### Chosen Solution

Services are stateless. They open a database session, load domain objects via repositories,
compute, write back, and return a typed result object. No DataFrame enters or exits a service
method. `st.session_state` is never read or written inside a service. Pages call services and
cache the returned domain objects in session state for UI responsiveness — the session state
cache is a UI concern, not a service concern.

DataFrames are permitted in file-parsing functions (e.g. reading the uploaded Excel file with
openpyxl/pandas), but must be converted to domain objects before being passed to a service.

### Rationale

The statefulness of `st.session_state` and the Pandas-centricity of the current service
signatures are the primary blockers for Phase 2. By enforcing stateless services now — one
time — the Phase 2 migration to FastAPI becomes a thin HTTP routing layer addition with no
business logic changes.

### Consequences

- All existing service methods must be rewritten in Phase 1 to accept and return domain
  objects. This is planned and scheduled in the milestones.
- Domain object classes (DTOs or dataclasses) must be defined for every entity that crosses
  a layer boundary. These live in the service files or a shared `domain/` module.
- Unit tests for services can be written without a running Streamlit session.

### Future Considerations

- In Phase 2, when FastAPI is introduced, it calls service methods identically to how the
  Streamlit pages call them today. No service method needs a new signature.

---

## ADR-006 — Repository Pattern with Session Injection

**Date:** 2026-06-23  
**Status:** Approved

### Decision

Use the Repository pattern with one repository class per aggregate root. Repositories receive
a SQLAlchemy `session` argument injected by the calling service and never commit or roll back
the session themselves.

### Context

Without an explicit data access layer, business logic and database queries become entangled.
Model functions in the current application mix CSV reading, data transformation, and business
classification in the same function. The Repository pattern enforces a clean boundary: all
SQL is in the repository, no SQL is in the service.

### Alternatives Considered

- **Active Record pattern (SQLAlchemy models contain their own `save()`/`delete()` methods)**:
  Less boilerplate but mixes persistence concerns into domain objects. Makes it harder to test
  domain logic without a database, and harder to change the persistence mechanism.
- **Data Mapper without an explicit repository class (queries directly in service methods)**:
  Keeps less indirection but scatters SQL across the service layer. As the number of queries
  grows, the service files become hard to navigate.

### Chosen Solution

One repository class per aggregate root:

- `TechnicianRepository`
- `ProductRepository`
- `ProductionOrderRepository`
- `ScheduleRepository`
- `ShiftRepository`
- `UserRepository`
- `ScheduleLockRepository`

Each class exposes typed methods: `find_by_*`, `get_all`, `save`, `delete`, `bulk_insert`.
No business logic in repositories. The service opens a session, passes it to one or more
repositories, and commits or rolls back.

### Rationale

The Repository pattern separates the persistence concern from the business logic concern,
making both independently testable. Passing the session from the service ensures that a
service operation spanning multiple repositories participates in a single transaction.
If a repository committed its own session, a multi-table service operation could partially
commit on failure.

### Consequences

- Repositories are thin. They contain only ORM operations. Classification logic, scheduling
  decisions, and validation all live in services.
- The service layer manages all transactions. The pattern: open session → call repositories →
  commit (or rollback on exception).

### Future Considerations

- If a specific query becomes a performance bottleneck, the repository can use a SQLAlchemy
  Core expression for that query without affecting the service interface.

---

## ADR-007 — Phase 1 Authentication: bcrypt + DB Session; Defer JWT to Phase 2

**Date:** 2026-06-23  
**Status:** Approved

### Decision

In Phase 1, store passwords hashed with bcrypt (cost factor ≥ 12) in the `users` table.
Validate on login and write the authenticated user's identity to `st.session_state`. Do not
implement JWT in Phase 1.

### Context

The current application stores credentials as plaintext in `config.py` and commits them to
version control. Three roles exist (`admin`, `manager`, `user`) but no page enforces them —
all roles see all pages. V1 of the architecture proposed JWT in Phase 1.

### Alternatives Considered

- **JWT in Phase 1 (as V1 proposed)**: JWTs are stateless bearer tokens designed for HTTP
  request authentication, where every request must carry proof of identity because the server
  has no persistent connection. Streamlit maintains a persistent WebSocket connection and
  `st.session_state` is already server-side. A JWT stored in `st.session_state` adds token
  issuance, expiry, and refresh logic while gaining none of the statelessness benefit.
- **OAuth2 / external identity provider**: Delegates authentication to an external system.
  Appropriate for large organizations but adds external infrastructure dependency and
  complexity that is not warranted for an internal single-plant tool in its first stable
  iteration.
- **Continue with plaintext credentials**: Not viable. Plaintext passwords in version control
  is a critical security vulnerability.

### Chosen Solution

- Credentials stored in a `users` table. Passwords hashed with bcrypt, cost factor ≥ 12.
- On login, `AuthService` loads the user from the DB, runs `bcrypt.checkpw`, and on success
  writes `user_id`, `username`, `role` to `st.session_state`.
- Every page checks `st.session_state.logged_in` and `st.session_state.role` before rendering.
- No credentials in source code, `config.py`, or any tracked file.
- DB connection string in `DATABASE_URL` environment variable (or `secrets.toml`, not
  committed to version control).
- After 5 consecutive failed login attempts in a session, a 30-second delay is applied.

### Rationale

JWT becomes genuinely useful in Phase 2 when FastAPI exposes real HTTP endpoints requiring
stateless authentication for API clients. Implementing it in Streamlit prematurely creates
infrastructure complexity with no practical security gain. Bcrypt with a `users` table is
the correct, secure, minimal solution for a Streamlit application.

### Consequences

- All existing `Config.CREDENTIALS` plaintext entries must be deleted before Phase 1
  deployment. Migration script seeds bcrypt-hashed versions into the `users` table.
- Role enforcement is implemented per page, not via a decorator — Streamlit does not support
  decorators on page functions in a way that prevents rendering.

### Future Considerations

- In Phase 2, FastAPI issues a JWT on successful login. The `users` table and bcrypt
  validation are unchanged — only the token transport mechanism is added. The `AuthService`
  business logic does not need to change.

---

## ADR-008 — Separate Product (Catalogue) from ProductionOrder (Work Instruction)

**Date:** 2026-06-23  
**Status:** Approved

### Decision

Model two separate entities: `products` (stable SAP catalogue) and `production_orders`
(dated ERP work instructions with quantity). Do not use a single "Order" entity for both.

### Context

The current system conflates two things with different lifecycles in a single concept called
"Order": the SAP product master data (routing time, material description) and the ERP work
instruction for a specific scheduling period (order ID, priority, date, quantity). Because of
this conflation, it is impossible to distinguish "we know this product exists" from "we have a
current work order for it," or to have two orders for the same SAP number on the same day with
different priorities and quantities — a valid real-world scenario.

### Alternatives Considered

- **Single Order entity with optional fields**: Keep one table, add columns for ERP-specific
  fields (order ID, priority, date). Simple to implement but semantically incorrect — it
  becomes impossible to query the product catalogue separately from the work order history.
- **Rename the current "Orders" table to "Products" and add a separate WorkOrder table**:
  Equivalent to the chosen solution. This is what V2 implements, just with clearer naming.

### Chosen Solution

Two tables:

- `products`: SAP number, material description, routing time per unit. Permanent catalogue
  entries. Routing time per unit is stable master data.
- `production_orders`: ERP order ID, reference to a product, priority, order date, quantity.
  Work instructions consumed in scheduling runs. The same product can appear in multiple
  production orders on the same day.

### Rationale

The separation accurately reflects the business reality: products are permanent master data
managed by SAP; production orders are transient work instructions issued per scheduling cycle
by the ERP. Separating them enables historical queries (how many times was a given SAP number
scheduled this month?), prevents the conflation of product lifecycle with order lifecycle, and
is the prerequisite for the quantity-first-class-field decision (ADR-009).

### Consequences

- `OrderService` must handle both domains: product CRUD (add/modify/delete SAP entries) and
  production order management (upload, validate, persist per-day batches).
- The bulk upload process must validate that all SAP numbers in the uploaded orders file exist
  in `products` before inserting `production_orders` rows.

### Future Considerations

- When order splitting is introduced in Phase 3 (ADR-022), the `production_orders` table
  gains `parent_order_id` and `is_split_child` columns. The core product/order separation
  remains unchanged.

---

## ADR-009 — Quantity Is a First-Class Field; Effective Time Drives All Capacity Checks; Atomic Assignment

**Date:** 2026-06-23 (quantity); 2026-06-30 (atomic assignment confirmed)  
**Status:** Approved

### Decision

`quantity` is a non-optional column on `production_orders`. All scheduling algorithm capacity
checks, workload calculations, and display values use `effective_time_minutes = routing_time_minutes × quantity`.
A production order is assigned atomically — its full quantity to a single technician. Splitting
a quantity across technicians is deferred to Phase 3.

### Context

The current system treats routing time as the unit of work without accounting for how many
units of a product must be produced. A production order for 10 units of a 30-minute part
occupies 300 minutes of a technician's time, not 30. Without quantity as a first-class field,
the scheduling algorithm assigns orders based on incorrect capacity estimates, and the
resulting schedule is wrong.

### Alternatives Considered

- **Store routing time as total time (pre-multiplied by quantity at upload time)**: Simpler
  to work with in the algorithm, but loses the per-unit routing time which is needed for
  display, manager modification, and future splitting. The per-unit time is meaningful master
  data that should not be destroyed at upload.
- **Allow splitting immediately**: Permit partial quantity assignment to multiple technicians
  in Phase 1. Rejected — order splitting changes the fundamental algorithm, the assignment
  model, and the completion tracking in ways that have not been designed yet. Introducing it
  before the core is stable and tested would be premature.

### Chosen Solution

- `production_orders.quantity INTEGER NOT NULL DEFAULT 1`.
- `effective_time_minutes = routing_time_minutes × quantity` computed at the service layer
  before the algorithm runs.
- All three phases of the scheduling algorithm use `effective_time_minutes` for capacity
  checks, not the per-unit routing time.
- `routing_time_minutes` (per unit) is kept as a snapshot on `schedule_assignments` for
  display and manager modification — modifying routing time on a specific assignment does
  not alter the product catalogue.

### Rationale

Quantity is a real field present in the ERP work instruction. Treating it as incidental leads
to systematically incorrect scheduling. The per-unit routing time is stable master data;
the effective time is a derived scheduling input that depends on both the product and the
order. Keeping both values correctly separated makes the data model honest.

### Consequences

- Every place in the codebase that reads `routing_time` for scheduling purposes must be
  updated to use `effective_time_minutes`. This is a correctness fix, not an enhancement.
- The algorithm test fixture must use orders with `quantity > 1` to verify that the formula
  is applied correctly after refactoring.

### Future Considerations

- Phase 3: order splitting allows assigning partial quantities to multiple technicians.
  This requires `parent_order_id` and `is_split_child` columns on `production_orders`, a
  redesigned assignment model, and a new completion-tracking mechanism for the parent order.
  The current atomic model is a documented constraint, not a permanent one.

---

## ADR-010 — Computed Values Are Never Stored in the Database

**Date:** 2026-06-23  
**Status:** Approved

### Decision

Derived values (classification labels, expertise class numeric codes, class codes, working
time in minutes) are not stored as columns in the database. They are computed by the service
layer at read time.

### Context

V1 proposed storing `Classification` and `Expertise Class` on technicians, and `Class` and
`Class Code` on orders. If the classification thresholds change (e.g. the boundary between
Low and Medium routing time shifts from 160 to 180 minutes), every stored value becomes stale
and a data migration is required to correct it.

### Alternatives Considered

- **Store derived values, update them with triggers**: Keeps the data consistent but adds
  trigger complexity and still requires a backfill if thresholds change.
- **Store derived values, mark them as denormalized/cached**: Acceptable if clearly flagged
  but requires cache invalidation logic to stay correct.
- **Compute everything at query time using SQL expressions**: Possible but forces threshold
  logic into SQL, which is harder to test and further from the Python service layer where
  the rest of the business logic lives.

### Chosen Solution

All classification thresholds and skill-to-expertise mappings remain in `config.py`. Service
methods compute derived values on read:

| Derived Value | Source Data | Computed By |
|---|---|---|
| Classification (Basic / Above Average / Good / Advanced) | `technician_skills` max score | `TechnicianService.compute_expertise_class()` |
| Expertise Class (1–4) | Classification label | `TechnicianService.compute_expertise_class()` |
| Class (Low / Medium / High / Very High) | `routing_time_minutes` | `OrderService.classify_product()` |
| Class Code (1–4) | Class label | `OrderService.classify_product()` |
| working_time_minutes | `break_minutes`, `extra_time_minutes` | `ShiftService.compute_working_time()` |
| effective_time_minutes | `routing_time_minutes × quantity` | Algorithm pre-processing |

### Rationale

A threshold change requires updating one function and zero data migrations. Computed values
are always current because they are derived at read time. The service layer is the single
source of truth for business rules, not the database.

### Consequences

- DTOs returned from service methods include computed fields alongside raw DB fields.
- Performance: classification is computed per-technician per-read. For a team of ~15 technicians,
  this is negligible. If the team ever grows to hundreds, caching in `st.session_state` between
  page renders is sufficient mitigation before any DB-level change is considered.

### Future Considerations

- If classification rules ever change (new skill levels, new routing time thresholds), the
  change is a single function edit with no data migration required.

---

## ADR-011 — Surrogate Integer Primary Keys Over Natural Keys

**Date:** 2026-06-23  
**Status:** Approved

### Decision

All tables use surrogate serial integer primary keys. External identifiers (`matricule`,
`sap_number`, `erp_order_id`) are unique indexed columns but are not primary keys.

### Context

V1 proposed using `Matricule` as the string primary key for technicians and the SAP number
as the primary key for products. External identifiers are assigned by HR and ERP systems that
are outside the control of this application.

### Alternatives Considered

- **Natural primary keys (Matricule, SAP number)**: Simple — the identifier already exists,
  no surrogate needed. However, if an identifier is ever corrected, reassigned, or reformatted
  by the external system, the database must cascade the change through every foreign key in
  every related table (assignments, skills, shifts). This has happened in practice in other
  systems and is a well-known source of complex data corruption bugs.
- **UUID primary keys**: Globally unique, no collision risk. More appropriate for distributed
  systems where keys need to be assigned without a central coordinator. For a single-node
  internal application, the overhead of storing and indexing 16-byte UUIDs vs 4-byte integers
  has no benefit.

### Chosen Solution

Serial integer `id` primary key on every table. Natural keys are declared `UNIQUE NOT NULL`
and indexed for efficient lookup queries. Foreign keys always reference the integer `id`.

Note: `schedule_assignments` retains a `schedule_row_id UUID` column for backward compatibility
with existing saved schedules during the Phase 1 migration. This UUID is not a primary key.

### Rationale

The database has its own identity independent of external systems. Natural keys are preserved
as unique indexed columns for lookup — the application still finds a technician by matricule —
but the relational graph is built on stable integer identifiers. A matricule correction in HR
requires updating one column in one row, with no cascading effects.

### Consequences

- Application code must use integer IDs in foreign key relationships, not natural keys.
- The Phase 1 migration scripts map CSV natural keys to integer IDs when constructing related
  rows (e.g. mapping `Matricule` to `technicians.id` when inserting `shifts`).

### Future Considerations

- No changes anticipated. Surrogate keys are a safe, stable foundation for the data model.

---

## ADR-012 — Technician Skill Levels Normalized Into a Junction Table

**Date:** 2026-06-23  
**Status:** Approved

### Decision

Replace the four horizontal columns `Niveau 1`, `Niveau 2`, `Niveau 3`, `Niveau 4` on the
technician entity with a `technician_skills` junction table containing one row per
`(technician_id, skill_level, score)`.

### Context

The current CSV stores four numeric score columns per technician. Adding a fifth level would
require a schema change. Querying all technicians with a Level 3 score above a threshold
requires a `CASE` expression across four columns.

### Alternatives Considered

- **Keep four columns as DB columns**: Simple to implement, matches the current data. Cannot
  be queried uniformly without column-specific logic, and adding a new level requires a schema
  migration.
- **Store as JSON in a single column**: No schema change when levels are added, but loses SQL
  indexing, integrity enforcement, and aggregation capability.

### Chosen Solution

`technician_skills` table with `UNIQUE(technician_id, skill_level)`. Four rows per technician
(one per level, 1–4). The classification algorithm reads all four rows, finds the maximum
scored level, and maps it to the expertise classification. This logic lives in
`TechnicianService.compute_expertise_class()`.

### Rationale

The four-column layout is a horizontal encoding of a one-to-many relationship, which is the
canonical anti-pattern that normalization addresses. A junction table makes the relationship
extensible, uniformly queryable, and correctly relational.

### Consequences

- Inserting or updating a technician requires writing four `technician_skills` rows. This is
  handled by `TechnicianRepository.save()`.
- `ON DELETE CASCADE` on the foreign key means deleting a technician removes their skill rows
  automatically.

### Future Considerations

- If a fifth skill level is introduced, a new row is inserted for each technician. No schema
  change required.

---

## ADR-013 — Replace WorkSessions JSON Column with a Normalized work_sessions Table

**Date:** 2026-06-23  
**Status:** Approved

### Decision

Replace the `WorkSessions` JSON array column on the schedule row with a `work_sessions`
relational table, where each row represents one contiguous start/stop interval for an
assignment.

### Context

The current system stores work session history as a JSON array in a `WorkSessions` column:
`[{"start": "ISO", "stop": "ISO"}, ...]`. This is written and read as a string, requires
application-side parsing, cannot be indexed, and cannot have integrity constraints applied
to it by the database.

### Alternatives Considered

- **Keep the JSON column**: No schema change needed, quick to implement. Cannot query
  time-range data, cannot enforce temporal ordering, cannot aggregate across sessions with SQL,
  cannot detect overlapping sessions.
- **Store as a PostgreSQL JSONB column**: Supports indexing on JSON fields. Slightly better
  than text JSON but still does not support row-level integrity constraints (e.g. `stopped_at
  > started_at`) or standard aggregate functions.

### Chosen Solution

A `work_sessions` table with a foreign key to `schedule_assignments`. Each row: `assignment_id`,
`started_at TIMESTAMPTZ NOT NULL`, `stopped_at TIMESTAMPTZ NULL` (NULL = currently in progress),
with a `CHECK (stopped_at IS NULL OR stopped_at > started_at)` constraint enforced by the
database.

### Rationale

A relational table makes all time-based queries straightforward SQL: total time spent on an
assignment is a `SUM()` aggregate; the first start time is `MIN(started_at)`; overlapping
sessions are detectable with a self-join. The `CHECK` constraint prevents the database from
storing a session that ended before it started — impossible to enforce with application code
alone if concurrent writes occur.

### Consequences

- The Phase 1 migration script must parse the `WorkSessions` JSON column from
  `current_schedule.csv` and reconstruct `work_sessions` rows from it.
- `TotalTimeSpent` on the old schedule row becomes a derivable aggregate. It can be cached as
  `remaining_time_minutes` on `schedule_assignments` for UI performance, but `work_sessions`
  is the source of truth.

### Future Considerations

- Reporting queries (total technician work time per day, average time per order type, etc.)
  are straightforward SQL aggregates on this table. No application-layer transformation needed.

---

## ADR-014 — Split the 22-Column ScheduleRow Into schedule_assignments and work_sessions

**Date:** 2026-06-23  
**Status:** Approved

### Decision

The existing 22-column `current_schedule.csv` `ScheduleRow` is replaced by two normalized
tables: `schedule_assignments` (static assignment data) and `work_sessions` (dynamic execution
tracking). Denormalized copies of technician names and product descriptions are removed.

### Context

The current flat schedule row carries both assignment data (who does what, in what order,
with what status) and execution data (when they started, how long it took, session history).
These have different change frequencies: assignment data is set at generation time and changes
only on reassignment; execution data changes constantly throughout the workday. Mixing them
in a single 22-column row creates lock contention and makes the two concerns harder to reason
about.

### Alternatives Considered

- **Keep all 22 columns in a single table**: Preserves the existing structure. As the system
  grows, the table accumulates more columns, session management becomes harder, and reporting
  requires parsing JSON from within a CSV column.
- **Split into three tables (assignments, sessions, metadata)**: Potentially cleaner but adds
  another join for every read and no additional benefit at the current scale.

### Chosen Solution

`schedule_assignments` holds: identity, foreign keys to the technician and order, date,
sequence, status, routing time snapshot, remaining time, remark, and the two override flags
(`is_expertise_override`, `was_unblocked_by_manager`). `work_sessions` holds the start/stop
intervals. Names and descriptions are read via joins, not stored as copies.

### Rationale

The split follows the single-responsibility principle at the data model level. Assignment data
and execution data have different consumers (the scheduling algorithm reads assignments; the
time-tracking UI reads sessions) and different update patterns. Separating them also eliminates
the denormalized name copies, which were a data quality risk — a corrected technician name
would not update the old schedule rows.

### Consequences

- Every schedule query that needs technician name or product description must join to
  `technicians` and `products` respectively. This is a correct relational design and not a
  performance concern at the current scale.
- The status state machine (`Planned → In Progress → Partially Completed → Completed / Blocked`)
  is enforced via a PostgreSQL `CHECK` constraint on `schedule_assignments.status`.

### Future Considerations

- The `schedule_row_id UUID` column on `schedule_assignments` is kept during Phase 1 for
  backward compatibility with existing saved schedules. It can be removed in Phase 2 once
  all clients are off the CSV-based schedule IDs.

---

## ADR-015 — Phase 3 Scheduling: Ignore Expertise as Automatic Last-Resort Fallback

**Date:** 2026-06-23 (original V2 design); 2026-06-30 (confirmed against flowchart conflict)  
**Status:** Approved

### Decision

Phase 3 of the scheduling algorithm (capacity fill) assigns unscheduled orders to any
technician with sufficient remaining time, regardless of expertise class. This assignment
is automatic. There is no confirmation gate that delays or withholds it.

### Context

The system's scheduling algorithm has three phases. Phase 1 (round-robin) and Phase 2
(balanced priority assignment) both enforce the expertise constraint
(`technician.expertise_class >= order.class_code`). After Phase 2, some orders may remain
unscheduled because no technician with a matching expertise level has remaining capacity.

`docs/FLOWCHART.md` labels both capacity-fill rounds "Expertise adequate," which read literally
would require Phase 3 to also enforce expertise — leaving orders unscheduled when no
matching technician has capacity. This interpretation was flagged as a conflict with V2's
original design and put to the product owner for resolution.

### Alternatives Considered

- **Enforce expertise in Phase 3 (flowchart's literal reading)**: Orders without a qualified
  technician remain in the unscheduled list. Expertise correctness is always maintained. This
  creates the production-blocking scenario where an order sits unscheduled while a technician
  sits idle — the idle technician could do the work, but the system refuses to assign it.
- **Hard-block Phase 3 assignments entirely**: No expertise-override assignments are ever made.
  Equivalent to the above; same production-blocking outcome.
- **Require manager confirmation before any Phase 3 assignment is finalized**: A confirmation
  step gating finalization means the assignment exists only after manager action. If the manager
  is unavailable, the order remains unscheduled — the same production-blocking outcome.

### Chosen Solution

Phase 3 ignores expertise and assigns automatically to the technician with the most remaining
time, regardless of expertise class. The assignment is made during `generate_schedule()` as
part of the normal generation run. No gate delays it. The `is_expertise_override` flag on
the resulting `schedule_assignments` row surfaces the mismatch for manager visibility (see
ADR-016). The manager sees a summary count of override assignments immediately after generation
as an informational notice.

The flowchart's "Expertise adequate" label is interpreted as describing Phase 2 (the preferred,
expertise-matched capacity-fill path), not Phase 3.

### Rationale

The product owner's reasoning: "if it remains unscheduled orders but we don't have technicians
with the same expertise for it, then we match the order with any available technician, so we
don't have unscheduled orders and free technicians — this will block the production." An
expertise mismatch is a manageable quality risk. An order unscheduled while a qualified-enough
technician is idle is a production stoppage. The lesser harm is the expertise mismatch.

### Consequences

- The existing Phase 3 code in `models/initial_scheduling.py` (which already ignores expertise)
  is the correct behavior. It is preserved when the algorithm is refactored to `SchedulingService`.
- The dead commented-out algorithm code (lines 345–525 of `initial_scheduling.py`) that
  included a stricter expertise-always-enforced pass 3 must be deleted, not activated.

### Future Considerations

- The `is_expertise_override` flag enables reporting: how many assignments per day required
  an expertise bypass? This can inform decisions about technician cross-training.
- If a technician receives a Phase 3 assignment for a class above their expertise, the
  manager may choose to manually reassign before work begins. The UI must surface
  override assignments prominently to facilitate this.

---

## ADR-016 — is_expertise_override Flag Replaces Freetext Remark String

**Date:** 2026-06-23  
**Status:** Approved

### Decision

Phase 3 assignments are marked with a boolean `is_expertise_override = true` column on
`schedule_assignments`. The free-text string `"Capacity fill - may not match expertise"`
that the current code writes to the `Remark` column is not sufficient.

### Context

The current algorithm marks Phase 3 assignments by setting `Remark = 'Capacity fill - may not
match expertise'` as a free-text string. This remark is buried in a column that also holds
other free-text remarks, is not indexed, cannot be filtered efficiently, and is invisible
unless a manager specifically reads that row.

### Alternatives Considered

- **Keep the freetext remark, add a UI filter for it**: Fragile — the filter depends on an
  exact string match that could silently break if the remark wording changes.
- **Separate status value for override assignments**: Would change the status state machine
  and require all status-related code to handle a new state.

### Chosen Solution

A dedicated boolean column `is_expertise_override BOOLEAN NOT NULL DEFAULT false` on
`schedule_assignments`. The `Remark` column is retained for free-text notes (manager
observations, block reasons) but is no longer the mechanism for communicating expertise
overrides. The UI renders assignments with `is_expertise_override = true` with a visible
warning indicator. The post-generation summary reports the count of override assignments
separately.

### Rationale

An expertise mismatch in a factory context is a real quality and safety risk. It must be
surfaced as a distinct, filterable, queryable property — not hidden in freetext. A boolean
column can be indexed, filtered in SQL, counted in aggregates, and displayed as a UI badge
without string parsing.

### Consequences

- `SchedulingService` must set `is_expertise_override = true` on every Phase 3
  `ScheduleAssignment`. The algorithm refactoring must not silently drop this behavior.
- The Schedule Management page must display a visible warning indicator on override assignments.
- Reporting in Phase 2 can include "assignments requiring expertise override per day."

### Future Considerations

- If the system is extended with a formal quality management module, `is_expertise_override`
  becomes a filter criterion for quality audit queries.

---

## ADR-017 — Working-Time Formula: 480 − break_minutes + extra_time_minutes

**Date:** 2026-06-30  
**Status:** Approved

### Decision

A technician's available working time in minutes is computed as:
`working_time_minutes = 480 − break_minutes + extra_time_minutes`.

The previous implementation used `480 + 30 − break_minutes + extra_time_minutes`, which
produces a 510-minute base. This formula is incorrect and is replaced.

### Context

The scheduling algorithm computes each working technician's available capacity from the shift
data. The existing code in `models/initial_scheduling.py` (line 58) uses the formula
`480 + 30 − Break + Extra Time`. This gives technicians a 510-minute base capacity when their
break is 30 minutes, meaning the algorithm systematically overestimates how much work each
technician can accept.

The correct interpretation: the workday is 8 hours (480 minutes). The 30-minute lunch break
is within those 480 minutes. `break_minutes` represents the break taken; subtracting it
reflects that break time is not work time. `extra_time_minutes` is overtime added on top.
The `+30` constant in the old formula is a bug — it adds an extra 30 minutes of capacity
that does not exist.

### Alternatives Considered

- **510-minute base (existing formula)**: Would mean the standard shift provides 510 minutes
  of working time. This contradicts the product owner's statement that the workday is 8 hours
  (480 minutes). The +30 would only be correct if the break is entirely outside the 8-hour
  window, which is not the case.
- **480 minutes flat (ignore break and extra entirely)**: Simpler but ignores the real
  variation between technicians who work different break durations or overtime.

### Chosen Solution

`working_time_minutes = 480 − break_minutes + extra_time_minutes`, implemented in
`ShiftService.compute_working_time()`. This formula is applied to every working technician
before the scheduling algorithm runs. `break_minutes` defaults to 30 in the `shifts` table.
`extra_time_minutes` defaults to 0.

### Rationale

The product owner confirmed this formula on 2026-06-30: "we work 8 hours a day + 30 min break
so the formula can be: 480 + extra time − break." The 30-minute break is included within the
480 minutes, not added on top.

### Consequences

- The scheduling algorithm will produce different capacity calculations than the current code.
  The golden-output regression test (Phase 1 test strategy) must account for this intentional
  difference: assignments that change due to the formula correction are expected and should be
  documented, not treated as bugs.
- Technicians with `break_minutes = 30` and `extra_time_minutes = 0` have exactly 450 minutes
  of working capacity under the correct formula (not 510 as the current code calculates).

### Future Considerations

- If shift patterns change (e.g. split shifts, different standard hours), the formula is
  updated in `ShiftService.compute_working_time()` in one place with no data migration.

---

## ADR-018 — DailyOrderPoolService Resolves Carryover Before Each Scheduling Run

**Date:** 2026-06-30  
**Status:** Approved

### Decision

Introduce `DailyOrderPoolService` as a service layer component that runs before the scheduling
algorithm each day. It resolves in-progress order carryover, blocked order carryover, and
late (unstarted prior-day) order collection. Its output, `DailyPoolResult`, is the input to
`SchedulingService.generate_schedule()`.

### Context

The current system has no formal mechanism for handling orders that carry over between days:
in-progress orders (technician continues or needs replacement), blocked orders (manager must
decide to unblock), and late unstarted orders (missed in a prior day's scheduling run). The
flowchart defines these pre-algorithm steps explicitly. Without formalizing this service, the
logic would be scattered across the page and algorithm code.

### Alternatives Considered

- **Handle carryover inside SchedulingService**: Keeps the pre-processing and the algorithm
  in one service. However, the carryover logic has different concerns (checking technician
  availability, re-querying prior assignments) from the scheduling algorithm (optimizing
  assignment of a given order pool). Mixing them makes both harder to test and reason about.
- **Handle carryover in the page**: The page would query prior-day assignments and resolve
  carryover before calling the scheduling service. Violates the rule that pages contain no
  business logic.

### Chosen Solution

`services/daily_pool_service.py` — `DailyOrderPoolService` with one public method:
`resolve_pool(date) → DailyPoolResult`.

Steps performed:
1. In-progress carryover: for each in-progress assignment from the prior shift date, check if
   the assigned technician is working today. If yes, the assignment continues unchanged. If no,
   find a replacement technician (same or higher expertise, no prior in-progress assignment of
   their own). If no replacement exists, mark the assignment Blocked with reason
   "No qualified tech available today."
2. Blocked order carryover: for each Blocked assignment from any prior date, check
   `was_unblocked_by_manager`. If false, keep Blocked. If true, treat as a new assignment
   for today using the same replacement logic.
3. Late order collection: retrieve all `not_started` production orders from prior dates that
   were never scheduled, and include them in today's assignable pool.

### Rationale

Separating carryover resolution from the scheduling algorithm follows single-responsibility.
The algorithm operates on a clean, resolved order pool; it does not need to know whether an
order is "carried over from yesterday" or "new today." The service produces a `DailyPoolResult`
that contains this context for the manager summary, while the algorithm receives only the
assignable pool.

### Consequences

- `DailyOrderPoolService` is called before `SchedulingService` on every schedule generation
  run, including the first day (when it returns an empty carryover and passes the full
  uploaded order pool as `assignable_pool`).
- The `was_unblocked_by_manager` column on `schedule_assignments` (ADR-019) is the flag this
  service reads to decide whether blocked orders re-enter the pool.

### Future Considerations

- If multi-day scheduling is introduced in Phase 2, `DailyOrderPoolService` may be extended
  to handle a range of dates rather than a single day.

---

## ADR-019 — was_unblocked_by_manager Column Tracks Manager-Initiated Unblocking

**Date:** 2026-06-30  
**Status:** Approved

### Decision

Add a `was_unblocked_by_manager BOOLEAN NOT NULL DEFAULT FALSE` column to
`schedule_assignments`. This flag is set by `ScheduleService.unblock_assignment()` when
a manager explicitly unblocks a Blocked order.

### Context

The `DailyOrderPoolService` (ADR-018) must distinguish between two types of Blocked
assignments when running carryover the next day: those that remain blocked (manager has not
acted) and those the manager has explicitly unblocked (and which should re-enter the
assignable pool). Without this flag, there is no way to tell them apart without out-of-band
state.

### Alternatives Considered

- **Use a dedicated Unblocked status value**: Add `Unblocked` to the status state machine as
  a distinct state after `Blocked`. The carryover service then looks for `status = 'Unblocked'`
  orders. This adds a status that has no meaning during the workday (an assignment cannot be
  simultaneously "done for today" and "ready for tomorrow") and complicates the state machine.
- **Store the unblock event as a work_sessions row with a special marker**: Overloads the
  session table with a concern it was not designed for and makes the carryover query complex.

### Chosen Solution

A simple boolean flag `was_unblocked_by_manager` alongside `is_expertise_override` on
`schedule_assignments`. The Alembic migration for this column is introduced in Task 1.5.4
(DailyOrderPoolService). The UI that allows a manager to unblock an assignment sets this flag
via `ScheduleService.unblock_assignment()`.

### Rationale

The flag is minimal, queryable, indexed (via the existing status index), and directly answers
the question `DailyOrderPoolService` needs to ask. It does not complicate the status state
machine or require a new status value.

### Consequences

- `ScheduleService.unblock_assignment()` must set `was_unblocked_by_manager = True` as part
  of the unblock operation. The implementation of this action is in Milestone 1.6.

### Future Considerations

- The flag enables reporting: how many blocked orders per day were manager-unblocked vs.
  left blocked? This is useful for identifying recurring blockage patterns.

---

## ADR-020 — schedule_locks Table Guards Concurrent Schedule Generation

**Date:** 2026-06-23  
**Status:** Approved

### Decision

Use a `schedule_locks` table as a lightweight advisory lock to prevent two users from
generating a schedule for the same date simultaneously.

### Context

The scheduling algorithm is a long-running computation that produces many rows in
`schedule_assignments`. Without a concurrency guard, two managers clicking "Generate Schedule"
simultaneously produce interleaved writes for the same date, resulting in a corrupted or
duplicated schedule.

### Alternatives Considered

- **PostgreSQL advisory locks (`pg_try_advisory_lock`)**: Database-level locking without a
  dedicated table. Effective but requires the application to know the PostgreSQL advisory lock
  API, and lock state is not visible or queryable.
- **Application-level mutex in session state**: Works only if both users share the same
  process, which is not guaranteed in a multi-worker Streamlit deployment.
- **Unique constraint on `schedule_assignments(schedule_date)` only**: Prevents duplicate rows
  but does not prevent two concurrent runs from generating conflicting data before either
  commits.

### Chosen Solution

`schedule_locks` table: `schedule_date DATE UNIQUE`, `locked_by INT FK users`, `locked_at`,
`released_at`. Before generating, `SchedulingService` attempts to insert a lock row. If a lock
already exists for that date, the generation is rejected with an informative error message.
The lock is released when generation completes or fails. Stale locks (unreleased and old) are
cleaned up on application startup by `ScheduleLockRepository.cleanup_stale()`.

### Rationale

A database-backed lock is visible, queryable, and persistent across application restarts.
If the generating process crashes mid-run, the stale lock is detectable and can be cleaned up
automatically. The table approach is simple to implement and debug.

### Consequences

- Schedule generation is serialized per date. Two concurrent users cannot generate the same
  date's schedule simultaneously.
- The lock must be released in a `finally` block to prevent stale locks when exceptions occur
  during generation.

### Future Considerations

- If the scheduling algorithm is eventually made idempotent (re-running for the same date
  produces the same result), the lock could be replaced with a simpler "does a schedule for
  this date already exist?" check. This is not planned for Phase 1.

---

## ADR-021 — Defer Reclamations to Advanced Level; Remove from Navigation Immediately

**Date:** 2026-06-23  
**Status:** Approved

### Decision

The Reclamations module is fully deferred to an advanced level (beyond Phase 2). The
Reclamations page is removed from the sidebar navigation in Phase 0. Its internal code is
not fixed.

### Context

The Reclamations page has three unfixable-in-place bugs: `generate_recommendations()` is
called but never defined (causes a `NameError` crash on every visit), the CRUD functions in
`models/reclamations.py` use hardcoded relative paths and mismatched signatures, and the page
was never connected to real data. Fixing all of this would constitute building the module from
scratch, which is out of scope for Phase 0 and Phase 1.

### Alternatives Considered

- **Fix the Reclamations page in Phase 0**: Would require implementing `generate_recommendations()`,
  correcting all CRUD paths and signatures, and potentially redesigning the storage. This is a
  significant feature build, not a bug fix, and contradicts the product vision's priority of
  making what exists work correctly before adding features.
- **Show the page but disable all functionality**: Still crashes when visited because the
  `NameError` is at import time in the render function, not inside a guarded block.
- **Silence the crash with a try/except**: Hides the error but delivers a broken, misleading
  page to the user.

### Chosen Solution

Remove the Reclamations option from the sidebar navigation in Phase 0 (Task P0.1). Do not
touch its internal code. The page file remains in the codebase but is unreachable from the UI.
The `data/reclamations_file.xlsx` file is not migrated to PostgreSQL in Phase 1 or Phase 2.
Full implementation is planned for the advanced level.

### Rationale

The product owner's decision: "I don't need it right now for the functionality of the app, we
will need it in an advanced level." Removing it from navigation is the minimal change that
makes the application safe to use (no more crash risk) without touching a module that needs
to be fully rebuilt anyway.

### Consequences

- No regression risk from Reclamations code changes during Phase 0–2.
- Users cannot access Reclamations until the advanced level implementation is complete.
- `data/reclamations_file.xlsx` is not included in the Phase 1 data migration.

### Future Considerations

- At advanced level, the Reclamations module will need a full architecture and implementation
  pass: correcting all function signatures, implementing `generate_recommendations()`,
  designing a proper `reclamations` DB table, and migrating the XLSX data.

---

## ADR-022 — Defer Order Splitting to Phase 3

**Date:** 2026-06-23 (deferred); 2026-06-30 (atomic default confirmed)  
**Status:** Approved

### Decision

Production orders with `quantity > 1` are assigned atomically in Phase 1 and Phase 2: one
technician completes all units. Splitting a quantity across multiple technicians is deferred
to Phase 3.

### Context

In a real manufacturing environment, a large order might be split so that two technicians
produce part of the quantity in parallel, reducing total lead time. The current scheduling
algorithm has no concept of order splitting. Introducing it would require redesigning the
three-phase assignment algorithm, changing the completion-tracking model (partial completion
of a parent order), and adding `parent_order_id` / `is_split_child` columns to the schema.

### Alternatives Considered

- **Implement order splitting in Phase 1**: Makes the scheduling algorithm significantly more
  complex before the core is stable and tested. The product vision says "correctness first" —
  introducing a redesigned algorithm before the current one is validated against a database
  is premature.
- **Manual splitting by the manager (splitting in the UI before uploading)**: Managers can
  manually create two smaller orders in the ERP if splitting is needed urgently. This is a
  workaround, not a design decision, but it means the system is not broken in the interim.

### Chosen Solution

Atomic assignment for Phase 1 and Phase 2. `quantity` is stored and used to compute
`effective_time_minutes`, but the order is always assigned as a unit. The `production_orders`
table schema includes no splitting columns in Phase 1 (they will be added via Alembic in
Phase 3). The constraint is documented in `TARGET_ARCHITECTURE_V2.md` Section 14 and in the
Known Constraint section of the scheduling algorithm description.

### Rationale

Order splitting is a redesign-level change to the algorithm, not an incremental refactoring.
The product vision prioritizes making what exists work correctly. Adding splitting before the
core is stable and production-tested would introduce complexity that could mask correctness
issues in the base algorithm.

### Consequences

- An order that exceeds any single technician's remaining capacity is placed in the unscheduled
  list. Managers must handle this manually (e.g. by breaking the order into two smaller orders
  in the ERP before uploading).
- The unscheduled order count may be nonzero even when technicians have collective capacity
  for a large order. This is a documented, expected behavior.

### Future Considerations

- Phase 3 implementation: `production_orders` gains `parent_order_id INT NULL REFERENCES
  production_orders(id)` and `is_split_child BOOLEAN NOT NULL DEFAULT FALSE`. The assignment
  model, completion tracking (when is the parent considered complete?), and algorithm
  pre-processing all require redesign. This is a substantial Phase 3 feature.

---

## ADR-023 — Department as a String Field in Phase 1; Defer Full Entity to Phase 2

**Date:** 2026-06-23  
**Status:** Approved

### Decision

Add a `department VARCHAR(100) NULL` field to `technicians` and `production_orders` in Phase 1.
Do not create a `departments` table or foreign key in Phase 1.

### Context

The architectural review recommended a full `Department` entity to allow department-level
schedule isolation. The factory currently operates as a single scheduling unit with no evidence
from the codebase, data files, or product vision that multi-department isolation is needed in
Phase 1.

### Alternatives Considered

- **Full Department entity in Phase 1**: Adds a `departments` table, foreign keys on
  `technicians` and `production_orders`, and scheduling algorithm changes to respect department
  boundaries. This is overengineering before the need is proven.
- **No department field at all**: Simpler, but if the need arises in Phase 2, adding the field
  to the schema is trivial. The concern is that if organizational data (which department a
  technician belongs to) is not captured now, it may need to be backfilled from external
  systems later.

### Chosen Solution

A `department VARCHAR(100) NULL` column on both `technicians` and `production_orders`. The
application does not use it for scheduling decisions in Phase 1. It is available for future
promotion to a proper `departments` table and foreign key in Phase 2, at which point a single
Alembic migration creates the table, populates it from the distinct string values, and replaces
the string column with an integer foreign key.

### Rationale

The string field costs almost nothing to add and avoids a potentially complex backfill if
departments become operationally important in Phase 2. It is not overengineering — it is
capturing real organizational data that exists in the source system.

### Consequences

- The field is nullable and unused by the scheduling algorithm in Phase 1. It is populated
  during data migration if department information is available in the CSV source files.

### Future Considerations

- Phase 2: if departments become a scheduling constraint (e.g. technicians from Department A
  cannot be assigned to orders from Department B), the field is promoted to a full entity.

---

## ADR-024 — Three-Environment Infrastructure: Local → Streamlit Cloud Demo → AWS RDS Production

**Date:** 2026-06-30  
**Status:** Approved

### Decision

The application uses three environments across its lifecycle: local PostgreSQL for development,
Streamlit Community Cloud for demonstrations and limited live use, and AWS RDS for PostgreSQL
in production. All three use the same application code — only `DATABASE_URL` changes.

### Context

No PostgreSQL instance existed before Phase 1 began. The product owner defined the hosting
plan on 2026-06-30. The application needs a database immediately for Phase 1 development
(local), periodic demonstrations (cloud), and eventual full production use (AWS).

### Alternatives Considered

- **Single cloud environment from day one**: Avoids local setup but adds external dependency
  and cost before the application is in any state to demonstrate. Also requires internet access
  for every development iteration.
- **Docker-based PostgreSQL for all environments**: Consistent across environments, avoids
  cloud costs. However, the product owner confirmed preference for local native installation
  for development and AWS RDS for production — Docker is an option for local but not the
  decided approach.
- **SQLite for development, PostgreSQL for production**: Would require testing against a
  different database engine locally than what runs in production, which is a source of
  subtle incompatibilities.

### Chosen Solution

Three environments:
1. **Local development**: PostgreSQL 15 installed on the developer's machine. Database
   `dass_dev`. Two roles: application role (DML only) and migration role (DDL). `DATABASE_URL`
   set as a local environment variable. Connection details documented (not the passwords)
   in `docs/DEV_SETUP.md` so a second developer can reproduce the environment.
2. **Demo/Streamlit Community Cloud**: The Streamlit app is deployed to Streamlit Community
   Cloud for demonstrations and limited live use. `DATABASE_URL` is set as a Streamlit secret
   pointing at a reachable PostgreSQL instance (decided when the first demo deployment is needed).
3. **Production/AWS**: The full application migrates to AWS. PostgreSQL runs on AWS RDS for
   PostgreSQL. The application code is unchanged; `DATABASE_URL` points at the RDS endpoint.

### Rationale

Using the same database engine in all three environments eliminates engine-specific
incompatibilities. The `DATABASE_URL` pattern means the application has no environment-specific
branching in code. The three-environment plan mirrors a standard development → demo → production
lifecycle and is proportional to the project's current maturity.

### Consequences

- Task 1.1.0 (provisioning local PostgreSQL) is a prerequisite for all other Phase 1 tasks.
  It has no dependency and can run in parallel with Phase 0.
- The Alembic migration command is the same in all three environments, run by an operator
  before deployment, never automatically on startup.

### Future Considerations

- If the team grows, a shared development database (rather than local per developer) may be
  introduced. The connection module supports this without code changes.
- AWS infrastructure setup (VPC, security groups, RDS parameter group) is out of scope for
  Phase 1 documentation and will be planned when Phase 2 begins.

---

## ADR-025 — Credential and Database Privilege Security Constraints

**Date:** 2026-06-23  
**Status:** Approved

### Decision

Enforce the following non-negotiable security constraints throughout all phases:

1. No credentials, passwords, or connection strings in source code or version control.
2. `DATABASE_URL` (application role) in an environment variable or `secrets.toml` (not committed).
3. The application database role has only `SELECT, INSERT, UPDATE, DELETE` — no DDL, no
   `TRUNCATE`.
4. A separate migration role (DDL privileges) is used exclusively by Alembic. The running
   application never authenticates as the migration role.
5. Passwords are hashed with bcrypt, cost factor ≥ 12. No plaintext storage, ever.
6. Technician full names are not written to application logs (PII constraint).
7. `role` and `user_id` are not exposed in URL parameters.
8. On logout, all session state keys are cleared, not just `logged_in`.

### Context

The current application commits plaintext credentials to version control (`config.py`).
The login help expander displays a password that differs from the actual configured password —
a copy-paste inconsistency revealing that credentials have already drifted. The role system
exists but is not enforced. These are critical vulnerabilities for an internal factory
management system that handles production scheduling data and technician PII.

### Alternatives Considered

- **Environment-specific config files (not committed)**: `.env` files per environment. Viable
  but relies on developers remembering not to commit them. `secrets.toml` for Streamlit and
  environment variables for production are the standard patterns for each context.
- **Secrets management service (AWS Secrets Manager, Vault)**: Appropriate for mature
  production environments. Adds infrastructure complexity that is not warranted until the
  application is running in production (Phase 2+). The pattern chosen (environment variables
  in production, `secrets.toml` locally) is directly compatible with later migration to a
  secrets service.

### Chosen Solution

All eight constraints listed above are implemented as absolute rules, not guidelines. The
first task of Phase 0 (after disconnecting Reclamations) is removing credentials from
`config.py` and moving them to environment variables. The two separate DB roles are
established in Task 1.1.0.

### Rationale

The factory scheduling system handles production orders, technician personal data, and
work session timing. A compromised application that can alter its own schema (because the
app user has DDL privileges) could silently destroy schedule history. Keeping the application
role minimal enforces a clear boundary between the running application and its schema.

### Consequences

- `Config.CREDENTIALS` must be deleted from `config.py` during Phase 0. Phase 0 completion
  is gated on this.
- Any developer setting up the application locally must create their own environment variables
  or `secrets.toml`. Setup instructions go in `docs/DEV_SETUP.md`.
- Brute-force mitigation (5 failed attempts → 30-second delay) is a session-level guard,
  not IP-level. IP-level rate limiting is delegated to the reverse proxy or hosting platform.

### Future Considerations

- Phase 2: when FastAPI is introduced, JWT signing keys are also managed through environment
  variables, consistent with this pattern. They are never committed to version control.

---

## ADR-026 — Incremental Refactoring Over Rewrite

**Date:** 2026-06-23  
**Status:** Approved

### Decision

The application is refactored incrementally — one file, one layer, one milestone at a time —
not rewritten. At every point, the application must be in a fully working state.

### Context

The existing codebase has technical debt but also working business logic — particularly the
three-phase scheduling algorithm, which is the core of the system. A rewrite risks discarding
working behavior along with the debt, and produces a long period during which the application
does not run at all. The product vision explicitly states "I prefer incremental refactoring
instead of rewriting."

### Alternatives Considered

- **Big-bang rewrite**: Start fresh with the target architecture and migrate data and logic
  in one pass. Faster to reach a clean state but requires a long period of broken or parallel
  systems. If the rewrite takes longer than expected, the business has no working tool.
- **Strangle Fig pattern (new architecture grows around old code)**:  Gradually replace
  components from the outside in, keeping the old and new running in parallel at each step.
  This is effectively what the phased roadmap implements, but made explicit.

### Chosen Solution

The roadmap is structured in phases (0, 1, 2, 3) and within each phase in milestones. Each
milestone ends with the application in a fully working state. New code is written alongside
old code, verified to produce identical results (especially for the scheduling algorithm),
and the old code is removed only after verification. This is the Strangle Fig pattern applied
at the milestone level.

The golden-output regression test for the scheduling algorithm (Phase 1 test strategy) is the
formal mechanism for verifying that refactoring has not changed the algorithm's behavior.

### Rationale

Incremental refactoring eliminates the window during which the application is not runnable.
It reduces risk by making each step small and verifiable. It also gives the product owner
visibility into progress — each completed milestone is a working application with one more
piece in the right place.

### Consequences

- No milestone can leave the application in a broken state. "New code written, old code not
  yet removed" is an acceptable intermediate state within a milestone. "Application crashes"
  is not.
- The algorithm's behavior is the hardest thing to preserve. The golden-output regression
  test (capture the current algorithm's output on real data, compare against the refactored
  output) is mandatory before Milestone 1.5 begins.

### Future Considerations

- The development rules established at the start of the implementation phase formalize this
  principle: explain before changing, verify after changing, one phase at a time.

---

## ADR-027 — Tests Run Against Real PostgreSQL; No Mocking the Database

**Date:** 2026-06-30  
**Status:** Approved

### Decision

All Phase 1 tests that involve database access run against a real PostgreSQL instance (either
the local development instance from Task 1.1.0, or a Dockerized PostgreSQL instance dedicated
to testing). Database mocking is not used.

### Context

The project has zero tests at the start of Phase 1. The Phase 1 test strategy was defined
when it was confirmed that no test strategy existed for the phase (identified as Missing 3
in the pre-implementation review). The test database engine choice has meaningful consequences
for the validity of tests.

### Alternatives Considered

- **Mock the database with unittest.mock or a fake repository**: Fast, no database required.
  However, the mock must accurately reproduce PostgreSQL's behavior — including constraint
  enforcement, transaction semantics, and query results. If the mock diverges from real
  PostgreSQL behavior, tests can pass while the real application fails. This has been
  identified as a known anti-pattern in the project's history: prior incidents where mocked
  tests passed but real database behavior failed influenced this decision.
- **SQLite as a test database**: No separate PostgreSQL instance required. SQLite and
  PostgreSQL have different constraint behavior, different `CHECK` constraint semantics,
  different `TIMESTAMPTZ` handling, and different concurrency models. A test that passes on
  SQLite may fail on PostgreSQL.

### Chosen Solution

A real PostgreSQL instance is used for all database tests in Phase 1. Each test function
that touches the database:
1. Uses a transaction that is rolled back after the test (so tests are isolated without
   needing to drop and recreate the schema between tests).
2. Runs against a dedicated test database (not the development `dass_dev` database).

The choice between a local test database and a Dockerized one is made in Task 1.1.0 and
documented in `tests/README.md`.

Phase 1 tests cover:
- Repository round-trip tests (write a row, read it back, assert all fields match).
- Service-layer tests for mutations with business-rule consequences: status transition guards,
  carryover logic in `DailyOrderPoolService`, capacity checks in the scheduling algorithm.
- Golden-output regression test for the scheduling algorithm (captured before refactoring,
  compared after).

### Rationale

The product vision's priority is correctness. Testing against a mock that does not accurately
represent the real database undermines the correctness guarantee. Using real PostgreSQL means
constraint violations, transaction rollbacks, and query behavior in tests match exactly what
happens in production. The overhead of a real database for this scale of application is
negligible.

### Consequences

- A PostgreSQL instance must be running and accessible before any database test can be
  executed. This is a dependency that the CI environment (Phase 2) must also satisfy.
- Tests are slightly slower than mock-based tests. At the scale of this application (9 tables,
  ~15 technicians, typical order sets of dozens of rows), this overhead is not a concern.

### Future Considerations

- Phase 2 adds CI automation. The CI pipeline must spin up a PostgreSQL service container
  before running tests. This is a standard configuration for GitHub Actions and is consistent
  with the "real database" decision made here.
