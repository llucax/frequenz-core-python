# Frequenz Core Library Release Notes

## Summary

<!-- Here goes a general summary of what this release is about -->

## Upgrading

<!-- Here goes notes on how to upgrade from previous versions, including deprecations and what they should be replaced with -->

## New Features

- A new `frequenz.core.warnings` module with a `catch_warnings` drop-in replacement for `warnings.catch_warnings` that preserves the warnings deduplication history, so warnings already shown before a block are not shown again after it. This works around [python/cpython#73858](https://github.com/python/cpython/issues/73858), where merely entering and leaving a `catch_warnings` block makes every warning in the program repeat. It relies on CPython internals (verified on 3.11 to 3.15) and falls back to the standard behaviour on interpreters that don't behave as expected, see the module documentation for the details and limitations.

## Bug Fixes

<!-- Here goes notable bug fixes that are worth a special mention or explanation -->
