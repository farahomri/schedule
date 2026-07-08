> ⚠️ **UPDATED** — Architecture revised based on real codebase analysis (May 2026). Chatbot and Audit deferred to post-production phase.
> 

---

## Architecture Decision: Layered Monolith (Streamlit-First, FastAPI-Ready)

Based on the real codebase, the app is a **pure Streamlit app** with no backend separation yet. The architecture below defines the **target state** for Phase 1 (production-ready Streamlit + DB), with FastAPI introduced only when needed.

---

## Revised Stack

| Layer | Current (Existing) | Target (Phase 1) | Future (Phase 2+) |
| --- | --- | --- | --- |
| Frontend | Streamlit ✅ | Streamlit ✅ | React (optional) |
| Backend | Embedded in Streamlit | FastAPI service layer | FastAPI microservices |
| Database | CSV files ❌ | PostgreSQL 15 | PostgreSQL (scaled) |
| ORM | None | SQLAlchemy 2.x + Alembic | Same |
| Scheduling | `initial_scheduling.py` ✅ | `SchedulingService` (refactored) | Same |
| AI/Chatbot | None | **DEFERRED** | Claude API |
| Audit | None | **DEFERRED** | Audit logs |
| Auth | `AuthService` (basic) ✅ | JWT-hardened | Same |

---

## What Exists in the Codebase (Real Analysis)

### ✅ Reusable As-Is

- `app.py` — page routing, sidebar navigation, `SessionManager`, auth check
- `models/technicians.py` — `Technician` class, classify/load/save/add/modify/delete logic → **keep, wrap with DB layer**
- `models/orders.py` — `classify_order`, load/save/add/modify/delete → **keep logic, replace CSV with DB**
- `models/initial_scheduling.py` — `create_initial_schedule()` with 3-phase algorithm (round-robin → balanced → capacity fill) → **core logic is solid, keep it**
- `services/schedule_service.py` — `ScheduleService` with `update_order_status`, `change_technician`, `change_priority`, `mark_as_blocked` → **well-structured, reusable**
- All Streamlit page rendering functions — UI layout and forms are good

### 🔄 Refactor (Logic Good, Storage Broken)

- All `pd.read_csv()` / `df.to_csv()` calls → replace with DB repository calls
- `SessionManager` state (`initial_schedule_df`, `unscheduled_orders_df`) → keep for UI state, but source from DB not CSV
- `PersistenceService.save_schedule()` / `FileService.save_schedule()` → replace with DB writes

### ❌ Remove / Replace

- All flat CSV data files (`technicians_file.csv`, `products_classified.csv`, schedule CSV)
- `save_technicians()` / `load_technicians()` from CSV → replace with DB queries
- `save_orders()` / `load_orders()` from CSV → replace with DB queries

### 🗑️ Defer (Not v1)

- Chatbot / AI integration
- Audit logs
- Reclamations module (low priority, defer after core scheduling works)

---

## Real Data Model (from codebase)

### Technician

```
Matricule (badge number, string PK)
Nom et prénom
Niveau 4 / 3 / 2 / 1 (qualification counts per level)
Classification (computed: Basic Knowledge / Above Average / Good / Advanced)
Expertise Class (computed numeric: 1-4)
```

### Order (Products Classified)

```
SAP (material number, string PK)
Material Description
routing time (minutes)
Class (Low / Medium / High / Very High)
Class Code (1-4, derived from routing time thresholds: 0-160 / 160-320 / 320-480 / 480+)
```

### Schedule Row (runtime, currently in-memory/CSV)

```
Day/Date, SAP, Order ID, Material Description, Routing Time (min)
Technician Matricule, Technician Name
Status (Planned / In Progress / Partially Completed / Completed / Blocked)
Remaining Time, Remark, Priority
Class Code
StartTime, StopTime, EndTime
RealSpentTime, RemainingRoutingTime
ScheduleRowID (UUID), SequenceNumber
FirstStartTime, TotalTimeSpent, WorkSessions (JSON sessions array)
```

### Shift (input file)

```
Matricule, Technician Name
Working (yes/no), Holiday (yes/no), Break (min), Extra Time (min)
To another (yes/no — transferred to another area)
Working Time (computed: 480 + 30 - Break + Extra Time = ~510min base)
```

---

## Scheduling Algorithm (Confirmed — 3-Phase)

The existing `create_initial_schedule()` in `initial_scheduling.py` uses:

**Phase 1 — Round Robin**: Assign one order to each technician first (fairness baseline)

**Phase 2 — Balanced Assignment**: Remaining orders assigned by: least total assigned time → exact expertise match → most available time

**Phase 3 — Capacity Fill**: Fill remaining technician capacity with any unscheduled order, ignoring expertise (marked with remark "Capacity fill")

**Sorting**: Orders sorted by Priority (Urgent=0, A=1, B=2, C=3) then by routing time DESC before assignment

**Expertise constraint**: `technician.Expertise Class >= order.Class Code` (higher can do lower)

---

## Target Architecture Diagram

```
┌───────────────────────────────────┐
│     STREAMLIT FRONTEND (app.py)   │
│  Pages: Schedule / Orders /       │
│  Technicians / Initial Scheduling │
└──────────────────┬────────────────┘
                   │ (direct service calls in v1)
┌──────────────────▼────────────────┐
│         SERVICE LAYER             │
│  SchedulingService (refactored)   │
│  OrderService (new)               │
│  TechnicianService (new)          │
│  ShiftService (new)               │
└──────────────────┬────────────────┘
                   │
┌──────────────────▼────────────────┐
│     REPOSITORY LAYER (new)        │
│  SQLAlchemy queries replacing     │
│  all CSV read/write calls         │
└──────────────────┬────────────────┘
                   │
┌──────────────────▼────────────────┐
│         PostgreSQL 15             │
│  technicians, orders, schedules,  │
│  shifts, assignments              │
└───────────────────────────────────┘
```

---