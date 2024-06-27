# License: MIT
# Copyright © 2024 Frequenz Energy-as-a-Service GmbH

"""Tests for the collections module."""


from frequenz.core.collections import Bounds


def test_bounds_contains() -> None:
    """Tests with complete bounds."""
    bounds = Bounds(lower=10.0, upper=100.0)
    assert 50.0 in bounds  # within
    assert 10.0 in bounds  # at lower
    assert 100.0 in bounds  # at upper
    assert 9.0 not in bounds  # below lower
    assert 101.0 not in bounds  # above upper


def test_bounds_contains_no_lower() -> None:
    """Tests without lower bound."""
    bounds_no_lower = Bounds(lower=None, upper=100.0)
    assert 50.0 in bounds_no_lower  # within upper
    assert 100.0 in bounds_no_lower  # at upper
    assert 101.0 not in bounds_no_lower  # above upper


def test_bounds_contains_no_upper() -> None:
    """Tests without upper bound."""
    bounds_no_upper = Bounds(lower=10.0, upper=None)
    assert 50.0 in bounds_no_upper  # within lower
    assert 10.0 in bounds_no_upper  # at lower
    assert 9.0 not in bounds_no_upper  # below lower


def test_bounds_contains_no_bounds() -> None:
    """Tests with no bounds."""
    bounds_no_bounds: Bounds[float | None] = Bounds(lower=None, upper=None)
    assert 50.0 in bounds_no_bounds  # any value within bounds
