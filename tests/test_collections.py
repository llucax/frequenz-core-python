# License: MIT
# Copyright © 2024 Frequenz Energy-as-a-Service GmbH

"""Tests for the collections module."""


from datetime import datetime

from frequenz.sdk.timeseries._base_types import Bounds, SystemBounds
from frequenz.sdk.timeseries._quantities import Power


def test_bounds_contains() -> None:
    """Tests with complete bounds."""
    bounds = Bounds(lower=Power.from_watts(10), upper=Power.from_watts(100))
    assert Power.from_watts(50) in bounds  # within
    assert Power.from_watts(10) in bounds  # at lower
    assert Power.from_watts(100) in bounds  # at upper
    assert Power.from_watts(9) not in bounds  # below lower
    assert Power.from_watts(101) not in bounds  # above upper


def test_bounds_contains_no_lower() -> None:
    """Tests without lower bound."""
    bounds_no_lower = Bounds(lower=None, upper=Power.from_watts(100))
    assert Power.from_watts(50) in bounds_no_lower  # within upper
    assert Power.from_watts(100) in bounds_no_lower  # at upper
    assert Power.from_watts(101) not in bounds_no_lower  # above upper


def test_bounds_contains_no_upper() -> None:
    """Tests without upper bound."""
    bounds_no_upper = Bounds(lower=Power.from_watts(10), upper=None)
    assert Power.from_watts(50) in bounds_no_upper  # within lower
    assert Power.from_watts(10) in bounds_no_upper  # at lower
    assert Power.from_watts(9) not in bounds_no_upper  # below lower


def test_bounds_contains_no_bounds() -> None:
    """Tests with no bounds."""
    bounds_no_bounds: Bounds[Power | None] = Bounds(lower=None, upper=None)
    assert Power.from_watts(50) in bounds_no_bounds  # any value within bounds
