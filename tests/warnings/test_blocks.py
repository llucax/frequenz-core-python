# License: MIT
# Copyright © 2026 Frequenz Energy-as-a-Service GmbH

"""Tests for what every context manager in this package has in common."""

from collections.abc import Callable
from typing import Any

import pytest

from frequenz.core.warnings import (
    asserting_no_deprecations,
    asserting_no_warnings,
    ignoring_deprecations,
    ignoring_warnings,
)


@pytest.mark.parametrize(
    "block",
    [
        ignoring_warnings,
        ignoring_deprecations,
        asserting_no_warnings,
        asserting_no_deprecations,
    ],
)
def test_blocks_are_not_decorators(block: Callable[[], Any]) -> None:
    """Test that none of these can be used as a decorator.

    Decorating would cover a whole function body, and for an `async` one it would
    cover building the coroutine and nothing else, so an ignore would silence
    nothing and an assertion could never fail. These are plain context manager
    classes, so Python refuses on its own.
    """

    def convert(value: int) -> int:
        return value * 2

    with pytest.raises(TypeError, match="not callable"):
        block()(convert)
    # Without the call it would be the class itself doing the decorating, which its
    # keyword-only arguments refuse.
    with pytest.raises(TypeError):
        block(convert)  # type: ignore[call-arg]


@pytest.mark.parametrize(
    "block",
    [
        ignoring_warnings,
        ignoring_deprecations,
        asserting_no_warnings,
        asserting_no_deprecations,
    ],
)
def test_blocks_reject_reentry(block: Callable[[], Any]) -> None:
    """Test that entering the same instance again is refused, and reusing it is not.

    Nesting one instance in itself would install its state twice and take it out
    once, so it is refused before anything is touched. That only happens to an
    instance kept in a variable, since a `with` statement makes a new one each time.
    """
    instance = block()
    with instance:
        with pytest.raises(RuntimeError, match="Cannot enter .* twice"):
            with instance:
                pass
    with instance:  # Left, so it can be entered again.
        pass
