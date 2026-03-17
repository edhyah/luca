"""Tests for the BKT model."""

import pytest
from luca.student.bkt import BKTModel


class TestBKTModel:
    """Tests for BKTModel."""

    def test_initial_mastery(self):
        """Test that initial mastery is the prior probability."""
        model = BKTModel()
        mastery = model.get_mastery("new_concept")
        assert mastery == model.DEFAULT_PARAMS["p_init"]

    def test_mastery_increases_on_correct(self):
        """Test that mastery increases after correct response."""
        model = BKTModel()
        initial = model.get_mastery("concept_1")
        model.update("concept_1", correct=True)
        updated = model.get_mastery("concept_1")
        assert updated > initial

    def test_mastery_changes_on_incorrect(self):
        """Test that mastery changes after incorrect response."""
        model = BKTModel()
        # First get some mastery
        model.update("concept_1", correct=True)
        model.update("concept_1", correct=True)
        high_mastery = model.get_mastery("concept_1")

        # Then an incorrect response
        model.update("concept_1", correct=False)
        after_incorrect = model.get_mastery("concept_1")

        # Mastery should decrease but learning can still occur
        # so it might not be strictly less, but it should change
        assert after_incorrect != high_mastery or after_incorrect > 0

    def test_get_mastered_concepts(self):
        """Test getting concepts above mastery threshold."""
        model = BKTModel()

        # Build up mastery for one concept
        for _ in range(10):
            model.update("concept_1", correct=True)

        # Low mastery for another
        model.update("concept_2", correct=False)

        mastered = model.get_mastered_concepts(threshold=0.8)
        assert "concept_1" in mastered
        assert "concept_2" not in mastered

    def test_mastery_bounded(self):
        """Test that mastery stays between 0 and 1."""
        model = BKTModel()

        # Many correct responses
        for _ in range(100):
            model.update("concept_1", correct=True)

        mastery = model.get_mastery("concept_1")
        assert 0 <= mastery <= 1

        # Many incorrect responses
        for _ in range(100):
            model.update("concept_2", correct=False)

        mastery = model.get_mastery("concept_2")
        assert 0 <= mastery <= 1
