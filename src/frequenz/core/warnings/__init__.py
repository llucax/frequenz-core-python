# License: MIT
# Copyright © 2026 Frequenz Energy-as-a-Service GmbH

"""Warnings utilities.

This module provides [`ignoring_warnings`][.ignoring_warnings], a context manager to
silence warnings around a piece of code, without the side effect that
[`warnings.catch_warnings`][] has, and
[`ignoring_deprecations`][.ignoring_deprecations] for the common case of a library
having to touch a symbol it deprecated itself.

It also provides [`deprecated_aliases`][.deprecated_aliases], to keep the old import
path of a symbol that moved to another module working, warning whoever uses it, and
[`asserting_no_warnings`][.asserting_no_warnings] with its
[`asserting_no_deprecations`][.asserting_no_deprecations] shortcut, to check in a test
that a piece of code doesn't warn.

The documented way of silencing a warning locally is a
[`warnings.catch_warnings`][] block, but merely entering and leaving one invalidates
the warnings deduplication history of the whole program, so every warning that was
already shown is shown again, and again on every call. This is
[python/cpython#73858](https://github.com/python/cpython/issues/73858), open since
2017.

[`ignoring_warnings`][.ignoring_warnings] adds the filter to the list the interpreter
consults and takes it out again on exit, which leaves the deduplication history
untouched, for about half a microsecond more per block than the standard library one
costs:

```python
import warnings

from frequenz.core.warnings import ignoring_warnings


def legacy_convert(value: str) -> int:
    warnings.warn("legacy_convert() is deprecated", DeprecationWarning, stacklevel=2)
    return int(value)


def convert(value: str) -> int:
    with ignoring_warnings(category=DeprecationWarning):
        return legacy_convert(value)


with warnings.catch_warnings(record=True, action="default") as caught:
    for _ in range(10):
        warnings.warn("shown only once", UserWarning)
        convert("1")

assert len(caught) == 1
```

With [`warnings.catch_warnings`][] in `convert()` the same loop shows the
`UserWarning` ten times.
"""

from ._asserting import asserting_no_deprecations, asserting_no_warnings
from ._deprecated_aliases import deprecated_aliases
from ._ignoring import ignoring_deprecations, ignoring_warnings

__all__ = [
    "asserting_no_deprecations",
    "asserting_no_warnings",
    "deprecated_aliases",
    "ignoring_deprecations",
    "ignoring_warnings",
]
