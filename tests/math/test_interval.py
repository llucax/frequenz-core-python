# License: MIT
# Copyright © 2024 Frequenz Energy-as-a-Service GmbH

"""Tests for the collections module."""


from typing import Self

import pytest

from frequenz.core.math import Bounds, Interval, LessThanComparable


class CustomComparable:
    """A custom comparable class."""

    def __init__(self, value: int) -> None:
        """Initialize this instance."""
        self.value = value

    def __lt__(self, other: Self) -> bool:
        """Return whether this instance is less than other."""
        return self.value < other.value

    def __eq__(self, other: object) -> bool:
        """Return whether this instance is equal to other."""
        if not isinstance(other, CustomComparable):
            return False
        return self.value == other.value

    def __repr__(self) -> str:
        """Return a string representation of this instance."""
        return str(self.value)


@pytest.mark.parametrize(
    "start, end",
    [
        (10.0, -100.0),
        (CustomComparable(10), CustomComparable(-100)),
    ],
)
def test_invalid_range(start: LessThanComparable, end: LessThanComparable) -> None:
    """Test if the interval has an invalid range."""
    with pytest.raises(
        ValueError,
        match=rf"The start \({start}\) can't be bigger than end \({end}\)",
    ):
        Interval(start, end)


@pytest.mark.parametrize(
    "start, end, within, at_start, at_end, before_start, after_end",
    [
        (10.0, 100.0, 50.0, 10.0, 100.0, 9.0, 101.0),
        (
            CustomComparable(10),
            CustomComparable(100),
            CustomComparable(50),
            CustomComparable(10),
            CustomComparable(100),
            CustomComparable(9),
            CustomComparable(101),
        ),
    ],
)
def test_contains(  # pylint: disable=too-many-arguments
    start: LessThanComparable,
    end: LessThanComparable,
    within: LessThanComparable,
    at_start: LessThanComparable,
    at_end: LessThanComparable,
    before_start: LessThanComparable,
    after_end: LessThanComparable,
) -> None:
    """Test if a value is within the interval."""
    interval = Interval(start=start, end=end)
    assert within in interval  # within
    assert at_start in interval  # at start
    assert at_end in interval  # at end
    assert before_start not in interval  # before start
    assert after_end not in interval  # after end


@pytest.mark.parametrize(
    "end, within, at_end, after_end",
    [
        (100.0, 50.0, 100.0, 101.0),
        (
            CustomComparable(100),
            CustomComparable(50),
            CustomComparable(100),
            CustomComparable(101),
        ),
    ],
)
def test_contains_no_start(
    end: LessThanComparable,
    within: LessThanComparable,
    at_end: LessThanComparable,
    after_end: LessThanComparable,
) -> None:
    """Test if a value is within the interval with no start."""
    interval_no_start = Interval(start=None, end=end)
    assert within in interval_no_start  # within end
    assert at_end in interval_no_start  # at end
    assert after_end not in interval_no_start  # after end


@pytest.mark.parametrize(
    "start, within, at_start, before_start",
    [
        (10.0, 50.0, 10.0, 9.0),
        (
            CustomComparable(10),
            CustomComparable(50),
            CustomComparable(10),
            CustomComparable(9),
        ),
    ],
)
def test_contains_no_end(
    start: LessThanComparable,
    within: LessThanComparable,
    at_start: LessThanComparable,
    before_start: LessThanComparable,
) -> None:
    """Test if a value is within the interval with no end."""
    interval_no_end = Interval(start=start, end=None)
    assert within in interval_no_end  # within start
    assert at_start in interval_no_end  # at start
    assert before_start not in interval_no_end  # before start


@pytest.mark.parametrize(
    "value",
    [
        50.0,
        10.0,
        -10.0,
        CustomComparable(50),
        CustomComparable(10),
        CustomComparable(-10),
    ],
)
def test_contains_unbound(value: LessThanComparable) -> None:
    """Test if a value is within the interval with no bounds."""
    interval_no_bounds: Interval[LessThanComparable | None] = Interval(
        start=None, end=None
    )
    assert value in interval_no_bounds  # any value within bounds


def test_bounds_constructor_fail() -> None:
    """Test that bounds can't be created without any limits."""
    with pytest.raises(
        ValueError, match="At least one interval or bound must be provided"
    ):
        Bounds()


def test_bounds_with_upper_lower() -> None:
    """Test that bounds are created correctly with upper and lower limits."""
    bounds = Bounds(lower=10.0, upper=100.0)
    assert 10.0 in bounds
    assert 100.0 in bounds
    assert 50.0 in bounds
    assert 9.0 not in bounds
    assert 100.0001 not in bounds


def test_bounds_with_interval() -> None:
    """Test that bounds are created correctly with an interval."""
    bounds = Bounds(Interval(10.0, 100.0))
    assert 10.0 in bounds
    assert 100.0 in bounds
    assert 50.0 in bounds
    assert 9.0 not in bounds
    assert 100.0001 not in bounds


def test_bounds_with_many_intervals() -> None:
    """Test that bounds are created correctly with multiple intervals."""
    bounds: Bounds[float | None] = Bounds(
        Interval(-2.0, 0.0), Interval(4.0, 6.0), Interval(7.0, None)
    )
    for value in [-2.0, -1.9999, -0.5, 0.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 1090349.0349]:
        assert value in bounds
    for value in [-3.0, -2.001, 0.1, 1.0, 2.0, 3.0, 6.01, 6.9999]:
        assert value not in bounds
