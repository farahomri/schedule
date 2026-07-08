import uuid

from sqlalchemy import (
    Boolean, CheckConstraint, Column, Date, DateTime,
    ForeignKey, Index, Integer, Numeric, String, Text,
    UniqueConstraint, func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from db.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    username = Column(String(100), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(20), nullable=False)  # admin | manager | user
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    schedule_locks = relationship("ScheduleLock", back_populates="locked_by_user")


class Technician(Base):
    __tablename__ = "technicians"
    __table_args__ = (
        Index("idx_technicians_matricule", "matricule"),
    )

    id = Column(Integer, primary_key=True)
    matricule = Column(String(50), unique=True, nullable=False)
    full_name = Column(String(200), nullable=False)
    department = Column(String(100), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    skills = relationship("TechnicianSkill", back_populates="technician", cascade="all, delete-orphan")
    shifts = relationship("Shift", back_populates="technician")
    assignments = relationship("ScheduleAssignment", back_populates="technician")


class TechnicianSkill(Base):
    __tablename__ = "technician_skills"
    __table_args__ = (
        UniqueConstraint("technician_id", "skill_level", name="uq_tech_skill_level"),
        Index("idx_tech_skills_tech_id", "technician_id"),
    )

    id = Column(Integer, primary_key=True)
    technician_id = Column(Integer, ForeignKey("technicians.id", ondelete="CASCADE"), nullable=False)
    skill_level = Column(Integer, nullable=False)   # 1, 2, 3, or 4
    score = Column(Integer, nullable=False, default=0)
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    technician = relationship("Technician", back_populates="skills")


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (
        Index("idx_products_sap", "sap_number"),
    )

    id = Column(Integer, primary_key=True)
    sap_number = Column(String(100), unique=True, nullable=False)
    description = Column(String(500), nullable=False)
    routing_time_minutes = Column(Numeric(8, 2), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    production_orders = relationship("ProductionOrder", back_populates="product")


class ProductionOrder(Base):
    __tablename__ = "production_orders"
    __table_args__ = (
        UniqueConstraint("erp_order_id", "order_date", name="uq_erp_order_date"),
        Index("idx_prod_orders_date", "order_date"),
        Index("idx_prod_orders_product", "product_id"),
    )

    id = Column(Integer, primary_key=True)
    erp_order_id = Column(String(100), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    priority = Column(String(20), nullable=True)    # Urgent | A | B | C | null
    order_date = Column(Date, nullable=False)
    quantity = Column(Integer, nullable=False, default=1)
    department = Column(String(100), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    product = relationship("Product", back_populates="production_orders")
    assignment = relationship("ScheduleAssignment", back_populates="production_order", uselist=False)


class Shift(Base):
    __tablename__ = "shifts"
    __table_args__ = (
        UniqueConstraint("technician_id", "shift_date", name="uq_tech_shift_date"),
        Index("idx_shifts_date", "shift_date"),
    )

    id = Column(Integer, primary_key=True)
    technician_id = Column(Integer, ForeignKey("technicians.id"), nullable=False)
    shift_date = Column(Date, nullable=False)
    is_working = Column(Boolean, nullable=False, default=False)
    is_transferred = Column(Boolean, nullable=False, default=False)   # "To another"
    break_minutes = Column(Integer, nullable=False, default=30)
    extra_time_minutes = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    technician = relationship("Technician", back_populates="shifts")


class ScheduleAssignment(Base):
    __tablename__ = "schedule_assignments"
    __table_args__ = (
        UniqueConstraint("production_order_id", "schedule_date", name="uq_order_assignment_date"),
        CheckConstraint(
            "status IN ('Planned', 'In Progress', 'Partially Completed', 'Completed', 'Blocked')",
            name="ck_assignment_status",
        ),
        Index("idx_assignments_date", "schedule_date"),
        Index("idx_assignments_technician", "technician_id", "schedule_date"),
        Index("idx_assignments_status", "status"),
    )

    id = Column(Integer, primary_key=True)
    schedule_row_id = Column(UUID(as_uuid=True), unique=True, nullable=False, default=uuid.uuid4)
    production_order_id = Column(Integer, ForeignKey("production_orders.id"), nullable=False)
    technician_id = Column(Integer, ForeignKey("technicians.id"), nullable=False)
    schedule_date = Column(Date, nullable=False)
    sequence_number = Column(Integer, nullable=False)
    status = Column(String(30), nullable=False, default="Planned")
    routing_time_minutes = Column(Numeric(8, 2), nullable=False)        # snapshot at scheduling time
    remaining_time_minutes = Column(Numeric(8, 2), nullable=False)
    remark = Column(Text, nullable=True)
    is_expertise_override = Column(Boolean, nullable=False, default=False)
    was_unblocked_by_manager = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    production_order = relationship("ProductionOrder", back_populates="assignment")
    technician = relationship("Technician", back_populates="assignments")
    work_sessions = relationship("WorkSession", back_populates="assignment", cascade="all, delete-orphan")


class WorkSession(Base):
    __tablename__ = "work_sessions"
    __table_args__ = (
        CheckConstraint(
            "stopped_at IS NULL OR stopped_at > started_at",
            name="ck_session_time_order",
        ),
        Index("idx_work_sessions_assignment", "assignment_id"),
    )

    id = Column(Integer, primary_key=True)
    assignment_id = Column(Integer, ForeignKey("schedule_assignments.id", ondelete="CASCADE"), nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=False)
    stopped_at = Column(DateTime(timezone=True), nullable=True)   # NULL = currently in progress
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    assignment = relationship("ScheduleAssignment", back_populates="work_sessions")


class ScheduleLock(Base):
    __tablename__ = "schedule_locks"

    id = Column(Integer, primary_key=True)
    schedule_date = Column(Date, unique=True, nullable=False)
    locked_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    locked_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    released_at = Column(DateTime(timezone=True), nullable=True)

    locked_by_user = relationship("User", back_populates="schedule_locks")
