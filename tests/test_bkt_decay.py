"""Tests for BKT decay functionality."""

import pytest

from luca.curriculum.models import BKTParameters
from luca.student.bkt import BKTModel


class TestBKTDecay:
    """Tests for BKT apply_decay method."""

    def test_decay_reduces_mastery(self):
        """Test that decay reduces mastery over time."""
        model = BKTModel()

        # Build up mastery
        for _ in range(10):
            model.update("concept_1", correct=True)

        high_mastery = model.get_mastery("concept_1")
        assert high_mastery > 0.5

        # Set p_forget
        model.params["concept_1"] = {**model.DEFAULT_PARAMS, "p_forget": 0.1}

        # Apply decay for 24 hours (1 day)
        new_mastery = model.apply_decay("concept_1", hours_elapsed=24)

        assert new_mastery < high_mastery
        assert new_mastery == pytest.approx(high_mastery * 0.9, rel=0.01)

    def test_decay_with_multiple_days(self):
        """Test decay over multiple days."""
        model = BKTModel()
        model.mastery["concept_1"] = 0.8
        model.params["concept_1"] = {**model.DEFAULT_PARAMS, "p_forget": 0.1}

        # Apply decay for 48 hours (2 days)
        # Expected: 0.8 * (1 - 0.1)^2 = 0.8 * 0.81 = 0.648
        new_mastery = model.apply_decay("concept_1", hours_elapsed=48)

        assert new_mastery == pytest.approx(0.648, rel=0.01)

    def test_decay_respects_floor(self):
        """Test that decay doesn't go below p_init."""
        model = BKTModel()
        model.mastery["concept_1"] = 0.2
        model.params["concept_1"] = {**model.DEFAULT_PARAMS, "p_forget": 0.5, "p_init": 0.1}

        # Apply heavy decay
        new_mastery = model.apply_decay("concept_1", hours_elapsed=240)  # 10 days

        # Should not go below p_init
        assert new_mastery >= 0.1

    def test_no_decay_with_zero_p_forget(self):
        """Test no decay when p_forget is 0."""
        model = BKTModel()
        model.mastery["concept_1"] = 0.8
        model.params["concept_1"] = {**model.DEFAULT_PARAMS, "p_forget": 0.0}

        new_mastery = model.apply_decay("concept_1", hours_elapsed=1000)

        assert new_mastery == 0.8

    def test_no_decay_with_zero_hours(self):
        """Test no decay when hours_elapsed is 0."""
        model = BKTModel()
        model.mastery["concept_1"] = 0.8
        model.params["concept_1"] = {**model.DEFAULT_PARAMS, "p_forget": 0.1}

        new_mastery = model.apply_decay("concept_1", hours_elapsed=0)

        assert new_mastery == 0.8

    def test_decay_unknown_concept(self):
        """Test decay on unknown concept returns p_init."""
        model = BKTModel()

        mastery = model.apply_decay("unknown", hours_elapsed=24)

        assert mastery == model.DEFAULT_PARAMS["p_init"]

    def test_set_params_includes_p_forget(self):
        """Test that set_params correctly sets p_forget."""
        model = BKTModel()
        params = BKTParameters(
            p_init=0.1,
            p_learn=0.2,
            p_guess=0.25,
            p_slip=0.1,
            p_forget=0.15,
        )

        model.set_params("concept_1", params)

        assert model.params["concept_1"]["p_forget"] == 0.15

    def test_set_mastery(self):
        """Test set_mastery method."""
        model = BKTModel()

        model.set_mastery("concept_1", 0.75)
        assert model.get_mastery("concept_1") == 0.75

        # Test bounds
        model.set_mastery("concept_2", 1.5)
        assert model.get_mastery("concept_2") == 1.0

        model.set_mastery("concept_3", -0.5)
        assert model.get_mastery("concept_3") == 0.0

    def test_decay_partial_day(self):
        """Test decay with partial days (12 hours = 0.5 days)."""
        model = BKTModel()
        model.mastery["concept_1"] = 0.8
        model.params["concept_1"] = {**model.DEFAULT_PARAMS, "p_forget": 0.1}

        # 12 hours = 0.5 days
        # Expected: 0.8 * (1 - 0.1)^0.5 = 0.8 * 0.9486... ≈ 0.759
        new_mastery = model.apply_decay("concept_1", hours_elapsed=12)

        expected = 0.8 * (0.9 ** 0.5)
        assert new_mastery == pytest.approx(expected, rel=0.01)
