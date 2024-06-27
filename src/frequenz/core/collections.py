# License: MIT
# Copyright © 2022 Frequenz Energy-as-a-Service GmbH

"""Data structures that contain collections of values or objects."""

from dataclasses import dataclass
from typing import Any, Generic, Protocol, TypeVar, cast


class Comparable(Protocol):
    """A protocol that requires the implementation of comparison methods.

    This protocol is used to ensure that types can be compared using
    the less than or equal to (`<=`) and greater than or equal to (`>=`)
    operators.
    """

    def __le__(self, other: Any, /) -> bool:
        """Return whether this instance is less than or equal to `other`."""

    def __ge__(self, other: Any, /) -> bool:
        """Return whether this instance is greater than or equal to `other`."""


ComparableOrNoneT = TypeVar("ComparableOrNoneT", bound=Comparable | None)
"""Type variable for values that are comparable or `None`."""


@dataclass(frozen=True)
class Bounds(Generic[ComparableOrNoneT]):
    """Lower and upper bound values."""

    lower: ComparableOrNoneT
    """Lower bound."""

    upper: ComparableOrNoneT
    """Upper bound."""

    def __contains__(self, item: ComparableOrNoneT) -> bool:
        """
        Check if the value is within the range of the container.

        Args:
            item: The value to check.

        Returns:
            bool: True if value is within the range, otherwise False.
        """
        if self.lower is None and self.upper is None:
            return True
        if self.lower is None:
            return item <= self.upper
        if self.upper is None:
            return self.lower <= item

        return cast(Comparable, self.lower) <= item <= cast(Comparable, self.upper)
