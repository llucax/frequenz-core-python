# License: MIT
# Copyright © 2022 Frequenz Energy-as-a-Service GmbH

"""Data structures that contain collections of values or objects."""

from dataclasses import dataclass
from typing import Generic, Protocol, Self, TypeVar, cast


class LessThanComparable(Protocol):
    """A protocol that requires the `__lt__` method to compare values."""

    def __lt__(self, other: Self, /) -> bool:
        """Return whether self is less than other."""


LessThanComparableOrNoneT = TypeVar(
    "LessThanComparableOrNoneT", bound=LessThanComparable | None
)
"""Type variable for a value that a `LessThanComparable` or `None`."""


@dataclass(frozen=True)
class Bounds(Generic[LessThanComparableOrNoneT]):
    """A range of values with lower and upper bounds.

    The bounds are inclusive, meaning that the lower and upper bounds are included in
    the range when checking if a value is within the range.

    The type stored in the bounds must be comparable, meaning that it must implement the
    `__lt__` method to be able to compare values.
    """

    lower: LessThanComparableOrNoneT
    """Lower bound."""

    upper: LessThanComparableOrNoneT
    """Upper bound."""

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

        if self.lower is None and self.upper is None:
            return True
        if self.lower is None:
            upper = cast(LessThanComparable, self.upper)
            return not casted_item > upper
        if self.upper is None:
            return not self.lower > item
        # mypy seems to get confused here, not being able to narrow upper and lower to
        # just LessThanComparable, complaining with:
        #   error: Unsupported left operand type for <= (some union)
        # But we know if they are not None, they should be LessThanComparable, and
        # actually mypy is being able to figure it out in the lines above, just not in
        # this one, so it should be safe to cast.
        return not (
            casted_item < cast(LessThanComparable, self.lower)
            or casted_item > cast(LessThanComparable, self.upper)
        )
