"""Student data store for persistence operations."""

from datetime import datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from luca.persistence.database import get_database
from luca.persistence.models import ConceptMastery, Session, Student, TeachingBriefRecord
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
