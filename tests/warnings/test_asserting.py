# License: MIT
# Copyright © 2026 Frequenz Energy-as-a-Service GmbH

"""Tests for `asserting_no_warnings()` and `asserting_no_deprecations()`."""

import contextlib
import logging
import re
import subprocess
import sys
import threading
import warnings
from collections.abc import Iterator
from typing import Any

import pytest

from frequenz.core.warnings import (
    _asserting,
    asserting_no_deprecations,
    asserting_no_warnings,
    ignoring_deprecations,
)


@contextlib.contextmanager
def _shown() -> Iterator[None]:
    """Show every warning, since this suite otherwise turns them into errors."""
    with warnings.catch_warnings(action="always"):
        yield


def test_asserting_no_warnings_passes_when_quiet() -> None:
    """Test that a block raising no matching warning is fine."""
    with _shown():
        with asserting_no_warnings(category=DeprecationWarning):
            warnings.warn("not a deprecation", UserWarning, stacklevel=1)


def test_asserting_no_warnings_reports_every_offender() -> None:
    """Test that the failure names each warning and where it came from."""
    with _shown():
        with pytest.raises(AssertionError) as failure:
            with asserting_no_warnings(category=DeprecationWarning):
                warnings.warn("first", DeprecationWarning, stacklevel=1)
                warnings.warn("second", FutureWarning, stacklevel=1)
    text = str(failure.value)
    assert "DeprecationWarning: first" in text
    assert "second" not in text
    assert f"({__file__}:" in text


def test_asserting_no_warnings_matches_the_message() -> None:
    """Test that only the warnings matching the message are rejected."""
    with _shown():
        with asserting_no_warnings(category=UserWarning, message="only this one"):
            warnings.warn("something else", UserWarning, stacklevel=1)
        with pytest.raises(AssertionError, match="only this one, really"):
            with asserting_no_warnings(category=UserWarning, message="only this one"):
                warnings.warn("only this one, really", UserWarning, stacklevel=1)


def test_asserting_no_warnings_preserves_an_ignore_filter() -> None:
    """Test that an ignored nonmatching warning stays ignored."""
    with warnings.catch_warnings(
        record=True, action="ignore", category=UserWarning
    ) as caught:
        with asserting_no_warnings(category=UserWarning, message="target"):
            warnings.warn("unrelated", UserWarning, stacklevel=1)
    assert not caught


def test_asserting_no_warnings_preserves_a_default_filter() -> None:
    """Test that a nonmatching warning keeps the ambient deduplication action."""

    def warn() -> None:
        warnings.warn("unrelated", UserWarning, stacklevel=1)

    with warnings.catch_warnings(
        record=True, action="default", category=UserWarning
    ) as caught:
        with asserting_no_warnings(category=UserWarning, message="target"):
            warn()
            warn()
    assert [str(warning.message) for warning in caught] == ["unrelated"]


def test_asserting_no_warnings_preserves_an_error_filter() -> None:
    """Test that a nonmatching warning still raises under an ambient error filter."""
    with warnings.catch_warnings(action="error", category=UserWarning):
        with pytest.raises(UserWarning, match="unrelated"):
            with asserting_no_warnings(category=UserWarning, message="target"):
                warnings.warn("unrelated", UserWarning, stacklevel=1)


def test_asserting_no_warnings_lets_other_warnings_through() -> None:
    """Test that warnings the block doesn't watch are still shown afterwards."""
    with warnings.catch_warnings(record=True, action="always") as caught:
        with asserting_no_warnings(category=DeprecationWarning):
            warnings.warn("passed along", UserWarning, stacklevel=1)
    assert [str(warning.message) for warning in caught] == ["passed along"]


def test_asserting_no_warnings_sees_already_shown_warnings() -> None:
    """Test that a warning deduplicated by the ambient filters is still caught."""
    with warnings.catch_warnings(action="default"):
        warnings.warn("said once", DeprecationWarning, stacklevel=1)
        with pytest.raises(AssertionError, match="said once"):
            with asserting_no_warnings(category=DeprecationWarning):
                warnings.warn("said once", DeprecationWarning, stacklevel=1)


def test_asserting_no_warnings_does_not_swallow_exceptions() -> None:
    """Test that an error in the block is what comes out."""
    with pytest.raises(ValueError, match="boom"):
        with asserting_no_warnings():
            warnings.warn("ignored, the error wins", UserWarning, stacklevel=1)
            raise ValueError("boom")


@pytest.mark.parametrize("kwargs", [{"category": int}, {"message": None}])
def test_asserting_no_warnings_rejects_invalid_arguments(
    kwargs: dict[str, Any],
) -> None:
    """Test that the arguments are validated."""
    with pytest.raises(TypeError):
        with asserting_no_warnings(**kwargs):
            pass


def test_asserting_no_warnings_rejects_an_invalid_pattern() -> None:
    """Test that a message that doesn't compile is reported as such."""
    with pytest.raises(re.error):
        with asserting_no_warnings(message="("):
            pass


def test_asserting_no_warnings_sees_warnings_from_other_threads() -> None:
    """Test that the recording is process-wide, and when it is not.

    This pins down the limitation the docstring warns about, so a change in how
    CPython scopes `catch_warnings` doesn't go unnoticed.
    """
    isolated = bool(getattr(sys.flags, "context_aware_warnings", 0))
    ready = threading.Event()
    done = threading.Event()

    def background() -> None:
        ready.wait()
        try:
            warnings.warn("from another thread", UserWarning, stacklevel=1)
        except UserWarning:
            pass  # An ambient "error" filter, which this test doesn't care about.
        done.set()

    thread = threading.Thread(target=background)
    thread.start()
    leaked = False
    try:
        with asserting_no_warnings(category=UserWarning):
            ready.set()
            done.wait()
    except AssertionError as error:
        leaked = "from another thread" in str(error)
    thread.join()

    assert leaked is not isolated


def test_asserting_no_warnings_replays_when_the_block_raises() -> None:
    """Test that every warning survives an exception leaving the block.

    The matching ones too: the exception wins over the assertion, but dropping
    them would leave them neither reported nor shown, so a deprecation raised
    inside a `pytest.raises()` block would disappear without a trace.
    """
    with warnings.catch_warnings(record=True, action="always") as caught:
        with pytest.raises(ValueError, match="boom"):
            with asserting_no_warnings(category=DeprecationWarning):
                warnings.warn("important diagnostic", UserWarning, stacklevel=1)
                warnings.warn("would have failed", DeprecationWarning, stacklevel=1)
                raise ValueError("boom")
    assert [str(warning.message) for warning in caught] == [
        "important diagnostic",
        "would have failed",
    ]


def test_asserting_no_warnings_replay_keeps_the_source() -> None:
    """Test that a replayed warning still points at the object it was about."""
    source = [1, 2, 3]
    with warnings.catch_warnings(record=True, action="always") as caught:
        with asserting_no_warnings(category=DeprecationWarning):
            warnings.warn("leaked", ResourceWarning, stacklevel=1, source=source)
    assert len(caught) == 1
    assert caught[0].source is source


def test_replay_without_showwarnmsg(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test the replay path taken when `warnings._showwarnmsg()` is not there.

    Every interpreter this supports has it, so nothing would notice this branch
    rotting until the one that drops it arrives. It is driven directly rather
    than through a block, because taking the name away also takes the recording
    of a `catch_warnings(record=True)` around it. What is lost on this path is
    the `source` of a `ResourceWarning`: the public `showwarning()` has no
    argument for it.
    """
    seen: list[tuple[Any, ...]] = []

    monkeypatch.delattr(warnings, "_showwarnmsg")
    monkeypatch.setattr(warnings, "showwarning", lambda *args: seen.append(args))
    recorded = warnings.WarningMessage(
        "leaked", ResourceWarning, "somewhere.py", 42, source=[1, 2, 3]
    )

    _asserting._replay(recorded)  # pylint: disable=protected-access

    # Six arguments, and none of them is the source.
    assert seen == [("leaked", ResourceWarning, "somewhere.py", 42, None, None)]


def test_asserting_no_warnings_yields_to_an_inner_ignore() -> None:
    """Test that a warning the code under test silences for itself doesn't fail.

    `ignoring_warnings` adds its filter in front of the one installed here, so the
    warning is never recorded. That is the intended reading, but it also means an
    assertion around code that ignores its own deprecations is about what is left.
    """
    with _shown():
        with asserting_no_deprecations():
            with ignoring_deprecations():
                warnings.warn("silenced on purpose", DeprecationWarning, stacklevel=1)


def test_asserting_no_warnings_replay_honours_a_custom_showwarning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that a replayed warning goes through a replaced `showwarning()`."""
    seen: list[str] = []

    # The rest of the arguments a `showwarning()` gets are the category, the file
    # name, the line number, the file and the line, and this one only needs to be
    # told it was called.
    def show(message: Warning | str, *_: Any) -> None:
        seen.append(str(message))

    with _shown():
        monkeypatch.setattr(warnings, "showwarning", show)
        with asserting_no_warnings(category=DeprecationWarning):
            warnings.warn("passed along", UserWarning, stacklevel=1)
    assert seen == ["passed along"]


def test_asserting_no_warnings_replay_reaches_the_logs(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test that a replayed warning still lands in the logs.

    `logging.captureWarnings()` is how an application usually ends up with a
    replaced `showwarning()`, and losing a warning from the logs is the damage.
    """
    with _shown():
        logging.captureWarnings(True)
        try:
            with asserting_no_warnings(category=DeprecationWarning):
                warnings.warn("passed along", UserWarning, stacklevel=1)
        finally:
            logging.captureWarnings(False)
    assert "passed along" in caplog.text


def test_asserting_no_warnings_fails_with_a_replaced_showwarning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that a matching warning fails the block when `showwarning()` is replaced.

    The recording only sees a warning while the default warnings output is the one
    installed, so a handler taking it first would leave nothing to fail on.
    """
    seen: list[str] = []

    def show(message: Warning | str, *_: Any) -> None:
        seen.append(str(message))

    with _shown():
        monkeypatch.setattr(warnings, "showwarning", show)
        with pytest.raises(AssertionError, match="must fail"):
            with asserting_no_warnings(category=UserWarning):
                warnings.warn("must fail", UserWarning, stacklevel=1)
        assert not seen
        # The handler is back afterwards, and the block didn't show what it rejected.
        warnings.warn("after the block", UserWarning, stacklevel=1)
    assert seen == ["after the block"]


def test_asserting_no_warnings_fails_under_logging_capture(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test that a matching warning fails the block while the logs capture warnings."""
    with _shown():
        logging.captureWarnings(True)
        try:
            with pytest.raises(AssertionError, match="must fail"):
                with asserting_no_warnings(category=UserWarning):
                    warnings.warn("must fail", UserWarning, stacklevel=1)
        finally:
            logging.captureWarnings(False)
    assert "must fail" not in caplog.text


_CONTEXT_AWARE_SCRIPT = """
import logging
import warnings

from frequenz.core.warnings import asserting_no_warnings

logged = []


class Collect(logging.Handler):
    def emit(self, record):
        logged.append(record.getMessage())


logging.getLogger("py.warnings").addHandler(Collect())
warnings.simplefilter("always")
logging.captureWarnings(True)

try:
    with asserting_no_warnings(category=UserWarning):
        warnings.warn("must fail", UserWarning, stacklevel=1)
except AssertionError:
    pass
else:
    raise SystemExit("the block passed, so the warning was never recorded")

if logged:
    raise SystemExit(f"the rejected warning was shown anyway: {logged}")

warnings.warn("after the block", UserWarning, stacklevel=1)
if len(logged) != 1 or "after the block" not in logged[0]:
    raise SystemExit(f"the logging capture was not restored: {logged}")

print("the assertion fired and the logs are back")
"""


@pytest.mark.skipif(
    sys.version_info < (3, 14), reason="context-aware warnings need Python 3.14"
)
def test_asserting_no_warnings_fails_with_context_aware_warnings() -> None:
    """Test that the assertion holds with context-aware warnings enabled too.

    That mode can only be asked for at interpreter startup, and it is the one where
    the recording used to see nothing at all once `showwarning()` was replaced, and
    the only one where restoring the handler afterwards is this block's job, so it
    runs a subprocess instead of leaving the case untested.
    """
    result = subprocess.run(
        [
            sys.executable,
            "-X",
            "context_aware_warnings=1",
            "-c",
            _CONTEXT_AWARE_SCRIPT,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "the assertion fired" in result.stdout


def test_asserting_no_warnings_reports_and_replays_in_order() -> None:
    """Test that every offender is reported and every bystander replayed, in order.

    The two are told apart in one pass, so the order of both has to survive it.
    """
    with warnings.catch_warnings(record=True, action="always") as caught:
        with pytest.raises(AssertionError) as failure:
            with asserting_no_warnings(category=DeprecationWarning):
                warnings.warn("bystander 1", UserWarning, stacklevel=1)
                warnings.warn("offender 1", DeprecationWarning, stacklevel=1)
                warnings.warn("bystander 2", UserWarning, stacklevel=1)
                warnings.warn("offender 2", DeprecationWarning, stacklevel=1)

    assert [str(warning.message) for warning in caught] == [
        "bystander 1",
        "bystander 2",
    ]
    listing = str(failure.value)
    assert listing.index("offender 1") < listing.index("offender 2")


def test_asserting_no_warnings_reentry_keeps_what_was_caught() -> None:
    """Test that a refused nested entry loses neither a warning nor the cleanup.

    Entering twice would replace the recording and the cleanup of the outer block,
    so the warnings raised before it would be dropped, the assertion would pass, and
    the recorder would still be installed afterwards.
    """
    with warnings.catch_warnings(record=True, action="always") as caught:
        block = asserting_no_warnings(category=DeprecationWarning)
        with pytest.raises(AssertionError, match="must fail"):
            with block:
                warnings.warn("passed along", UserWarning, stacklevel=1)
                warnings.warn("must fail", DeprecationWarning, stacklevel=1)
                with pytest.raises(
                    RuntimeError, match="Cannot enter asserting_no_warnings"
                ):
                    with block:
                        pass
        warnings.warn("after the block", UserWarning, stacklevel=1)
    assert [str(warning.message) for warning in caught] == [
        "passed along",
        "after the block",
    ]


def test_asserting_no_deprecations() -> None:
    """Test the deprecation shortcut."""
    with _shown():
        with asserting_no_deprecations():
            warnings.warn("not a deprecation", UserWarning, stacklevel=1)
    with pytest.raises(AssertionError, match="gone in v3"):
        with asserting_no_deprecations():
            warnings.warn("gone in v3", DeprecationWarning, stacklevel=1)


def test_asserting_no_deprecations_matches_the_message() -> None:
    """Test that the shortcut can reject one deprecation and let others be."""
    with _shown():
        with asserting_no_deprecations(message="ours"):
            warnings.warn("somebody else's", DeprecationWarning, stacklevel=1)
        with pytest.raises(AssertionError, match="ours is deprecated"):
            with asserting_no_deprecations(message="ours"):
                warnings.warn("ours is deprecated", DeprecationWarning, stacklevel=1)
