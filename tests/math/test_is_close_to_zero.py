# License: MIT
# Copyright © 2024 Frequenz Energy-as-a-Service GmbH

"""Tests for the math module."""

from hypothesis import given
from hypothesis import strategies as st

from frequenz.core.math import is_close_to_zero

# We first do some regular test cases to avoid mistakes using hypothesis and having
# basic cases not working.


def test_default_tolerance() -> None:
    """Test the is_close_to_zero function with the default tolerance."""
    assert is_close_to_zero(0.0)
    assert is_close_to_zero(1e-10)
    assert not is_close_to_zero(1e-8)


def test_custom_tolerance() -> None:
    """Test the is_close_to_zero function with a custom tolerance."""
    assert is_close_to_zero(0.0, abs_tol=1e-8)
    assert is_close_to_zero(1e-8, abs_tol=1e-8)
    assert not is_close_to_zero(1e-7, abs_tol=1e-8)


def test_negative_values() -> None:
    """Test the is_close_to_zero function with negative values."""
    assert is_close_to_zero(-1e-10)
    assert not is_close_to_zero(-1e-8)


@given(st.floats(allow_nan=False, allow_infinity=False))
def test_default_tolerance_hypothesis(value: float) -> None:
    """Test the is_close_to_zero function with the default tolerance for many values."""
    if -1e-9 <= value <= 1e-9:
        assert is_close_to_zero(value)
    else:
        assert not is_close_to_zero(value)


@given(
    st.floats(allow_nan=False, allow_infinity=False),
    st.floats(allow_nan=False, allow_infinity=False, min_value=0.0, max_value=2.0),
)
def test_custom_tolerance_hypothesis(value: float, abs_tol: float) -> None:
    """Test the is_close_to_zero function with a custom tolerance with many values/tolerance."""
    if -abs_tol <= value <= abs_tol:
        assert is_close_to_zero(value, abs_tol=abs_tol)
    else:
        assert not is_close_to_zero(value, abs_tol=abs_tol)
