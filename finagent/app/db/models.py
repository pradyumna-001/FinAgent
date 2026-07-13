import enum
from datetime import datetime
from typing import List, Optional
from sqlalchemy import String, Integer, ForeignKey, DateTime, Enum, Index, Text, text
from sqlalchemy.dialects.postgresql import JSONB, ARRAY
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from pgvector.sqlalchemy import Vector

class Base(DeclarativeBase):
    pass

class StatusEnum(enum.Enum):
    pending = "pending"
    generating = "generating"
    completed = "completed"
    failed = "failed"

class Manager(Base):
    __tablename__ = "managers"

    manager_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)

    companies: Mapped[List["Company"]] = relationship(
        secondary="portfolios", back_populates="managers"
    )

class Company(Base):
    __tablename__ = "companies"
    
    company_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String(12), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    sector: Mapped[str] = mapped_column(String(100), nullable=False)

    managers: Mapped[List[Manager]] = relationship(
        secondary="portfolios", back_populates="companies"
    )

class Portfolio(Base):
    __tablename__ = "portfolios"

    manager_id: Mapped[int] = mapped_column(
        Integer, 
        ForeignKey("managers.manager_id", ondelete="CASCADE"),
        primary_key=True
    )
    company_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("companies.company_id", ondelete="CASCADE"),
        primary_key=True
    )

class MorningNote(Base):
    __tablename__ = "morning_notes"

    morning_note_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pipeline_run_id: Mapped[str] = mapped_column(String(64), nullable=False)
    manager_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("managers.manager_id", ondelete="CASCADE"),
        nullable=False
    )
    company_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("companies.company_id", ondelete="CASCADE"),
        nullable=False
    )
    date: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)

    confidence_score: Mapped[dict] = mapped_column(JSONB, nullable=False)
    data_freshness: Mapped[dict] = mapped_column(JSONB, nullable=False)
    flags: Mapped[Optional[List[dict]]] = mapped_column(ARRAY(JSONB), nullable=True)

    status: Mapped[StatusEnum] = mapped_column(
        Enum(StatusEnum, name="status_enum"),
        default=StatusEnum.pending,
        nullable=True
    )

    embedding: Mapped[Optional[Vector]] = mapped_column(Vector(1536), nullable=True)

    recommendation: Mapped["Recommendation"] = relationship(
        back_populates="morning_note",
        uselist=False,
        cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_manager_company_date", "manager_id", "company_id", "date"),
        Index("idx_partial_completed_data", "date", postgresql_where=text("status = 'completed'")),
    )

class Recommendation(Base):
    __tablename__ = "recommendations"

    recommendation_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    morning_note_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("morning_notes.morning_note_id", ondelete="CASCADE"),
        nullable=False
    )
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    justification: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(nullable=False)

    morning_note: Mapped[MorningNote] = relationship(back_populates="recommendation")
