# License: MIT
# Copyright © 2023 Frequenz Energy-as-a-Service GmbH

"""Math tools."""

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


LessThanComparableOrNoneT = TypeVar(
    "LessThanComparableOrNoneT", bound=LessThanComparable | None
)
"""Type variable for a value that a `LessThanComparable` or `None`."""


@dataclass(frozen=True, repr=False)
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

    def __repr__(self) -> str:
        """Return a string representation of this instance."""
        return f"Interval({self.start!r}, {self.end!r})"

    def __str__(self) -> str:
        """Return a string representation of this instance."""
        start = "∞" if self.start is None else str(self.start)
        end = "∞" if self.end is None else str(self.end)
        return f"[{start}, {end}]"


class Bounds(Generic[LessThanComparableOrNoneT]):
    """A set of allowed intervals to check if a value is within any of them.

    Bounds are used to check if a value is within the limits of some allowed intervals.
    Like [`Interval`][frequenz.core.collections.Interval], the limits of the intervals
    are inclusive, and if open intervals are allowed, they can be represented by using
    `None` as the limit.

    Example:
        Given the following bounds representation:

        ```
               -2       0       2       4       6   7   8   9    ...
        <-------[ALLOWED]---------------[ALLOWED]---[ALLOWED------->
        ```

        The value `-2`, `-1.9999`, `-0.5`, `0`, `4`, `5, `6`, `7`, `8`, `9` and `1090349.0349` all
        all within the bounds, but `-3`, `-2.001`, `0.1`, `1`, `2`, `3`, `6.01` and
        `6.9999` are not.

        These bounds can be represented by the following code:

        ```python
        from frequenz.core.collections import Bounds, Interval

        bounds: Bounds[float | None] = Bounds(
            Interval(-2.0, 0.0), Interval(4.0, 6.0), Interval(7.0, None)
        )
        for value in [-2.0, -1.9999, -0.5, 0.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 1090349.0349]:
            assert value in bounds
        for value in [-3.0, -2.001, 0.1, 1.0, 2.0, 3.0, 6.01, 6.9999]:
            assert value not in bounds
        ```
    """

    @overload
    def __init__(  # noqa: DOC502 (Raises without a raise statement)
        self,
        *,
        lower: LessThanComparableOrNoneT | None = None,
        upper: LessThanComparableOrNoneT | None = None,
    ) -> None:
        """Initialize this instance providing an `upper` and `lower` bound.

        Args:
            lower: The lower bound.
            upper: The upper bound.

        Raises:
            ValueError: If both `upper` and `lower` are `None` or if `lower` is bigger
                than the `upper`.
        """

    @overload
    def __init__(  # noqa: DOC502 (Raises without a raise statement)
        self,
        *intervals: Interval[LessThanComparableOrNoneT],
    ) -> None:
        """Initialize this instance providing a set of `intervals`.

        Args:
            *intervals: The set of intervals.

        Raises:
            ValueError: If no intervals are provided.
        """

    def __init__(
        self,
        *intervals: Interval[LessThanComparableOrNoneT],
        lower: LessThanComparableOrNoneT | None = None,
        upper: LessThanComparableOrNoneT | None = None,
    ) -> None:
        """Initialize this instance providing an `upper` and `lower` bound or a set of `intervals`.

        Either a set of `intervals` or an `upper` and `lower` bound must be provided,
        but not both. If `upper` and `lower` are provided, a unique interval with those
        bounds is used.

        Args:
            *intervals: The set of intervals.
            lower: The lower bound.
            upper: The upper bound.

        Raises:
            ValueError: If no intervals are provided, or if both `upper` and `lower` are
                `None`, or if `lower` is bigger than the `upper`.
        """
        if not intervals and lower is None and upper is None:
            raise ValueError("At least one interval or bound must be provided")
        casted_lower = cast(LessThanComparableOrNoneT, lower)
        casted_upper = cast(LessThanComparableOrNoneT, upper)
        self._intervals: frozenset[Interval[LessThanComparableOrNoneT]] = frozenset(
            intervals or [Interval(casted_lower, casted_upper)]
        )

    def __contains__(self, item: LessThanComparableOrNoneT) -> bool:
        """Check if `item` is within the bounds of this instance.

        Args:
            item: The value to check.

        Returns:
            bool: Whether `item` is within the bounds.
        """
        for interval in self._intervals:
            if item in interval:
                return True
        return False
