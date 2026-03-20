"""Student data store for persistence operations."""

from datetime import datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from luca.persistence.database import get_database
from luca.persistence.models import (
    ConceptMastery,
    ErrorHistory,
    Session,
    Student,
    TeachingBriefRecord,
)
from luca.student.teaching_brief import TeachingBrief
from luca.utils.logging import get_logger

logger = get_logger("persistence.student_store")


class StudentStore:
    """Store for student-related database operations."""

    async def create_student(self, name: str | None = None) -> Student:
        """Create a new student."""
        db = get_database()
        async with db.session() as session:
            student = Student(id=str(uuid4()), name=name)
            session.add(student)
            await session.flush()
            logger.info(f"Created student: {student.id}")
            return student

    async def get_student(self, student_id: str) -> Student | None:
        """Get a student by ID."""
        db = get_database()
        async with db.session() as session:
            result = await session.execute(
                select(Student).where(Student.id == student_id)
            )
            return result.scalar_one_or_none()

    async def get_mastery(
        self, student_id: str, concept_id: str
    ) -> ConceptMastery | None:
        """Get mastery record for a student-concept pair."""
        db = get_database()
        async with db.session() as session:
            result = await session.execute(
                select(ConceptMastery).where(
                    ConceptMastery.student_id == student_id,
                    ConceptMastery.concept_id == concept_id,
                )
            )
            return result.scalar_one_or_none()

    async def update_mastery(
        self,
        student_id: str,
        concept_id: str,
        mastery: float,
        correct: bool,
    ) -> ConceptMastery:
        """Update mastery for a concept."""
        db = get_database()
        async with db.session() as session:
            result = await session.execute(
                select(ConceptMastery).where(
                    ConceptMastery.student_id == student_id,
                    ConceptMastery.concept_id == concept_id,
                )
            )
            record = result.scalar_one_or_none()

            if record:
                record.mastery = mastery
                record.attempts += 1
                record.correct += 1 if correct else 0
                record.last_practiced = datetime.now()
            else:
                record = ConceptMastery(
                    student_id=student_id,
                    concept_id=concept_id,
                    mastery=mastery,
                    attempts=1,
                    correct=1 if correct else 0,
                    last_practiced=datetime.now(),
                )
                session.add(record)

            await session.flush()
            return record

    async def get_all_mastery(self, student_id: str) -> list[ConceptMastery]:
        """Get all mastery records for a student."""
        db = get_database()
        async with db.session() as session:
            result = await session.execute(
                select(ConceptMastery).where(ConceptMastery.student_id == student_id)
            )
            return list(result.scalars().all())

    async def save_teaching_brief(
        self, student_id: str, brief: TeachingBrief
    ) -> TeachingBriefRecord:
        """Save or update a teaching brief."""
        db = get_database()
        async with db.session() as session:
            result = await session.execute(
                select(TeachingBriefRecord).where(
                    TeachingBriefRecord.student_id == student_id
                )
            )
            record = result.scalar_one_or_none()

            brief_data = {
                "strengths": brief.strengths,
                "challenges": brief.challenges,
                "preferred_explanation_style": brief.preferred_explanation_style,
                "optimal_session_length": brief.optimal_session_length,
                "error_patterns": brief.error_patterns,
                "effective_strategies": brief.effective_strategies,
                "summary": brief.summary,
            }

            if record:
                record.brief_data = brief_data
                record.generated_at = datetime.now()
            else:
                record = TeachingBriefRecord(
                    student_id=student_id,
                    brief_data=brief_data,
                )
                session.add(record)

            await session.flush()
            return record

    async def create_session(self, student_id: str) -> Session:
        """Create a new tutoring session."""
        db = get_database()
        async with db.session() as session:
            tutoring_session = Session(
                id=str(uuid4()),
                student_id=student_id,
            )
            session.add(tutoring_session)
            await session.flush()
            return tutoring_session

    async def save_error(
        self,
        student_id: str,
        error_type: str,
        concept_id: str,
        student_response: str = "",
        expected_response: str = "",
    ) -> ErrorHistory:
        """Save an error occurrence."""
        db = get_database()
        async with db.session() as session:
            record = ErrorHistory(
                student_id=student_id,
                error_type=error_type,
                concept_id=concept_id,
                student_response=student_response,
                expected_response=expected_response,
            )
            session.add(record)
            await session.flush()
            return record

    async def get_error_history(
        self, student_id: str, limit: int = 100
    ) -> list[ErrorHistory]:
        """Get error history for a student."""
        db = get_database()
        async with db.session() as session:
            result = await session.execute(
                select(ErrorHistory)
                .where(ErrorHistory.student_id == student_id)
                .order_by(ErrorHistory.created_at.desc())
                .limit(limit)
            )
            return list(result.scalars().all())

    async def get_teaching_brief(self, student_id: str) -> TeachingBrief | None:
        """Get the teaching brief for a student."""
        db = get_database()
        async with db.session() as session:
            result = await session.execute(
                select(TeachingBriefRecord).where(
                    TeachingBriefRecord.student_id == student_id
                )
            )
            record = result.scalar_one_or_none()
            if not record:
                return None

            data = record.brief_data
            return TeachingBrief(
                student_id=student_id,
                strengths=data.get("strengths", []),
                challenges=data.get("challenges", []),
                preferred_explanation_style=data.get("preferred_explanation_style", ""),
                optimal_session_length=data.get("optimal_session_length", 20),
                response_time_pattern=data.get("response_time_pattern", "average"),
                error_patterns=data.get("error_patterns", []),
                effective_strategies=data.get("effective_strategies", []),
                summary=data.get("summary", ""),
                trigger_type=data.get("trigger_type", ""),
                trigger_concept=data.get("trigger_concept", ""),
            )
