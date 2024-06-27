# License: MIT
# Copyright © 2024 Frequenz Energy-as-a-Service GmbH

"""Tests for the collections module."""


from typing import Self

import pytest

from frequenz.core.collections import Bounds, LessThanComparable


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
    "lower, upper, within, at_lower, at_upper, below_lower, above_upper",
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
def test_bounds_contains(  # pylint: disable=too-many-arguments
    lower: LessThanComparable,
    upper: LessThanComparable,
    within: LessThanComparable,
    at_lower: LessThanComparable,
    at_upper: LessThanComparable,
    below_lower: LessThanComparable,
    above_upper: LessThanComparable,
) -> None:
    """Test if a value is within the bounds."""
    bounds = Bounds(lower=lower, upper=upper)
    assert within in bounds  # within
    assert at_lower in bounds  # at lower
    assert at_upper in bounds  # at upper
    assert below_lower not in bounds  # below lower
    assert above_upper not in bounds  # above upper


@pytest.mark.parametrize(
    "upper, within, at_upper, above_upper",
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
def test_bounds_contains_no_lower(
    upper: LessThanComparable,
    within: LessThanComparable,
    at_upper: LessThanComparable,
    above_upper: LessThanComparable,
) -> None:
    """Test if a value is within the bounds with no lower bound."""
    bounds_no_lower = Bounds(lower=None, upper=upper)
    assert within in bounds_no_lower  # within upper
    assert at_upper in bounds_no_lower  # at upper
    assert above_upper not in bounds_no_lower  # above upper


@pytest.mark.parametrize(
    "lower, within, at_lower, below_lower",
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
def test_bounds_contains_no_upper(
    lower: LessThanComparable,
    within: LessThanComparable,
    at_lower: LessThanComparable,
    below_lower: LessThanComparable,
) -> None:
    """Test if a value is within the bounds with no upper bound."""
    bounds_no_upper = Bounds(lower=lower, upper=None)
    assert within in bounds_no_upper  # within lower
    assert at_lower in bounds_no_upper  # at lower
    assert below_lower not in bounds_no_upper  # below lower


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
def test_bounds_contains_no_bounds(value: LessThanComparable) -> None:
    """Test if a value is within the bounds with no bounds."""
    bounds_no_bounds: Bounds[LessThanComparable | None] = Bounds(lower=None, upper=None)
    assert value in bounds_no_bounds  # any value within bounds
