# License: MIT
# Copyright © 2023 Frequenz Energy-as-a-Service GmbH

"""Internal math tools."""

import math
from dataclasses import dataclass
from typing import Generic, Protocol, Self, TypeVar, cast


def is_close_to_zero(value: float, abs_tol: float = 1e-9) -> bool:
    """Check if a floating point value is close to zero.

    A value of 1e-9 is a commonly used absolute tolerance to balance precision
    and robustness for floating-point numbers comparisons close to zero. Note
    that this is also the default value for the relative tolerance.
    For more technical details, see https://peps.python.org/pep-0485/#behavior-near-zero

    Args:
        value: the floating point value to compare to.
        abs_tol: the minimum absolute tolerance. Defaults to 1e-9.

    Returns:
        whether the floating point value is close to zero.
    """
    zero: float = 0.0
    return math.isclose(a=value, b=zero, abs_tol=abs_tol)


class LessThanComparable(Protocol):
    """A protocol that requires the `__lt__` method to compare values."""

    def __lt__(self, other: Self, /) -> bool:
        """Return whether self is less than other."""


LessThanComparableOrNoneT = TypeVar(
    "LessThanComparableOrNoneT", bound=LessThanComparable | None
)
"""Type variable for a value that a `LessThanComparable` or `None`."""


@dataclass(frozen=True)
class Interval(Generic[LessThanComparableOrNoneT]):
    """An interval to test if a value is within its limits.

    The `start` and `end` are inclusive, meaning that the `start` and `end` limites are
    included in the range when checking if a value is contained by the interval.

    If the `start` or `end` is `None`, it means that the interval is unbounded in that
    direction.

    If `start` is bigger than `end`, a `ValueError` is raised.

    The type stored in the interval must be comparable, meaning that it must implement
    the `__lt__` method to be able to compare values.
    """

    start: LessThanComparableOrNoneT
    """The start of the interval."""

    end: LessThanComparableOrNoneT
    """The end of the interval."""

    def __post_init__(self) -> None:
        """Check if the start is less than or equal to the end."""
        if self.start is None or self.end is None:
            return
        start = cast(LessThanComparable, self.start)
        end = cast(LessThanComparable, self.end)
        if start > end:
            raise ValueError(
                f"The start ({self.start}) can't be bigger than end ({self.end})"
            )

    def __contains__(self, item: LessThanComparableOrNoneT) -> bool:
        """
        Check if the value is within the range of the container.

        Args:
            item: The value to check.

        Returns:
            bool: True if value is within the range, otherwise False.
        """
        if item is None:
            return False
        casted_item = cast(LessThanComparable, item)

        if self.start is None and self.end is None:
            return True
        if self.start is None:
            start = cast(LessThanComparable, self.end)
            return not casted_item > start
        if self.end is None:
            return not self.start > item
        # mypy seems to get confused here, not being able to narrow start and end to
        # just LessThanComparable, complaining with:
        #   error: Unsupported left operand type for <= (some union)
        # But we know if they are not None, they should be LessThanComparable, and
        # actually mypy is being able to figure it out in the lines above, just not in
        # this one, so it should be safe to cast.
        return not (
            casted_item < cast(LessThanComparable, self.start)
            or casted_item > cast(LessThanComparable, self.end)
        )
