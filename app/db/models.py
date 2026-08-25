from datetime import datetime
from enum import Enum

from sqlalchemy import String, DateTime, ForeignKey, Text, CheckConstraint, func, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import JSONB

from pgvector.sqlalchemy import HALFVEC


class Base(DeclarativeBase):
    pass


class Manager(Base):
    __tablename__ = "managers"

    id: Mapped[int] = mapped_column(primary_key=True)
    feedbacks: Mapped[list["Feedback"]] = relationship(back_populates="manager")
    morning_notes: Mapped[list["MorningNote"]] = relationship(back_populates="manager")
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(primary_key=True)
    morning_notes: Mapped[list["MorningNote"]] = relationship(back_populates="company")
    ticker: Mapped[str] = mapped_column(String(12), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    sector: Mapped[str | None] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Portfolio(Base):
    __tablename__ = "portfolios"

    id: Mapped[int] = mapped_column(primary_key=True)
    manager_id: Mapped[int] = mapped_column(ForeignKey("managers.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class PortfolioHolding(Base):
    __tablename__ = "portfolio_holdings"

    id: Mapped[int] = mapped_column(primary_key=True)
    portfolio_id: Mapped[int] = mapped_column(ForeignKey("portfolios.id"), nullable=False, index=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), nullable=False, index=True)
    weight: Mapped[float] = mapped_column(nullable=False)
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class MorningNoteStatus(str, Enum):
    PENDING = "pending"
    GENERATING = "generating"
    COMPLETED = "completed"
    FAILED = "failed"


class MorningNote(Base):
    __tablename__ = "morning_notes"

    id: Mapped[int] = mapped_column(primary_key=True)
    feedbacks: Mapped[list["Feedback"]] = relationship(back_populates="morning_note")
    recommendation: Mapped["Recommendation"] = relationship(back_populates="morning_note", uselist=False)
    manager: Mapped["Manager"] = relationship(back_populates="morning_notes")
    company: Mapped["Company"] = relationship(back_populates="morning_notes")
    portfolio_id: Mapped[int] = mapped_column(ForeignKey("portfolios.id"), nullable=False, index=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    note_text: Mapped[str] = mapped_column(Text, nullable=False)
    pipeline_run_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    status: Mapped[MorningNoteStatus] = mapped_column(
        String(16), 
        CheckConstraint("status IN ('pending', 'generating', 'completed', 'failed')", name="ck_morning_notes_status"), 
        nullable=False, server_default=MorningNoteStatus.PENDING.value
    )
    confidence_scores: Mapped[dict[str, float]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    data_freshness: Mapped[dict[str, datetime]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    flags: Mapped[list[dict[str, str]]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    manager_id: Mapped[int] = mapped_column(ForeignKey("managers.id"), nullable=False, index=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), nullable=False, index=True)
    embedding: Mapped[list[float] | None] = mapped_column(HALFVEC(2048), nullable=True)


class Recommendation(Base):
    __tablename__ = "recommendations"

    id: Mapped[int] = mapped_column(primary_key=True)
    morning_note_id: Mapped[int] = mapped_column(ForeignKey("morning_notes.id"), nullable=False, index=True)
    morning_note: Mapped["MorningNote"] = relationship(back_populates="recommendation")
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    confidence: Mapped[float] = mapped_column(nullable=False)
    justification: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class FeedbackAction(str, Enum):
    BUY = "buy"
    SELL = "sell"
    KEEP = "keep"


class Feedback(Base):
    __tablename__ = "feedbacks"

    id: Mapped[int] = mapped_column(primary_key=True)
    morning_note: Mapped["MorningNote"] = relationship(back_populates="feedbacks")
    manager: Mapped["Manager"] = relationship(back_populates="feedbacks")
    morning_note_id: Mapped[int] = mapped_column(ForeignKey("morning_notes.id"), nullable=False, index=True)
    manager_id: Mapped[int] = mapped_column(ForeignKey("managers.id"), nullable=False, index=True)
    action: Mapped[FeedbackAction] = mapped_column(
        String(16), 
        CheckConstraint("action IN ('buy', 'sell', 'keep')", name="ck_feedback_action"),
        nullable=False
    )
    justification: Mapped[str] = mapped_column(Text, nullable=False)
    comment: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
