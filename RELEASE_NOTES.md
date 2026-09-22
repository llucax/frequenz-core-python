# Frequenz Core Library Release Notes

## New Features

A new `frequenz.core.warnings` module with:

- `ignoring_warnings()` and `ignoring_deprecations()` to silence warnings/deprecations around a piece of code. Unlike `warnings.catch_warnings()`, entering and leaving it doesn't reset the warnings deduplication history of the program, so warnings already shown are not shown again, working around [python/cpython#73858](https://github.com/python/cpython/issues/73858). It costs about the same as the standard library block, so it is also usable on a hot path, where repairing the damage afterwards would not be.

- `asserting_no_warnings()`, and its `asserting_no_deprecations()` shortcut, fail when the code in the block raises a matching warning/deprecation, listing each one with the place it came from. They are meant for tests, and are a better tool than an `"error"` filter, which makes `warnings.warn()` raise inside the code under test and so changes the very behaviour the test is checking.

- `deprecated_aliases()` builds a module `__getattr__` that warns when a symbol that moved to another module is reached through its old import path, serving the very same object so `isinstance` keeps working through both paths.
