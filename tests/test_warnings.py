# License: MIT
# Copyright © 2026 Frequenz Energy-as-a-Service GmbH

"""Tests for the warnings module.

The scenarios compare the standard library's `catch_warnings` (which is expected to
repeat warnings, see https://github.com/python/cpython/issues/73858) with ours, and
check that ours never suppresses a warning the standard library would show.
"""

import sys
import threading
import warnings
from collections.abc import Callable, Iterator
from types import FunctionType, ModuleType
from typing import Any

import pytest

from frequenz.core import warnings as core_warnings
from frequenz.core.warnings import Action, catch_warnings

_MODULE_SOURCE = """
import warnings

# Messages include the module name so the "once" action, which deduplicates by
# message and category only, doesn't see repeated messages across tests.
DEFAULT_MESSAGE = f"warned in {__name__}"

def warn(message=DEFAULT_MESSAGE, category=UserWarning):
    warnings.warn(message, category, stacklevel=1)

def warn_then_block(block, message=DEFAULT_MESSAGE, category=UserWarning):
    warnings.warn(message, category, stacklevel=1)
    with block():
        pass

def block_then_warn(block, message=DEFAULT_MESSAGE, category=UserWarning):
    with block():
        pass
    warnings.warn(message, category, stacklevel=1)
"""

Block = Callable[[], Any]


@pytest.fixture(name="make_module")
def make_module_fixture() -> Iterator[Callable[[str], ModuleType]]:
    """Create fresh modules, each with its own (initially missing) registry."""
    created: list[str] = []

    def make(name: str) -> ModuleType:
        module = ModuleType(name)
        module.__file__ = f"<{name}>"
        # pylint: disable-next=exec-used
        exec(compile(_MODULE_SOURCE, f"<{name}>", "exec"), module.__dict__)
        sys.modules[name] = module
        created.append(name)
        return module

    yield make
    for name in created:
        sys.modules.pop(name, None)


def _run(action: Action, function: Callable[[], Any], times: int = 10) -> int:
    """Call `function` repeatedly under `action` and count the warnings shown."""
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter(action)
        for _ in range(times):
            function()
    return len(caught)


def test_interpreter_is_supported() -> None:
    """Test that the CPython internals behave as the workaround expects."""
    assert sys.implementation.name == "cpython"
    assert core_warnings._SUPPORTED  # pylint: disable=protected-access
    assert core_warnings._check_bump_counts()  # pylint: disable=protected-access


@pytest.mark.parametrize("action", ["default", "module", "once"])
def test_stdlib_repeats_warnings(
    make_module: Callable[[str], ModuleType], action: Action
) -> None:
    """Test the standard library behaviour we are working around (control)."""
    if action == "once" and isinstance(warnings.warn_explicit, FunctionType):
        pytest.skip("The pure Python implementation doesn't repeat 'once' warnings")
    module = make_module("control")
    assert _run(action, lambda: module.warn_then_block(warnings.catch_warnings)) == 10


@pytest.mark.parametrize("action", ["default", "module", "once"])
def test_warning_before_block_is_shown_once(
    make_module: Callable[[str], ModuleType], action: Action
) -> None:
    """Test that a block after a warning doesn't make it repeat."""
    module = make_module("same_site")
    assert _run(action, lambda: module.warn_then_block(catch_warnings)) == 1


def test_warning_after_block_is_shown_once(
    make_module: Callable[[str], ModuleType],
) -> None:
    """Test that a block before a warning doesn't make it repeat."""
    module = make_module("block_first")
    assert _run("default", lambda: module.block_then_warn(catch_warnings)) == 1


def test_other_module_history_is_preserved(
    make_module: Callable[[str], ModuleType],
) -> None:
    """Test that a block in one module preserves the history of another one."""
    warner = make_module("warner")
    blocker = make_module("blocker")

    def step() -> None:
        warner.warn("from warner")
        blocker.block_then_warn(catch_warnings, "from blocker")

    assert _run("default", step) == 2


@pytest.mark.parametrize("action, expected", [("always", 10), ("ignore", 0)])
def test_always_and_ignore_are_unchanged(
    make_module: Callable[[str], ModuleType], action: Action, expected: int
) -> None:
    """Test that actions not using the registry behave as usual."""
    module = make_module(f"unchanged_{action}")
    assert _run(action, lambda: module.warn_then_block(catch_warnings)) == expected


def test_error_action_keeps_raising(
    make_module: Callable[[str], ModuleType],
) -> None:
    """Test that a warning turned into an error keeps raising after blocks."""
    module = make_module("error")
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        for _ in range(3):
            with pytest.raises(UserWarning):
                module.warn_then_block(catch_warnings)


@pytest.mark.parametrize("action", ["error", "always"])
def test_filter_change_outside_block_is_honoured(
    make_module: Callable[[str], ModuleType], action: Action
) -> None:
    """Test that a history invalidated before the block is not revived.

    A warning is shown, then the filters are changed outside any block (the registry
    is stale but not yet cleared), then a block is entered and left: the new filter
    must apply, the block must not re-validate the stale history.
    """
    module = make_module(f"stale_{action}")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("default")
        module.warn()
        warnings.simplefilter(action)
        with catch_warnings():
            pass
        if action == "error":
            with pytest.raises(UserWarning):
                module.warn()
        else:
            module.warn()
            module.warn()
            assert len(caught) == 3


@pytest.mark.parametrize("how", ["simplefilter", "action"])
def test_history_recorded_under_other_filters_is_dropped(
    make_module: Callable[[str], ModuleType], how: str
) -> None:
    """Test that a warning shown inside under "default" still raises outside."""
    module = make_module(f"inner_{how}")
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        if how == "simplefilter":
            with catch_warnings(record=True) as inner:
                warnings.simplefilter("default")
                module.warn()
        else:
            with catch_warnings(record=True, action="default") as inner:
                module.warn()
        assert len(inner) == 1
        with pytest.raises(UserWarning):
            module.warn()


def test_ignore_by_simplefilter_inside_block(
    make_module: Callable[[str], ModuleType],
) -> None:
    """Test the documented suppression pattern, with the filter added by hand."""
    module = make_module("simplefilter_ignore")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("default")
        for _ in range(5):
            with catch_warnings():
                warnings.simplefilter("ignore")
                module.warn()
            module.warn()
    assert len(caught) == 1


def test_ignore_by_action_inside_block(
    make_module: Callable[[str], ModuleType],
) -> None:
    """Test the documented suppression pattern, with the `action` argument."""
    module = make_module("action_ignore")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("default")
        for _ in range(5):
            with catch_warnings(record=True, action="ignore") as inner:
                module.warn("inside")
            module.warn("outside")
            assert not inner
    assert len(caught) == 1


def test_unrelated_warning_inside_ignore_block_is_shown_once(
    make_module: Callable[[str], ModuleType],
) -> None:
    """Test that history recorded inside a block adding only ignores is kept."""
    module = make_module("unrelated")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("default")
        for _ in range(5):
            with catch_warnings(action="ignore", category=DeprecationWarning):
                module.warn("deprecated", DeprecationWarning)
                module.warn("unrelated", RuntimeWarning)
            module.warn("outside")
    assert [str(w.message) for w in caught] == ["unrelated", "outside"]


def test_nested_blocks_compose(make_module: Callable[[str], ModuleType]) -> None:
    """Test that an inner block preserving its history lets the outer do it too."""
    module = make_module("nested")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("default")
        for _ in range(5):
            with catch_warnings():
                with catch_warnings(action="ignore", category=DeprecationWarning):
                    module.warn("deprecated", DeprecationWarning)
                module.warn("middle")
            module.warn("outside")
    assert [str(w.message) for w in caught] == ["middle", "outside"]


def test_nested_block_changing_filters_drops_inner_history_only(
    make_module: Callable[[str], ModuleType],
) -> None:
    """Test that an inner block changing filters by hand behaves like stdlib.

    The outer block can't tell what "middle" was shown under, so it repeats like it
    does with the standard library, but the history from before the outer block is
    still preserved.
    """
    module = make_module("nested_manual")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("default")
        for _ in range(5):
            with catch_warnings():
                with catch_warnings():
                    warnings.simplefilter("ignore")
                    module.warn("ignored")
                module.warn("middle")
            module.warn("outside")
    messages = [str(w.message) for w in caught]
    assert messages.count("middle") == 5
    assert messages.count("outside") == 1
    assert messages.count("ignored") == 0


def test_exception_inside_block(make_module: Callable[[str], ModuleType]) -> None:
    """Test that exceptions propagate and the history is still preserved."""
    module = make_module("exception")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("default")
        for _ in range(5):
            with pytest.raises(KeyError):
                with catch_warnings():
                    raise KeyError("boom")
            module.warn()
    assert len(caught) == 1


def test_module_first_warning_inside_block(
    make_module: Callable[[str], ModuleType],
) -> None:
    """Test a module whose registry is created inside a block."""
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("default")
        for i in range(5):
            with catch_warnings():
                if i == 0:
                    module = make_module("late")
                module.warn("inside")
            module.warn("outside")
    assert [str(w.message) for w in caught] == ["inside", "outside"]


def test_categories_and_messages_are_independent(
    make_module: Callable[[str], ModuleType],
) -> None:
    """Test that distinct warnings are each shown once."""
    module = make_module("categories")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("default")
        for _ in range(3):
            with catch_warnings():
                pass
            module.warn("a", DeprecationWarning)
            module.warn("a", RuntimeWarning)
            module.warn("b", RuntimeWarning)
    assert len(caught) == 3


def test_filters_are_restored_without_leftovers() -> None:
    """Test that the probe filter doesn't leak out of the block."""
    with warnings.catch_warnings():
        warnings.simplefilter("default")
        before = list(warnings.filters)
        with catch_warnings():
            warnings.simplefilter("ignore")
        assert list(warnings.filters) == before
        assert not any("Probe" in repr(item) for item in before)


def test_record_returns_the_log() -> None:
    """Test that the `record` argument works as in the standard library."""
    with catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        warnings.warn("recorded", UserWarning)
    assert [str(w.message) for w in caught] == ["recorded"]
    with catch_warnings() as nothing:
        pass
    assert nothing is None


def test_filter_changed_by_another_thread_is_honoured(
    make_module: Callable[[str], ModuleType],
) -> None:
    """Test that a filter change that persists after the block is not undone.

    Without context-aware warnings the standard library discards the other thread's
    change on exit, so the history is valid and the warning is deduplicated. With
    them the change persists, so the history must not be restored and the warning
    must raise. Both outcomes are checked against the standard library's own.
    """
    module = make_module("threads")
    outcomes: list[tuple[str, bool]] = []
    for block in (warnings.catch_warnings, catch_warnings):
        module.__dict__.pop("__warningregistry__", None)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("default")
            module.warn()
            with block():
                thread = threading.Thread(target=lambda: warnings.simplefilter("error"))
                thread.start()
                thread.join()
            try:
                module.warn()
                outcomes.append(("shown" if len(caught) > 1 else "deduped", False))
            except UserWarning:
                outcomes.append(("raised", True))
    assert len(outcomes) == 2
    stdlib, ours = outcomes[0], outcomes[1]
    assert ours[1] == stdlib[1], "we must raise exactly when the stdlib raises"
    if not stdlib[1]:
        assert ours[0] == "deduped"


def test_unsupported_interpreter_falls_back(
    monkeypatch: pytest.MonkeyPatch, make_module: Callable[[str], ModuleType]
) -> None:
    """Test that without support the class is a plain `catch_warnings`."""
    monkeypatch.setattr(core_warnings, "_SUPPORTED", False)
    module = make_module("fallback")
    assert _run("default", lambda: module.warn_then_block(catch_warnings)) == 10
    with catch_warnings(record=True, action="ignore") as caught:
        module.warn()
    assert not caught


def test_concurrent_blocks_do_not_crash(
    make_module: Callable[[str], ModuleType],
) -> None:
    """Test that overlapping blocks in several threads don't raise."""
    module = make_module("concurrent")
    errors: list[BaseException] = []

    def worker() -> None:
        try:
            for _ in range(200):
                with catch_warnings(action="ignore"):
                    module.warn()
        except BaseException as error:  # pylint: disable=broad-exception-caught
            errors.append(error)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        threads = [threading.Thread(target=worker) for _ in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
    assert not errors


def _live_filters() -> list[Any]:
    """Get the live filters list (not `warnings.filters` in context-aware mode)."""
    filters = core_warnings._live_filters(warnings)  # pylint: disable=W0212
    assert filters is not None
    return filters


def test_ignore_fast_path_does_not_bump_the_version(
    make_module: Callable[[str], ModuleType],
) -> None:
    """Test that an `action="ignore"` block leaves the filters version alone."""
    module = make_module("fast")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("default")
        module.warn("before")
        registry = module.__dict__["__warningregistry__"]
        stamped = registry["version"]
        with catch_warnings(action="ignore", category=DeprecationWarning) as log:
            module.warn("ignored", DeprecationWarning)
            module.warn("inside")
        assert log is None
        assert registry["version"] == stamped
        module.warn("before")
        module.warn("inside")
        module.warn("ignored", DeprecationWarning)
    assert [str(w.message) for w in caught] == ["before", "inside", "ignored"]


def test_ignore_fast_path_restores_filters_changed_by_hand(
    make_module: Callable[[str], ModuleType],
) -> None:
    """Test that filters changed inside the block are restored, as in stdlib.

    Also covers `simplefilter()` replacing our own (equal) entry with its own.
    """
    module = make_module("fast_manual")
    with warnings.catch_warnings(record=True) as caught:
        warnings.resetwarnings()
        warnings.simplefilter("default")
        before = _live_filters()[:]
        with catch_warnings(action="ignore", category=DeprecationWarning):
            warnings.simplefilter("ignore", DeprecationWarning)
            warnings.simplefilter("always", UserWarning)
            module.warn()
            module.warn()
        assert _live_filters() == before
        module.warn("dep", DeprecationWarning)
        module.warn()
        module.warn()
    assert [str(w.message) for w in caught] == [
        "warned in fast_manual",  # "always" inside, twice
        "warned in fast_manual",
        "dep",  # ignore restored away
        "warned in fast_manual",  # "default" restored, so only once
    ]


def test_ignore_fast_path_survives_nested_stdlib_block() -> None:
    """Test that a nested standard block copying the filters doesn't confuse it."""
    with warnings.catch_warnings():
        warnings.resetwarnings()
        with catch_warnings(action="ignore", category=DeprecationWarning, append=True):
            with warnings.catch_warnings():
                warnings.simplefilter("error")
            assert len(_live_filters()) == 1
        assert not _live_filters()


def test_ignore_fast_path_restores_showwarning_and_rejects_reentry() -> None:
    """Test the remaining `catch_warnings` semantics of the fast path."""
    original = warnings.showwarning
    block = catch_warnings(action="ignore")
    with block:
        warnings.showwarning = lambda *args, **kwargs: None
    assert warnings.showwarning is original
    with pytest.raises(RuntimeError, match="twice"):
        with block:
            pass


def test_ignore_fast_path_still_ignores_and_honours_outer_error(
    make_module: Callable[[str], ModuleType],
) -> None:
    """Test filtering inside and outside the fast block."""
    module = make_module("fast_error")
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        with catch_warnings(action="ignore", category=UserWarning):
            module.warn()
            with pytest.raises(DeprecationWarning):
                module.warn("still an error", DeprecationWarning)
        with pytest.raises(UserWarning):
            module.warn()
