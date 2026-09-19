# License: MIT
# Copyright © 2026 Frequenz Energy-as-a-Service GmbH

"""Ignoring warnings without resetting the deduplication history.

See the package documentation for the background.
"""

import contextlib
import re
import warnings
from types import TracebackType
from typing import Any, TypeAlias

_Filter: TypeAlias = tuple[
    str, "re.Pattern[str] | None", type[Warning], "re.Pattern[str] | None", int
]
"""A warning filter, in the shape CPython keeps in its filters list."""


def _live_filters() -> list[Any] | None:
    """Return the list of warning filters in effect, the live object.

    Returns:
        The list CPython consults on each warning, honouring context-aware warnings
            when available, or `None` if it can't be found.
    """
    # On 3.14+ the filters in effect may live in a context rather than in
    # `warnings.filters`, and `_get_filters()` is what the warnings machinery itself
    # calls to find them.
    get_filters = getattr(warnings, "_get_filters", None)
    filters: Any = get_filters() if get_filters is not None else warnings.filters
    return filters if isinstance(filters, list) else None


def _build_filter(  # noqa: DOC503
    category: type[Warning], message: str, module: str
) -> _Filter:
    """Build an `"ignore"` filter entry, validating the arguments.

    [`warnings.filterwarnings`][] checks its arguments before building the same
    entry, with `assert`s up to Python 3.12 and with real exceptions from 3.13 on.
    Building the entry here bypasses both, so the equivalent checks are done here,
    always as real exceptions.

    Args:
        category: The category of warnings to ignore.
        message: A regular expression the start of the warning message must match,
            or an empty string to match any message.
        module: A regular expression the start of the module name must match, or an
            empty string to match any module.

    Returns:
        The filter entry.

    Raises:
        TypeError: If any argument has the wrong type.
        re.error: If `message` or `module` is not a valid regular expression.
    """
    if not (isinstance(category, type) and issubclass(category, Warning)):
        raise TypeError(f"category must be a Warning subclass, got {category!r}")
    if not isinstance(message, str):
        raise TypeError(f"message must be a str, got {message!r}")
    if not isinstance(module, str):
        raise TypeError(f"module must be a str, got {module!r}")
    return (
        "ignore",
        re.compile(message, re.IGNORECASE) if message else None,
        category,
        re.compile(module) if module else None,
        0,
    )


def _remove_filter(filters: list[Any], item: _Filter) -> None:
    """Take a filter entry out of a filters list again.

    Args:
        filters: The list the entry was inserted into.
        item: The entry to remove.
    """
    for index, existing in enumerate(filters):
        # By identity: somebody may have inserted an equal filter meanwhile, and that
        # one is theirs to keep.
        if existing is item:
            del filters[index]
            return


# A lowercase name, like `warnings.catch_warnings`, because this is read as the
# statement it is used in and never as a type worth naming.
# pylint: disable-next=invalid-name
class ignoring_warnings(contextlib.AbstractContextManager[None]):
    """A context manager that ignores the matching warnings raised inside its block.

    The constructor arguments select which warnings are ignored, and mean the same as
    the arguments of [`warnings.filterwarnings`][] with `action="ignore"`.

    Unlike [`warnings.catch_warnings`][], this doesn't reset the warnings
    deduplication history of the program, so warnings shown before the block are not
    shown again after it. See the module documentation for the background.

    Example:
        ```python
        import warnings

        from frequenz.core.warnings import ignoring_warnings


        # Some third-party function warns about something out of our control.
        def third_party() -> int:
            warnings.warn("this is fine, actually", RuntimeWarning, stacklevel=2)
            return 42


        def use_third_party() -> int:
            with ignoring_warnings(RuntimeWarning, message="this is fine"):
                return third_party()
        ```

    Warning: This is not a `catch_warnings` replacement
        This only adds a filter for the duration of the block, it doesn't save and
        restore the filters around it. Any change made to the filters inside the
        block, by this thread or another one, is still in effect afterwards, exactly
        as if the block wasn't there. Use [`warnings.catch_warnings`][] when the
        point is to undo filter changes.

    Warning: Scope
        The filter is added to the filters the interpreter consults, which are
        normally shared by every thread and every asyncio task, so a matching
        warning raised by unrelated code running concurrently is ignored too, for as
        long as the block lasts. Keep the block around the call that needs it, and
        prefer not to hold it across an `await`.

        Wrapping this in a [`warnings.catch_warnings`][] block only narrows that on
        Python 3.14 and newer, with `sys.flags.context_aware_warnings` on, which is
        off by default except in free-threaded builds. The outer block then gives
        the current context a filters list of its own, kept in a
        [`contextvars.ContextVar`][], so other threads, and tasks created before
        it, are no longer affected. Tasks created inside it still inherit that same
        list, so they are silenced too. Without the flag,
        [`warnings.catch_warnings`][] reaches for the same shared state and
        isolates nothing. Either way it resets the deduplication history, which is
        what this class exists to avoid.

    Warning: Not reentrant
        Entering an instance that is already inside its block raises
        [`RuntimeError`][]. A `with ignoring_warnings(...)` statement builds a new
        instance each time, so this only comes up when one instance is kept in a
        variable and entered again from inside itself, by a recursive function or a
        helper called in the block. Nesting is rejected rather than supported
        because the inner block would only ignore what the outer one already
        ignores, so there is nothing to gain from making it work; an instance can
        be entered again once it has been left.

    Warning: Not thread-safe
        Taking the filter out again is a lookup followed by a deletion, with no
        locking in between, so another thread removing a filter from the same list
        at the same time can make this delete the wrong one, dropping a filter that
        was not this block's and leaving this block's behind. Nothing guards against
        that, because a lock would cost every block to protect against something
        only a program that changes warning filters from several threads at once can
        do. If yours does, don't use this.
    """

    def __init__(  # noqa: DOC502
        self,
        category: type[Warning] = Warning,
        *,
        message: str = "",
        module: str = "",
    ) -> None:
        """Initialize this instance.

        Args:
            category: The category of warnings to ignore, including its subclasses.
            message: A regular expression the start of the warning message must
                match, case insensitively. The default matches every message.
            module: A regular expression the start of the module name must match. The
                default matches every module.

        Raises:
            TypeError: If any argument has the wrong type.
            re.error: If `message` or `module` is not a valid regular expression.
        """
        self._arguments = (category, message, module)
        self._item = _build_filter(category, message, module)
        self._entered = False
        self._filters: list[Any] | None = None
        self._fallback: contextlib.ExitStack | None = None

    def __enter__(self) -> None:
        """Enter the block, adding the filter.

        Raises:
            RuntimeError: If this instance is already inside its block.
        """
        if self._entered:
            raise RuntimeError(f"Cannot enter {type(self).__name__}() twice")
        self._entered = True

        filters = _live_filters()

        if filters is None:
            # The interpreter doesn't keep its filters where we can reach them, so
            # there is nothing to be clever about: do what the standard library
            # does, which is correct, only more expensive and with the history
            # damage.
            category, message, module = self._arguments
            self._fallback = contextlib.ExitStack()
            self._fallback.enter_context(warnings.catch_warnings())
            warnings.filterwarnings(
                "ignore", message=message, category=category, module=module
            )
            return

        # The whole point: inserting into the live list directly means the internal
        # filters version doesn't move, and it is that version moving which makes
        # CPython treat every module's `__warningregistry__` as stale
        # (cpython#73858). Adding an "ignore" filter without bumping it is sound, and
        # only for "ignore": the registry is consulted *before* the filters, and an
        # ignore can only take warnings away, never add them, so a warning recorded
        # as already shown outside the block is still correctly recorded as shown
        # inside it, and the other way around. `simplefilter()` and
        # `filterwarnings()` can't do this, they bump the version on purpose because
        # they can add warnings back.
        #
        # The list object is remembered, rather than only looked up again on exit,
        # because code inside the block can replace `warnings.filters` with another
        # list and the entry has to come out of both (see `__exit__()`). Only our own
        # entry is removed, and nothing else is restored: an entry/exit snapshot
        # would make two blocks overlapping in different threads (A enters, B enters,
        # A exits, B exits) put each other's filters back, leaving one installed
        # forever.
        self._filters = filters
        filters.insert(0, self._item)

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Exit the block, taking the filter out again.

        Args:
            exc_type: The type of the exception leaving the block, if any.
            exc_value: The exception leaving the block, if any.
            traceback: The traceback of that exception, if any.
        """
        self._entered = False
        fallback, self._fallback = self._fallback, None
        if fallback is not None:
            fallback.close()
            return
        filters, self._filters = self._filters, None
        if filters is None:
            return

        _remove_filter(filters, self._item)
        # Code inside the block may have replaced the filters in effect with a copy of
        # the list, which carries our entry along with the rest, and it is that copy
        # the interpreter consults now. Both lists are cleaned then: the live one
        # because leaving an ignore filter in it silences warnings after the block,
        # and the one entered with because it can be put back later, by the
        # `catch_warnings` block that made the copy. A list that is neither, left
        # behind by a second replacement inside the block, keeps our entry, and there
        # is no way to reach it to take it out.
        live = _live_filters()
        if live is not None and live is not filters:
            _remove_filter(live, self._item)


def ignoring_deprecations(  # noqa: DOC502
    *, message: str = "", module: str = ""
) -> ignoring_warnings:
    """Ignore the deprecation warnings raised inside the block.

    This is [`ignoring_warnings`][..ignoring_warnings] for the most common case,
    library code that has to touch a symbol it deprecated itself. The user was
    already warned by the deprecated symbol they used; warning them again from its
    internals, about something they can do nothing about, is noise.

    Warning: All limitations of `ignoring_warnings()` apply
        Read the documentation of [`ignoring_warnings`][..ignoring_warnings],
        many limitations apply here too, as this is only a thin wrapper around it.

    Tip:
        Wrap the call that reaches the deprecated symbol, not everything around
        it. A block that covers more than that also silences deprecations that have
        nothing to do with the one it was added for.

    Example:
        ```python
        import warnings

        from frequenz.core.warnings import ignoring_deprecations


        # A type that used to be public and is now deprecated.
        class Wrapper:
            def __init__(self, raw: str) -> None:
                warnings.warn("Wrapper is deprecated", DeprecationWarning, stacklevel=2)
                self.raw = raw


        def from_wire(raw: str) -> Wrapper:
            # Whatever else this function does, the deprecations raised out there
            # are the user's business, so they stay outside the block.
            with ignoring_deprecations():
                return Wrapper(raw)
        ```

    Example: Inside a function that is itself deprecated
        A deprecated function has already warned its caller about this code path, so
        the deprecations it reaches on the way are noise too. Even there, keep the
        block around the calls that raise them rather than putting it around the
        whole body, which this module can't do for you: it is a context manager and
        refuses to be used as a decorator.

        ```python
        import warnings

        from typing_extensions import deprecated

        from frequenz.core.warnings import ignoring_deprecations


        # A type that used to be public and is now deprecated.
        class Wrapper:
            def __init__(self, raw: str) -> None:
                warnings.warn("Wrapper is deprecated", DeprecationWarning, stacklevel=2)
                self.raw = raw


        async def save(wrapper: Wrapper) -> None:
            print(f"saving {wrapper.raw}")


        @deprecated("Use from_wire() instead")
        async def parse(raw: str) -> Wrapper:
            with ignoring_deprecations():
                wrapper = Wrapper(raw)
            await save(wrapper)  # Outside: the scope note applies across an await.
            return wrapper
        ```

    Args:
        message: A regular expression the start of the warning message must match,
            case insensitively. The default matches every deprecation, which is
            usually right: the way to be precise here is a short block, not a narrow
            filter. Use it when the call being wrapped can also raise a deprecation
            that should be heard.
        module: A regular expression the start of the module name must match. The
            default matches every module.

    Returns:
        A context manager that ignores deprecation warnings.

    Raises:
        TypeError: If any argument has the wrong type.
        re.error: If `message` or `module` is not a valid regular expression.
    """
    return ignoring_warnings(
        category=DeprecationWarning, message=message, module=module
    )
