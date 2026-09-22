# License: MIT
# Copyright © 2026 Frequenz Energy-as-a-Service GmbH

"""Asserting in a test that a piece of code doesn't warn.

See the package documentation for the background.
"""

import contextlib
import re
import warnings
from types import TracebackType


def _replay(warning: warnings.WarningMessage) -> None:
    """Show a recorded warning, as it would have been shown without the recording.

    The filters are not consulted again: this warning already passed them, and
    `record=True` is the only reason it wasn't shown.

    Args:
        warning: The recorded warning.
    """
    # `_showwarnmsg()` is what the warnings machinery itself calls to show a warning,
    # with the whole message: it hands it to `warnings.showwarning` if the application
    # replaced that (`logging.captureWarnings()` does), and otherwise to the default
    # implementation, which is also what `catch_warnings(record=True)` replaces to
    # record instead of showing. Calling the public `showwarning()` here would be
    # wrong both ways around: it has no `source` argument, so a `ResourceWarning`
    # would lose the object it points at, and calling the default implementation
    # directly would skip whatever the application installed.
    show_message = getattr(warnings, "_showwarnmsg", None)
    if show_message is not None:
        show_message(warning)
        return
    warnings.showwarning(
        warning.message,
        warning.category,
        warning.filename,
        warning.lineno,
        warning.file,
        warning.line,
    )


# A lowercase name, like `warnings.catch_warnings`, because this is read as the
# statement it is used in and never as a type worth naming.
# pylint: disable-next=invalid-name
class asserting_no_warnings(contextlib.AbstractContextManager[None]):
    """A context manager that fails if a matching warning is raised inside its block.

    Use this to test that a call doesn't warn. The usual alternative, an
    `"error"` filter, makes [`warnings.warn`][] raise an exception **inside** the
    code under test. A broad `except` in that code can then swallow it or turn
    it into an unrelated failure, and the code no longer behaves as it would in
    production. This block records warnings instead and leaves the code alone.
    When the block ends, it raises [`AssertionError`][] listing every
    unexpected warning and where it came from.

    Warnings that don't cause a failure are still shown as usual when the block
    ends. The unexpected ones are shown too if the block is left because of an
    exception. In that case the exception is raised instead of the
    [`AssertionError`][], since it's the bigger problem, but the warnings aren't
    lost.

    Warning: Resets the warnings deduplication history
        Recording needs [`warnings.catch_warnings`][], and using it resets that
        history for the whole program. There's no way around it here: a warning
        that was already shown is skipped (by the module's
        `__warningregistry__`) before the filters are even checked, so the only
        way to catch it again is to reset the history.

        In tests this is usually fine, since they are isolated. Anywhere else,
        every warning shown before the block will be shown again after it. So
        use this in a short test that checks just this, not in a hot path, a
        long-running process, or around a whole test suite.

    Warning: Concurrency
        [`warnings.catch_warnings`][] affects the whole process unless
        `sys.flags.context_aware_warnings` is on. That flag was added in Python
        3.14 and is off by default, except in free-threaded builds. Without it,
        a matching warning from another thread, or from another asyncio task
        while the block is waiting on an `await`, is recorded here and fails the
        block, even if the code under test never warned. Use it only around
        synchronous code, and not where background threads can raise matching
        warnings.

        With the flag on, the problem is smaller but not gone. New threads start
        with an empty context, so their warnings aren't recorded. Tasks created
        inside the block, however, inherit its recording and can still fail it.

    Warning: An `ignoring_warnings` block inside wins
        [`ignoring_warnings`][..ignoring_warnings] puts its filter in front of
        the one this block adds. So if the code under test ignores a warning
        itself, that warning is never recorded and can't fail the block. This is
        intended, since the code explicitly asked to ignore it. It does mean
        that an [`asserting_no_deprecations`][..asserting_no_deprecations] block
        around code using [`ignoring_deprecations`][..ignoring_deprecations]
        internally only checks the deprecations the code didn't silence, not all
        of them.

    Warning: Handlers installed inside the block
        While the block is active, it controls how warnings are shown. Handlers
        installed *before* the block, like the one [`logging.captureWarnings`][]
        sets up, keep working: once the block ends, they receive the warnings
        that didn't fail it. But if the code **under test** replaces
        [`warnings.showwarning`][] itself, any warning raised after that goes
        straight to its own handler, and this block can't see it or fail on it.
        A plain `catch_warnings(record=True)` has the same limitation.

    Warning: Not reentrant
        Entering an instance that is already inside its block raises
        [`RuntimeError`][].

    Example:
        ```python
        import warnings

        from frequenz.core.warnings import asserting_no_warnings


        def convert(value: str) -> int:
            return int(value)


        with asserting_no_warnings(category=DeprecationWarning):
            assert convert("1") == 1
        ```
    """

    def __init__(  # noqa: DOC503
        self, *, category: type[Warning] = Warning, message: str = ""
    ) -> None:
        """Initialize this instance.

        Args:
            category: The category of warnings to reject, including its subclasses.
            message: A regular expression the start of the warning message must
                match, case insensitively. The default matches every message.

        Raises:
            TypeError: If any argument has the wrong type.
            re.error: If `message` is not a valid regular expression.
        """
        if not (isinstance(category, type) and issubclass(category, Warning)):
            raise TypeError(f"category must be a Warning subclass, got {category!r}")
        if not isinstance(message, str):
            raise TypeError(f"message must be a str, got {message!r}")
        self._category = category
        self._message = message
        self._pattern = re.compile(message, re.IGNORECASE) if message else None
        self._entered = False
        self._stack: contextlib.ExitStack | None = None
        self._caught: list[warnings.WarningMessage] = []

    def _matches(self, warning: warnings.WarningMessage) -> bool:
        """Tell whether a recorded warning is one this block rejects.

        Args:
            warning: The recorded warning.

        Returns:
            Whether it matches.
        """
        # There is no `module` argument next to `category` and `message`, even
        # though `ignoring_warnings` has one and the "always" filter added in
        # `__enter__()` would take it, and it can't be added here as it stands.
        # A recorded `WarningMessage` carries `filename` and not the module
        # name the filter matched, and those are different strings (`mymod`
        # against `/tmp/mymod.py`), so this function can't reproduce the
        # decision. Putting it only on the filter doesn't work either: a
        # warning from a module the argument was meant to exempt still reaches
        # this function through an ambient "default" or "always" filter, and
        # would be reported. Giving it filename semantics instead would mean
        # one name for two meanings across this module.
        if not issubclass(warning.category, self._category):
            return False
        return self._pattern is None or bool(self._pattern.match(str(warning.message)))

    def __enter__(self) -> None:
        """Enter the block, recording the warnings raised inside it.

        Raises:
            RuntimeError: If this instance is already inside its block.
        """
        if self._entered:
            raise RuntimeError(f"Cannot enter {type(self).__name__}() twice")
        self._entered = True

        self._stack = contextlib.ExitStack()
        self._caught = self._stack.enter_context(warnings.catch_warnings(record=True))

        # Recording happens in the default warnings output, so it only sees a
        # warning while that output is the one installed. `catch_warnings` resets
        # `showwarning` itself to make sure of that, but only when the filters are
        # process-wide: with context-aware warnings (Python 3.14 and later) the
        # recording lives in the context while `showwarning` stays a module global,
        # so a handler the application installed, as `logging.captureWarnings()`
        # does, keeps taking every warning, nothing is recorded, and every assertion
        # here passes. That is python/cpython#151149, so the reset is done here too,
        # in every mode. It is undone before the recording block closes, so the
        # replay on the way out still reaches the application's handler.
        default_show = getattr(warnings, "_showwarning_orig", None)
        if default_show is not None:
            self._stack.callback(setattr, warnings, "showwarning", warnings.showwarning)
            warnings.showwarning = default_show

        # "always" so a warning already shown elsewhere is still recorded here, with
        # the message too, so a warning this block doesn't reject keeps whatever the
        # surrounding filters say about it.
        warnings.filterwarnings(
            "always", message=self._message, category=self._category
        )

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Exit the block, replaying what it didn't reject and failing on the rest.

        Args:
            exc_type: The type of the exception leaving the block, if any.
            exc_value: The exception leaving the block, if any.
            traceback: The traceback of that exception, if any.

        Raises:
            AssertionError: If a matching warning was raised inside the block and no
                exception is on its way out, which is the more important news.
        """
        self._entered = False
        stack, self._stack = self._stack, None
        caught, self._caught = self._caught, []
        if stack is not None:
            stack.close()

        # An exception is the more important news, so the assertion stands down and
        # the warnings it would have reported are shown instead of being reported.
        # Dropping them here would lose them entirely, which is the one thing the
        # replay below exists to prevent.
        failing = exc_type is None

        # One pass, rather than a list of offenders and a membership test per
        # warning: the filter added inside is an "always" one, so a regression in a
        # loop can easily leave tens of thousands of warnings here, and the failure
        # path is the last place to spend quadratic time.
        unexpected: list[warnings.WarningMessage] = []
        for warning in caught:
            if failing and self._matches(warning):
                unexpected.append(warning)
            else:
                _replay(warning)

        if unexpected:
            listing = "\n".join(
                f"  {warning.category.__name__}: {warning.message} "
                f"({warning.filename}:{warning.lineno})"
                for warning in unexpected
            )
            raise AssertionError(f"Unexpected warnings raised:\n{listing}")


def asserting_no_deprecations(  # noqa: DOC502
    *, message: str = ""
) -> asserting_no_warnings:
    """Fail if a deprecation warning is raised inside the block.

    This is [`asserting_no_warnings`][..asserting_no_warnings] for the usual case,
    checking that the replacement for a deprecated symbol doesn't itself go through
    the deprecated one.

    Warning: All limitations of `asserting_no_warnings()` apply
        Read the documentation of [`asserting_no_warnings`][..asserting_no_warnings],
        many limitations apply here too, as this is only a thin wrapper around it.

    Pass `message` when the code under test legitimately deprecates something else,
    or reaches a third-party deprecation there is nothing to be done about: the block
    wraps the code being tested, so unlike an
    [`ignoring_deprecations`][..ignoring_deprecations] block it can't be narrowed by
    making it shorter.

    Example:
        ```python
        import warnings

        from frequenz.core.warnings import asserting_no_deprecations


        def convert(value: str) -> int:
            return int(value)


        with asserting_no_deprecations(message="Wrapper is deprecated"):
            assert convert("1") == 1
        ```

    Args:
        message: A regular expression the start of the warning message must match,
            case insensitively. The default rejects every deprecation.

    Returns:
        A context manager that fails if a deprecation warning is raised in it.

    Raises:
        TypeError: If `message` has the wrong type.
        re.error: If `message` is not a valid regular expression.
    """
    return asserting_no_warnings(category=DeprecationWarning, message=message)
