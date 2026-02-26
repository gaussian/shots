"""Tests for shots.runner helper functions."""

from __future__ import annotations

from shots.config import ShotSpec
from shots.runner import _build_chains, _format_accumulated_goal


class TestBuildChains:
    def test_single_shot(self):
        shots = [ShotSpec(id="a", description="A")]
        assert _build_chains(shots) == [[0]]

    def test_no_continue(self):
        shots = [
            ShotSpec(id="a", description="A", url="/a"),
            ShotSpec(id="b", description="B", url="/b"),
        ]
        assert _build_chains(shots) == [[0], [1]]

    def test_simple_chain(self):
        shots = [
            ShotSpec(id="a", description="A", url="/a"),
            ShotSpec(id="b", description="B", continue_from_prev=True),
            ShotSpec(id="c", description="C", continue_from_prev=True),
        ]
        assert _build_chains(shots) == [[0, 1, 2]]

    def test_mixed_chains(self):
        shots = [
            ShotSpec(id="a", description="A", url="/a"),
            ShotSpec(id="b", description="B", continue_from_prev=True),
            ShotSpec(id="c", description="C", continue_from_prev=True),
            ShotSpec(id="d", description="D", url="/d"),
            ShotSpec(id="e", description="E", continue_from_prev=True),
        ]
        assert _build_chains(shots) == [[0, 1, 2], [3, 4]]

    def test_all_independent(self):
        shots = [
            ShotSpec(id="a", description="A", url="/a"),
            ShotSpec(id="b", description="B", url="/b"),
            ShotSpec(id="c", description="C", url="/c"),
        ]
        assert _build_chains(shots) == [[0], [1], [2]]


class TestFormatAccumulatedGoal:
    def test_single_description(self):
        result = _format_accumulated_goal(["Navigate to settings"])
        assert result == "Navigate to settings"

    def test_two_descriptions(self):
        result = _format_accumulated_goal(["First step", "Second step"])
        assert "[Step 1 - COMPLETED EARLIER]" in result
        assert "[Step 2 - CURRENT GOAL]" in result
        assert "First step" in result
        assert "Second step" in result
        assert "multi-step" in result

    def test_three_descriptions(self):
        result = _format_accumulated_goal(["Step A", "Step B", "Step C"])
        assert "[Step 1 - COMPLETED EARLIER]" in result
        assert "[Step 2 - COMPLETED EARLIER]" in result
        assert "[Step 3 - CURRENT GOAL]" in result
        assert "Step A" in result
        assert "Step B" in result
        assert "Step C" in result

    def test_only_last_is_current_goal(self):
        result = _format_accumulated_goal(["A", "B", "C", "D"])
        assert result.count("[Step 4 - CURRENT GOAL]") == 1
        assert result.count("COMPLETED EARLIER") == 3
