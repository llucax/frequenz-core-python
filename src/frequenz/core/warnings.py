# License: MIT
# Copyright © 2026 Frequenz Energy-as-a-Service GmbH

"""Warnings utilities.

This module provides [`catch_warnings`][.catch_warnings], a drop-in replacement for
[`warnings.catch_warnings`][] that works around a long-standing CPython issue
([python/cpython#73858](https://github.com/python/cpython/issues/73858)) where merely
entering and leaving a `catch_warnings` block makes every warning in the program be
shown again.

The standard library deduplicates warnings (the `"default"`, `"module"` and `"once"`
filter actions) using a per-module `__warningregistry__` dictionary, and invalidates
every registry whenever the filters change, including on every enter and exit of a
[`warnings.catch_warnings`][] block, even if the filters are restored to exactly what
they were. So code like this, which is the documented way of suppressing a warning
locally:

```python
import warnings


def legacy_convert(value: str) -> int:
    warnings.warn("legacy_convert() is deprecated", DeprecationWarning)
    return int(value)


def convert(value: str) -> int:
    with warnings.catch_warnings(action="ignore", category=DeprecationWarning):
        return legacy_convert(value)
```

makes any warning emitted by the *caller* (or by any other code in the program) be
shown again on every call, regardless of the filters in place. See
[python/cpython#73858](https://github.com/python/cpython/issues/73858) for the
details.

[`catch_warnings`][.catch_warnings] restores the registries of all loaded modules on
exit, so the deduplication history is preserved across the block whenever it is safe to
do so.
"""

import sys
import threading
import warnings
from types import ModuleType, TracebackType
from typing import Any, Final, Generic, Literal, TypeAlias, TypeVar, cast, overload

__all__ = ["Action", "catch_warnings"]

_W_co = TypeVar("_W_co", bound="list[warnings.WarningMessage] | None", covariant=True)
"""What entering the block returns: the recorded warnings or `None`."""


Action: TypeAlias = Literal[
    "default", "error", "ignore", "always", "all", "module", "once"
]
"""The possible actions for a warning filter (see [`warnings.simplefilter`][])."""

_VERSION_KEY: Final[str] = "version"
"""The key used by CPython to store the filters version in warning registries."""

_Registry: TypeAlias = dict[Any, Any]
"""A module `__warningregistry__` dictionary."""


class _RegistryProbeWarning(Warning):
    """Private warning category used only to read the internal filters version."""


def _registries() -> list[_Registry]:
    """Collect the warning registries of all loaded modules.

    Returns:
        The `__warningregistry__` dictionaries found in `sys.modules`.
    """
    registries: list[_Registry] = []
    for module in list(sys.modules.values()):
        namespace = getattr(module, "__dict__", None)
        if not isinstance(namespace, dict):
            continue
        registry = namespace.get("__warningregistry__")
        if isinstance(registry, dict):
            registries.append(registry)
    return registries


def _live_filters(module: Any) -> list[Any] | None:
    """Return the list of warning filters in effect, the live object.

    Args:
        module: The `warnings` module in use.

    Returns:
        The list CPython consults on each warning, honouring context-aware warnings
            when available, or `None` if it can't be found.
    """
    get_filters = getattr(module, "_get_filters", None)
    filters = get_filters() if get_filters is not None else module.filters
    return filters if isinstance(filters, list) else None


def _mutated(module: Any) -> None:
    """Bump the internal filters version.

    Args:
        module: The `warnings` module in use.
    """
    mutated = getattr(module, "_filters_mutated", None)
    if mutated is not None:
        mutated()
        return
    with module.catch_warnings():  # Entering and leaving bumps it.
        pass


def _current_filters(module: Any) -> list[Any]:
    """Return a copy of the warning filters in effect.

    Args:
        module: The `warnings` module in use.

    Returns:
        The filters in effect, honouring context-aware warnings when available.
    """
    return list(_live_filters(module) or [])


def _probe_version(module: Any) -> int | None:
    """Read the internal filters version.

    This adds an `"ignore"` filter for a private category and emits a warning of that
    category with a private registry: CPython stamps the current filters version into
    the registry before consulting the filters. It must be called inside a
    [`warnings.catch_warnings`][] block, so the added filter is discarded on exit.

    Args:
        module: The `warnings` module in use.

    Returns:
        The filters version after adding the filter, or `None` if the interpreter
            doesn't behave like CPython.
    """
    registry: _Registry = {}
    module.simplefilter("ignore", _RegistryProbeWarning)
    module.warn_explicit(
        "filters version probe",
        _RegistryProbeWarning,
        __file__,
        0,
        module=__name__,
        registry=registry,
    )
    version = registry.get(_VERSION_KEY)
    return version if isinstance(version, int) else None


def _check_bump_counts() -> bool:
    """Check that the interpreter bumps the filters version as this module expects.

    The workaround assumes that adding a filter, entering a
    [`warnings.catch_warnings`][] block and leaving one each bump the version exactly
    once. This measures them with nested blocks.

    Returns:
        Whether the interpreter behaves as expected.
    """
    with warnings.catch_warnings():
        first = _probe_version(warnings)
        second = _probe_version(warnings)
        with warnings.catch_warnings():
            inner = _probe_version(warnings)
        after = _probe_version(warnings)
    if first is None or second is None or inner is None or after is None:
        return False
    filter_bump = second - first
    enter_bump = inner - second - filter_bump
    exit_bump = after - inner - filter_bump
    return (filter_bump, enter_bump, exit_bump) == (1, 1, 1)


_SUPPORTED: Final[bool] = _check_bump_counts()
"""Whether the registry preservation is active for this interpreter."""

_local = threading.local()
"""Per-thread stack of the active `catch_warnings` blocks, for nesting."""


def _stack() -> list["catch_warnings[Any]"]:
    """Get the per-thread stack of active blocks.

    Returns:
        The stack, innermost block last.
    """
    stack: list[catch_warnings[Any]] | None = getattr(_local, "stack", None)
    if stack is None:
        stack = _local.stack = []
    return stack


class catch_warnings(  # pylint: disable=invalid-name,too-many-instance-attributes
    warnings.catch_warnings, Generic[_W_co]
):
    """A `catch_warnings` block that preserves the warnings deduplication history.

    This is a drop-in replacement for [`warnings.catch_warnings`][] that takes the
    same arguments and behaves the same way, except that on exit it also brings the
    per-module `__warningregistry__` dictionaries back to a valid state (with some
    **extra runtime costs**), so warnings that were already shown before the block are
    not shown again just because a block was entered and left. See the module
    documentation for the background.

    The internals are probed once when this module is imported, and if they don't
    behave as expected the extra work is skipped, so on an unexpected interpreter the
    class degrades to a plain [`warnings.catch_warnings`][], it never suppresses a
    warning the standard library would show.

    What is preserved:

    * The history of every module loaded at the time the block is entered, so warnings
      emitted before the block (by any module, not just the one using the block) are
      not repeated after it.
    * Warnings emitted *inside* the block, as long as the filters were only changed
      through the `action="ignore"` argument or not at all. With any other change to
      the filters inside the block (like a `simplefilter()` call, even one adding an
      `"ignore"` filter) the history inside the block is discarded on exit, as the
      standard library does, because the warnings could have been shown under filters
      that no longer apply.
    * Nested blocks compose: an inner block that could preserve its history doesn't
      prevent the outer one from preserving its own.

    Tip: Use the `action` argument, not `simplefilter()`
        To ignore warnings inside a block, pass `action="ignore"` (and
        `category`) instead of calling [`warnings.simplefilter`][] inside it.
        Both fix the repetition of warnings shown *before* the block, but only
        the `action` form also keeps deduplicating warnings shown *inside* it
        (like an unrelated warning emitted by the wrapped code), because it is
        the only case where the block can be sure the filters were only
        narrowed.

    What is not, on purpose:

    * If the filters in effect after the block differ from the ones in effect when it
      was entered (for example, another thread changed them, which can persist with
      `-X context_aware_warnings`), nothing is restored, as the history may no longer
      be valid.
    * If the filters were changed *outside* any block since a module last emitted a
      warning, that module's history was already invalid when the block was entered
      and it stays discarded, so a `"error"` or `"always"` filter set in the meantime
      is honoured.
    * Registries not reachable through `sys.modules` (like the globals of code run
      with `exec()`) and warnings emitted with an explicit `registry` argument are not
      handled.

    Warning: Cost
        With `action="ignore"` and no `record`, the block doesn't go through the
        standard library at all: the filter is added to the live filters list and
        removed on exit, which leaves the internal filters version untouched, so no
        registry ever becomes stale and there is nothing to restore. This costs about as
        much as the standard library block.

        Any other use (another `action`, `record=True`, or no `action` at all) must go
        through the standard library and then repair the registries, which iterates over
        `sys.modules` twice per block and copies every warning registry found: tens of
        microseconds with a few hundred modules loaded, linear in their number, compared
        to well under a microsecond for the standard library version. Fine for
        occasional use, but not free in tight loops.

    Warning: Concurrency
        The restoration is not atomic with respect to other threads emitting warnings or
        changing filters, and there is no locking against them. Every race considered
        degrades to the standard library behaviour (a warning that was already shown is
        shown once more), never to suppressing a warning that should be shown, but this
        was only verified with the GIL, not on free-threaded builds.

    Example:
        ```python
        import warnings

        from frequenz.core.warnings import catch_warnings


        def legacy_convert(value: str) -> int:
            warnings.warn("legacy_convert() is deprecated", DeprecationWarning)
            return int(value)


        def convert(value: str) -> int:
            with catch_warnings(action="ignore", category=DeprecationWarning):
                return legacy_convert(value)


        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("default")
            for _ in range(10):
                warnings.warn("shown only once", UserWarning)
                convert("1")

        assert len(caught) == 1
        ```

    Warning: Relies on CPython implementation details
        This works by inspecting the undocumented `__warningregistry__` dictionaries and
        the internal *filters version* counter used by CPython's `warnings` module (both
        the C and the pure Python implementations). The behaviour was verified on CPython
        3.11 to 3.15, with and without `-X context_aware_warnings`.
    """

    _module: Any
    """The `warnings` module in use (set by the base class)."""

    _record: bool
    """Whether warnings are recorded (set by the base class)."""

    @overload
    def __init__(  # noqa: D107  # pylint: disable=too-many-arguments
        self: "catch_warnings[None]",
        *,
        record: Literal[False] = False,
        module: ModuleType | None = None,
        action: Action | None = None,
        category: type[Warning] | tuple[type[Warning], ...] = Warning,
        lineno: int = 0,
        append: bool = False,
    ) -> None: ...

    @overload
    def __init__(  # noqa: D107  # pylint: disable=too-many-arguments
        self: "catch_warnings[list[warnings.WarningMessage]]",
        *,
        record: Literal[True],
        module: ModuleType | None = None,
        action: Action | None = None,
        category: type[Warning] | tuple[type[Warning], ...] = Warning,
        lineno: int = 0,
        append: bool = False,
    ) -> None: ...

    @overload
    def __init__(  # noqa: D107  # pylint: disable=too-many-arguments
        self,
        *,
        record: bool,
        module: ModuleType | None = None,
        action: Action | None = None,
        category: type[Warning] | tuple[type[Warning], ...] = Warning,
        lineno: int = 0,
        append: bool = False,
    ) -> None: ...

    def __init__(  # pylint: disable=too-many-arguments
        self,
        *,
        record: bool = False,
        module: ModuleType | None = None,
        action: Action | None = None,
        category: type[Warning] | tuple[type[Warning], ...] = Warning,
        lineno: int = 0,
        append: bool = False,
    ) -> None:
        """Initialize this instance.

        The arguments are the same as for [`warnings.catch_warnings`][].

        Args:
            record: Whether to record warnings instead of showing them.
            module: An alternative `warnings` module (only for testing `warnings`).
            action: If given, a filter with this action is added on entering, as if
                [`warnings.simplefilter`][] was called with the remaining arguments.
            category: The warning category for `action`.
            lineno: The line number for `action`.
            append: Whether the filter for `action` is appended instead of inserted.
        """
        super().__init__(record=record, module=module)
        self._own_filter: tuple[Any, ...] | None = (
            None if action is None else (action, category, lineno, append)
        )
        self._snapshots: dict[int, tuple[_Registry, _Registry, bool]] = {}
        self._entry_filters: list[Any] = []
        self._enter_version: int | None = None
        self._harmless_bumps: int = 0
        self._fast_item: tuple[Any, ...] | None = None
        self._fast_saved: list[Any] = []
        self._fast_showwarning: Any = None
        self._fast_entered: bool = False

    def _only_ignores(self) -> bool:
        """Tell whether this block itself only adds `"ignore"` filters.

        Returns:
            Whether the history recorded inside the block is valid outside it.
        """
        return self._own_filter is None or self._own_filter[0] == "ignore"

    def __enter__(self) -> _W_co:
        """Enter the block.

        Returns:
            The list of recorded warnings if `record` is true, `None` otherwise.

        Raises:
            RuntimeError: If this instance was already entered.
        """
        if not _SUPPORTED:
            log = cast(_W_co, super().__enter__())
            if self._own_filter is not None:
                self._module.simplefilter(*self._own_filter)
            return log

        if self._own_filter is not None and self._own_filter[0] == "ignore":
            filters = _live_filters(self._module) if not self._record else None
            if filters is not None:
                # Ignoring only removes warnings, so history recorded on either
                # side of the block is valid on the other: add the filter without
                # going through the standard library (which would bump the filters
                # version and invalidate every registry) and take it out on exit.
                if self._fast_entered:
                    raise RuntimeError(f"Cannot enter {self!r} twice")
                self._fast_entered = True
                _, category, lineno, append = self._own_filter
                self._fast_item = ("ignore", None, category, None, lineno)
                self._fast_saved = filters[:]
                self._fast_showwarning = self._module.showwarning
                if append:
                    filters.append(self._fast_item)
                else:
                    filters.insert(0, self._fast_item)
                return cast(_W_co, None)

        snapshots = [(registry, registry.copy()) for registry in _registries()]
        self._entry_filters = _current_filters(self._module)
        log = cast(_W_co, super().__enter__())  # Bumps the version once.
        version = _probe_version(self._module)  # And this once more.
        self._enter_version = version
        self._harmless_bumps = 0
        if version is not None:
            # Only registries stamped with the version in effect before entering
            # hold a valid history; older ones were already invalidated by a filter
            # change and must stay that way.
            entry_version = version - 2
            self._snapshots = {
                id(registry): (
                    registry,
                    saved,
                    saved.get(_VERSION_KEY) == entry_version,
                )
                for registry, saved in snapshots
            }
        if self._own_filter is not None:
            self._module.simplefilter(*self._own_filter)
        if version is not None and self._only_ignores():
            # Only "ignore" filters were added, so what was already shown is still
            # valid inside the block too: keep deduplicating in here.
            inner_version = version + (0 if self._own_filter is None else 1)
            for registry, _, valid in self._snapshots.values():
                if valid:
                    registry[_VERSION_KEY] = inner_version
        _stack().append(self)
        return log

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Exit the block, restoring the filters and the warning registries."""
        if not _SUPPORTED:
            super().__exit__(exc_type, exc_val, exc_tb)
            return

        if self._fast_item is not None:
            self._exit_fast()
            return

        stack = _stack()
        if stack and stack[-1] is self:
            stack.pop()
        try:
            version = _probe_version(self._module)  # Bumps the version once.
        finally:
            super().__exit__(exc_type, exc_val, exc_tb)  # And this once more.
        snapshots, self._snapshots = self._snapshots, {}
        if version is None or self._enter_version is None:
            return
        if _current_filters(self._module) != self._entry_filters:
            # The filters changed for good while we were inside (possible with
            # context-aware warnings and threads): the history may not be valid.
            return

        final_version = version + 1
        own_bumps = 0 if self._own_filter is None else 1
        unexplained_bumps = (
            version - self._enter_version - own_bumps - 1 - self._harmless_bumps
        )
        if unexplained_bumps == 0 and self._only_ignores():
            self._keep_history(snapshots, final_version)
            if stack:
                stack[-1]._harmless_bumps += final_version - (self._enter_version - 2)
        else:
            self._restore_history(snapshots, final_version)

    def _exit_fast(self) -> None:
        """Leave a block that only added an `"ignore"` filter to the live list."""
        item, self._fast_item = self._fast_item, None
        filters = _live_filters(self._module)
        if filters is not None:
            # By identity: somebody may have inserted an equal filter meanwhile.
            for index, existing in enumerate(filters):
                if existing is item:
                    del filters[index]
                    break
            if filters != self._fast_saved:
                # The filters were changed by hand inside the block: restore them
                # as the standard library would, bumping the version as it does,
                # since the registries were filled under other filters.
                filters[:] = self._fast_saved
                _mutated(self._module)
        self._fast_saved = []
        self._module.showwarning = self._fast_showwarning
        self._fast_showwarning = None

    @staticmethod
    def _keep_history(
        snapshots: dict[int, tuple[_Registry, _Registry, bool]], version: int
    ) -> None:
        """Keep the history recorded inside the block and re-validate everything.

        Everything recorded inside is valid under the restored filters: keep it, add
        back what was valid at entry, and stamp every registry with the new version.

        Args:
            snapshots: The registries and their copies taken on entry.
            version: The filters version in effect after leaving the block.
        """
        for registry in _registries():
            snapshot = snapshots.get(id(registry))
            if snapshot is None:
                registry[_VERSION_KEY] = version
                continue
            _, saved, valid = snapshot
            if valid:
                registry.update(saved)
                registry[_VERSION_KEY] = version
            elif registry.get(_VERSION_KEY) != saved.get(_VERSION_KEY):
                # Stale at entry but cleared and refilled inside.
                registry[_VERSION_KEY] = version

    @staticmethod
    def _restore_history(
        snapshots: dict[int, tuple[_Registry, _Registry, bool]], version: int
    ) -> None:
        """Bring the registries that were valid at entry back to that state.

        The filters changed inside the block in a way we can't vouch for, so whatever
        was recorded inside is dropped.

        Args:
            snapshots: The registries and their copies taken on entry.
            version: The filters version in effect after leaving the block.
        """
        for registry, saved, valid in snapshots.values():
            if not valid:
                continue
            registry.clear()
            registry.update(saved)
            registry[_VERSION_KEY] = version
