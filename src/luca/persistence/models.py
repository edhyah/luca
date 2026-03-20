"""SQLAlchemy models for persistence."""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Float, ForeignKey, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all models."""

    pass


class Student(Base):
    """Student profile and settings."""

    __tablename__ = "students"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    mastery_records: Mapped[list["ConceptMastery"]] = relationship(
        back_populates="student", cascade="all, delete-orphan"
    )
    sessions: Mapped[list["Session"]] = relationship(
        back_populates="student", cascade="all, delete-orphan"
    )
    teaching_brief: Mapped["TeachingBriefRecord | None"] = relationship(
        back_populates="student", uselist=False, cascade="all, delete-orphan"
    )
    error_history: Mapped[list["ErrorHistory"]] = relationship(
        back_populates="student", cascade="all, delete-orphan"
    )


class ConceptMastery(Base):
    """Student mastery level for a concept."""

    __tablename__ = "concept_mastery"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    student_id: Mapped[str] = mapped_column(ForeignKey("students.id"), index=True)
    concept_id: Mapped[str] = mapped_column(String(255), index=True)
    mastery: Mapped[float] = mapped_column(Float, default=0.0)
    attempts: Mapped[int] = mapped_column(default=0)
    correct: Mapped[int] = mapped_column(default=0)
    last_practiced: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # BKT parameters (can be personalized per student)
    bkt_params: Mapped[dict[str, Any] | None] = mapped_column(JSON)

    student: Mapped["Student"] = relationship(back_populates="mastery_records")


class Session(Base):
    """Tutoring session record."""

    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    student_id: Mapped[str] = mapped_column(ForeignKey("students.id"), index=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    concepts_covered: Mapped[list[str] | None] = mapped_column(JSON)
    summary: Mapped[str | None] = mapped_column(Text)

    student: Mapped["Student"] = relationship(back_populates="sessions")
    exchanges: Mapped[list["Exchange"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )


class Exchange(Base):
    """Single exchange (prompt + response) in a session."""

    __tablename__ = "exchanges"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.id"), index=True)
    concept_id: Mapped[str | None] = mapped_column(String(255))
    tutor_prompt: Mapped[str] = mapped_column(Text)
    student_response: Mapped[str | None] = mapped_column(Text)
    expected_response: Mapped[str | None] = mapped_column(Text)
    correct: Mapped[bool | None] = mapped_column()
    response_time_ms: Mapped[int | None] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    session: Mapped["Session"] = relationship(back_populates="exchanges")


class TeachingBriefRecord(Base):
    """Stored teaching brief for a student."""

    __tablename__ = "teaching_briefs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    student_id: Mapped[str] = mapped_column(
        ForeignKey("students.id"), unique=True, index=True
    )
    brief_data: Mapped[dict[str, Any]] = mapped_column(JSON)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    student: Mapped["Student"] = relationship(back_populates="teaching_brief")


class ErrorHistory(Base):
    """Error occurrence record for pattern tracking."""

    __tablename__ = "error_history"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    student_id: Mapped[str] = mapped_column(ForeignKey("students.id"), index=True)
    error_type: Mapped[str] = mapped_column(String(255), index=True)
    concept_id: Mapped[str] = mapped_column(String(255), index=True)
    student_response: Mapped[str | None] = mapped_column(Text)
    expected_response: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    student: Mapped["Student"] = relationship(back_populates="error_history")
