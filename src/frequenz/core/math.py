# License: MIT
# Copyright © 2023 Frequenz Energy-as-a-Service GmbH

"""Math tools."""

import math
from dataclasses import dataclass
from typing import Generic, Protocol, Self, TypeVar

from .typing import FloatInt


def is_close_to_zero(value: FloatInt, abs_tol: FloatInt = 1e-9) -> bool:
    """Check if a floating point value is close to zero.

    A value of 1e-9 is a commonly used absolute tolerance to balance precision
    and robustness for floating-point numbers comparisons close to zero. Note
    that this is also the default value for the relative tolerance.
    For more technical details, see https://peps.python.org/pep-0485/#behavior-near-zero

    Args:
        value: The floating point value to compare to.
        abs_tol: The minimum absolute tolerance. Defaults to 1e-9.

    Returns:
        Whether the floating point value is close to zero.
    """
    zero: float = 0.0
    return math.isclose(a=value, b=zero, abs_tol=abs_tol)


class LessThanComparable(Protocol):
    """A protocol that requires the `__lt__` method to compare values."""

    def __lt__(self, other: Self, /) -> bool:
        """Return whether self is less than other."""


LessThanComparableT = TypeVar("LessThanComparableT", bound=LessThanComparable)
"""Type variable for a value that is [`LessThanComparable`][..LessThanComparable]."""


LessThanComparableOrNoneT = TypeVar(
    "LessThanComparableOrNoneT", bound=LessThanComparable | None
)
"""Type variable for a value that is [`LessThanComparable`][..LessThanComparable] or `None`.

Deprecated:
    This type variable is deprecated since v1.4.0 and it will be removed in a
    future version. Use [`LessThanComparableT`][..LessThanComparableT] instead.
"""


@dataclass(frozen=True, repr=False)
class Interval(Generic[LessThanComparableT]):
    """An interval to test if a value is within its limits.

    The [`.start`][.start] and [`.end`][.end] are inclusive, meaning that the
    [`.start`][.start] and [`.end`][.end] limits are included in the range when
    checking if a value is contained by the interval.

    If the [`.start`][.start] or [`.end`][.end] is `None`, it means that the interval
    is unbounded in that direction. `None` is used purely as a bound marker; it is
    never a value in the interval.

    If [`.start`][.start] is bigger than [`.end`][.end], a `ValueError` is raised.

    The type stored in the interval must be comparable, meaning that it must implement
    the `__lt__` method to be able to compare values.
    """

    start: LessThanComparableT | None
    """The start of the interval, or `None` to indicate no lower bound (-∞)."""

    end: LessThanComparableT | None
    """The end of the interval, or `None` to indicate no upper bound (+∞)."""

    def __post_init__(self) -> None:
        """Check if the start is less than or equal to the end."""
        if self.start is None or self.end is None:
            return
        if self.start > self.end:
            raise ValueError(
                f"The start ({self.start}) can't be bigger than end ({self.end})"
            )

    def __contains__(self, item: LessThanComparableT) -> bool:
        """Check if the value is within the range of the interval.

        Args:
            item: The value to check.

        Returns:
            True if value is within the range, otherwise False.
        """
        if self.start is not None and item < self.start:
            return False
        if self.end is not None and item > self.end:
            return False
        return True

    def __repr__(self) -> str:
        """Return a string representation of this instance."""
        return f"Interval({self.start!r}, {self.end!r})"

    def __str__(self) -> str:
        """Return a string representation of this instance."""
        start = "∞" if self.start is None else str(self.start)
        end = "∞" if self.end is None else str(self.end)
        return f"[{start}, {end}]"
