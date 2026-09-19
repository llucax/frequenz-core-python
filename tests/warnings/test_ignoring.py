# License: MIT
# Copyright © 2026 Frequenz Energy-as-a-Service GmbH

"""Tests for `ignoring_warnings()` and `ignoring_deprecations()`.

Several scenarios compare the standard library's `catch_warnings` (which is expected
to repeat warnings, see https://github.com/python/cpython/issues/73858) with ours, and
check that ours never suppresses a warning the standard library would show.
"""

import asyncio
import re
import warnings
from collections.abc import Callable
from types import ModuleType
from typing import Any

import pytest

from frequenz.core.warnings import _ignoring, ignoring_deprecations, ignoring_warnings


def _run(function: Callable[[], Any], times: int = 10) -> int:
    """Call `function` repeatedly under "default" and count the warnings shown."""
    with warnings.catch_warnings(record=True, action="default") as caught:
        for _ in range(times):
            function()
    return len(caught)


def test_filters_are_reachable() -> None:
    """Test that this interpreter keeps its filters where we can reach them."""
    if _ignoring._live_filters() is None:  # pylint: disable=protected-access
        pytest.skip("The filters in effect are not reachable, using the fallback")


def test_matching_warnings_are_ignored() -> None:
    """Test that the block ignores what it says and nothing else."""
    with warnings.catch_warnings(record=True, action="always") as caught:
        with ignoring_warnings(category=DeprecationWarning):
            warnings.warn("gone", DeprecationWarning, stacklevel=1)
            warnings.warn("kept", UserWarning, stacklevel=1)
        warnings.warn("also kept", DeprecationWarning, stacklevel=1)
    assert [str(warning.message) for warning in caught] == ["kept", "also kept"]


def test_message_and_module_select_the_warnings() -> None:
    """Test the message and module arguments."""
    with warnings.catch_warnings(record=True, action="always") as caught:
        with ignoring_warnings(message="this is fine"):
            warnings.warn("this is fine, actually", UserWarning, stacklevel=1)
            warnings.warn("this is not", UserWarning, stacklevel=1)
        with ignoring_warnings(module="no_such_module"):
            warnings.warn("from this module", UserWarning, stacklevel=1)
    assert [str(warning.message) for warning in caught] == [
        "this is not",
        "from this module",
    ]


def test_module_picks_the_warning_source(
    make_module: Callable[[str], ModuleType],
) -> None:
    """Test that the module argument silences the module it names, and only it.

    The case above only checks that a pattern matching nothing silences nothing,
    which a filter that never matched at all would pass too. The pattern is matched
    against the module's `__name__`, not against its file name.
    """
    selected = make_module("selected")
    other = make_module("other_module")

    with warnings.catch_warnings(record=True, action="always") as caught:
        with ignoring_warnings(module="selected"):
            selected.warn()
            other.warn()

    assert [str(warning.message) for warning in caught] == ["warned in other_module"]


def test_stdlib_repeats_warnings(make_module: Callable[[str], ModuleType]) -> None:
    """Test the standard library behaviour we are working around (control)."""
    module = make_module("control")
    block = lambda: warnings.catch_warnings(  # noqa: E731
        action="ignore", category=DeprecationWarning
    )
    # If this ever fails with a count of 1, cpython#73858 was fixed upstream: the
    # standard library block stopped repeating warnings and this whole module may
    # not be needed anymore on the versions that carry the fix.
    assert _run(lambda: module.warn_then_block(block)) == 10


def test_history_is_preserved(make_module: Callable[[str], ModuleType]) -> None:
    """Test that a block after a warning doesn't make it repeat."""
    module = make_module("preserved")
    block = lambda: ignoring_warnings(category=DeprecationWarning)  # noqa: E731
    assert _run(lambda: module.warn_then_block(block)) == 1


def test_warning_shown_inside_is_not_repeated_outside(
    make_module: Callable[[str], ModuleType],
) -> None:
    """Test that the history recorded inside the block is valid outside it."""
    module = make_module("inside")

    def step() -> None:
        with ignoring_warnings(category=DeprecationWarning):
            module.warn()

    assert _run(step) == 1


def test_outer_error_filter_is_honoured() -> None:
    """Test that a warning outside the ignored set still raises."""
    with warnings.catch_warnings(action="error"):
        with ignoring_warnings(category=UserWarning):
            warnings.warn("ignored", UserWarning, stacklevel=1)
            with pytest.raises(DeprecationWarning):
                warnings.warn("still an error", DeprecationWarning, stacklevel=1)
        with pytest.raises(UserWarning):
            warnings.warn("an error again", UserWarning, stacklevel=1)


def test_overlapping_blocks_leave_no_filter_behind() -> None:
    """Test that blocks exited out of order don't strand each other's filters.

    Two threads or two asyncio tasks can enter and leave their blocks interleaved,
    which is what this reproduces by driving the context managers by hand.
    """
    live = _ignoring._live_filters()  # pylint: disable=protected-access
    assert live is not None
    before = live[:]

    # Interleaving is the whole point here, so a `with` statement can't be used.
    # pylint: disable=unnecessary-dunder-call
    first = ignoring_warnings(category=UserWarning)
    second = ignoring_warnings(category=DeprecationWarning)
    first.__enter__()
    second.__enter__()
    first.__exit__(None, None, None)
    second.__exit__(None, None, None)

    live = _ignoring._live_filters()  # pylint: disable=protected-access
    assert live is not None
    assert live == before


def test_ignoring_warnings_reentry_leaves_the_block_working() -> None:
    """Test that a refused nested entry doesn't disturb the block it was refused in.

    Entering twice would add a second filter and take only one of them out again,
    leaving an ignore installed after the block.
    """
    with warnings.catch_warnings(record=True, action="always") as caught:
        live = _ignoring._live_filters()  # pylint: disable=protected-access
        assert live is not None
        before = live[:]

        block = ignoring_warnings(category=UserWarning)
        with block:
            with pytest.raises(RuntimeError, match="Cannot enter ignoring_warnings"):
                with block:
                    pass
            warnings.warn("still ignored", UserWarning, stacklevel=1)
        warnings.warn("shown", UserWarning, stacklevel=1)

        live = _ignoring._live_filters()  # pylint: disable=protected-access
        assert live is not None
        assert live == before
    assert [str(warning.message) for warning in caught] == ["shown"]


def test_replacing_the_filters_list_inside_strands_nothing() -> None:
    """Test that a new filters list installed inside doesn't keep our filter.

    The copy carries our entry too and is the one in effect afterwards, so removing
    it only from the list entered with would leave the ignore installed for good.
    """
    original = warnings.filters
    before = original[:]
    try:
        with warnings.catch_warnings(record=True, action="always") as caught:
            with ignoring_warnings(category=UserWarning):
                warnings.filters = list(warnings.filters)
            warnings.warn("shown", UserWarning, stacklevel=1)
        assert [str(warning.message) for warning in caught] == ["shown"]
        assert list(original) == before
    finally:
        warnings.filters = original


def test_simplefilter_inside_keeps_its_filter() -> None:
    """Test that a filter installed inside the block remains afterwards.

    It removes an *equal* entry before inserting its own, so on exit ours is not
    there anymore and the equal one belongs to the caller.
    """

    class TestWarning(Warning):
        """A warning category local to this test."""

    live = _ignoring._live_filters()  # pylint: disable=protected-access
    assert live is not None
    before = live[:]

    with ignoring_warnings(category=TestWarning):
        warnings.simplefilter("ignore", TestWarning)

    live = _ignoring._live_filters()  # pylint: disable=protected-access
    assert live is not None
    assert live == [("ignore", None, TestWarning, None, 0), *before]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"category": "DeprecationWarning"},
        {"category": int},
        {"message": None},
        {"module": 0},
    ],
)
def test_invalid_arguments_are_rejected(kwargs: dict[str, Any]) -> None:
    """Test that the checks the standard library does with asserts are done here."""
    with pytest.raises(TypeError):
        with ignoring_warnings(**kwargs):
            pass


@pytest.mark.parametrize("kwargs", [{"message": "("}, {"module": "[a-"}])
def test_invalid_patterns_are_rejected(kwargs: dict[str, Any]) -> None:
    """Test that a pattern that doesn't compile is reported as such."""
    with pytest.raises(re.error):
        with ignoring_warnings(**kwargs):
            pass


def test_exit_without_enter_does_nothing() -> None:
    """Test that exiting a block that was never entered is harmless.

    The context manager protocol doesn't allow this, but `ExitStack.push()` and
    hand-written cleanup code do, and getting a stray filter removed would be
    worse than doing nothing.
    """
    live = _ignoring._live_filters()  # pylint: disable=protected-access
    assert live is not None
    before = live[:]

    ignoring_warnings(category=UserWarning).__exit__(None, None, None)

    live = _ignoring._live_filters()  # pylint: disable=protected-access
    assert live is not None
    assert live == before


def test_fallback_still_ignores(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test the path taken when the filters in effect can't be reached."""
    monkeypatch.setattr(
        _ignoring, "_live_filters", lambda: None, raising=True  # noqa: ARG005
    )
    with warnings.catch_warnings(record=True, action="always") as caught:
        with ignoring_warnings(category=UserWarning):
            warnings.warn("gone", UserWarning, stacklevel=1)
        warnings.warn("kept", UserWarning, stacklevel=1)
    assert [str(warning.message) for warning in caught] == ["kept"]


async def test_ignoring_warnings_works_across_awaits() -> None:
    """Test that a block held across an await keeps ignoring."""
    with warnings.catch_warnings(record=True, action="always") as caught:
        with ignoring_warnings(category=UserWarning):
            warnings.warn("before await", UserWarning, stacklevel=1)
            await asyncio.sleep(0)
            warnings.warn("after await", UserWarning, stacklevel=1)
    assert not caught


async def test_ignoring_warnings_is_not_task_local() -> None:
    """Test that a block held across an await also silences other tasks.

    This pins down the scope note, which is easy to read as a promise of task
    isolation on Python 3.14. The sibling is created inside the outer
    `catch_warnings` block, and a task inherits the filters list of the task that
    started it, so in any mode the filter added here is the same one the sibling
    is matched against.
    """
    started = asyncio.Event()
    warned = asyncio.Event()

    async def sibling() -> None:
        await started.wait()
        warnings.warn("from another task", UserWarning, stacklevel=1)
        warned.set()

    with warnings.catch_warnings(record=True, action="default") as caught:
        task = asyncio.create_task(sibling())
        with ignoring_warnings(category=UserWarning):
            started.set()
            await warned.wait()
        await task

    assert not caught


def test_ignoring_deprecations_only_ignores_deprecations() -> None:
    """Test that the shortcut silences deprecations and nothing else."""
    with warnings.catch_warnings(record=True, action="always") as caught:
        with ignoring_deprecations():
            warnings.warn("gone", DeprecationWarning, stacklevel=1)
            warnings.warn("kept", UserWarning, stacklevel=1)
        warnings.warn("also kept", DeprecationWarning, stacklevel=1)
    assert [str(warning.message) for warning in caught] == ["kept", "also kept"]


def test_ignoring_deprecations_preserves_history(
    make_module: Callable[[str], ModuleType],
) -> None:
    """Test that the shortcut doesn't make already shown warnings repeat."""
    module = make_module("deprecations")

    def step() -> None:
        module.warn()
        with ignoring_deprecations():
            module.warn("internal", DeprecationWarning)

    assert _run(step) == 1


def test_ignoring_deprecations_matches_message_and_module() -> None:
    """Test that the shortcut can narrow down to one deprecation."""
    with warnings.catch_warnings(record=True, action="always") as caught:
        with ignoring_deprecations(message="ours"):
            warnings.warn("ours is deprecated", DeprecationWarning, stacklevel=1)
            warnings.warn("somebody else's", DeprecationWarning, stacklevel=1)
        with ignoring_deprecations(module="no_such_module"):
            warnings.warn("from this module", DeprecationWarning, stacklevel=1)
    assert [str(warning.message) for warning in caught] == [
        "somebody else's",
        "from this module",
    ]
