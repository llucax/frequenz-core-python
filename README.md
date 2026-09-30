# Frequenz Core Library

[![Build Status](https://github.com/frequenz-floss/frequenz-core-python/actions/workflows/ci.yaml/badge.svg)](https://github.com/frequenz-floss/frequenz-core-python/actions/workflows/ci.yaml)
[![PyPI Package](https://img.shields.io/pypi/v/frequenz-core)](https://pypi.org/project/frequenz-core/)
[![Docs](https://img.shields.io/badge/docs-latest-informational)](https://frequenz-floss.github.io/frequenz-core-python/)

## Introduction

Core utilities to complement Python's standard library. This library provides
essential building blocks for Python applications, including mathematical
utilities, datetime constants, typing helpers, strongly-typed identifiers,
module introspection tools, and warning and deprecation helpers.

The `frequenz-core` library is designed to be lightweight, type-safe, and
follow modern Python best practices. It fills common gaps in the standard
library with utilities that are frequently needed across different projects.

## Supported Platforms

The following platforms are officially supported (tested):

- **Python:** 3.11, 3.12, 3.13, 3.14
- **Operating System:** Ubuntu Linux 24.04
- **Architectures:** amd64, arm64

## Installation

You can install the library from PyPI using pip:

```bash
python -m pip install frequenz-core
```

Or add it to your project's dependencies in `pyproject.toml`:

```toml
[project]
dependencies = [
    "frequenz-core >= 1.0.2, < 2",
]
```

> [!NOTE]
> We recommend pinning the dependency to the latest version for programs,
> like `"frequenz-core == 1.0.2"`, and specifying a version range spanning
> one major version for libraries, like `"frequenz-core >= 1.0.2, < 2"`.
> We follow [semver](https://semver.org/).

## Quick Start

Here's a quick overview of the main functionality:

```python
from frequenz.core.math import is_close_to_zero, Interval
from frequenz.core.datetime import UNIX_EPOCH
from frequenz.core.module import get_public_module_name

# Math utilities
print(is_close_to_zero(1e-10))  # True - check if float is close to zero
interval = Interval(1, 10)
print(5 in interval)  # True - check if value is in range

# Datetime utilities
print(UNIX_EPOCH)  # 1970-01-01 00:00:00+00:00

# Module utilities
public_name = get_public_module_name("my.package._private.module")
print(public_name)  # "my.package"
```

## Code Examples

### Math Utilities

The math module provides utilities for floating-point comparisons and interval
checking:

```python
from frequenz.core.math import is_close_to_zero, Interval

# Robust floating-point zero comparison
assert is_close_to_zero(1e-10)  # True
assert not is_close_to_zero(0.1)  # False

# Interval checking with inclusive bounds
numbers = Interval(0, 100)
assert 50 in numbers  # True
assert not (150 in numbers)  # False - 150 is outside the interval

# Unbounded intervals
positive = Interval(0, None)  # [0, ∞]
assert 1000 in positive  # True
```

### `Enum` Utilities

Define enums with deprecated members that raise deprecation warnings when
accessed:

```python
from frequenz.core.enum import Enum, deprecated_member, unique

@unique
class TaskStatus(Enum):
   OPEN = 1
   IN_PROGRESS = 2
   # Duplicate values are fine with `@unique` as long as they are deprecated
   PENDING = deprecated_member(1, "PENDING is deprecated, use OPEN instead")
   DONE = deprecated_member(3, "DONE is deprecated, use FINISHED instead")
   FINISHED = 4

status1 = TaskStatus.PENDING  # Warns: "PENDING is deprecated, use OPEN instead"
assert status1 is TaskStatus.OPEN
```

### Typing Utilities

Disable class constructors to enforce factory pattern usage:

```python
from frequenz.core.typing import disable_init

@disable_init
class ApiClient:
    @classmethod
    def create(cls, api_key: str) -> "ApiClient":
        # Factory method with validation
        instance = cls.__new__(cls)
        # Custom initialization logic here
        return instance

# This will raise TypeError:
# client = ApiClient()  # ❌ TypeError

# Use factory method instead:
client = ApiClient.create("my-api-key")  # ✅ Works
```

Annotate floating point values honestly, as Python's numeric tower lets `int`
values through any `float` annotation:

```python
from typing import assert_never

from frequenz.core.typing import FloatInt

def describe(value: FloatInt | None) -> str:
    match value:
        case float() | int():
            return f"number {value}"
        case None:
            return "nothing"
        case unexpected:
            assert_never(unexpected)

assert describe(1) == "number 1"  # ✅ `case float():` alone would crash here
assert describe(1.5) == "number 1.5"
assert describe(None) == "nothing"
```

### Warnings/Deprecations Utilities

Silence a warning around a call without the side effect
[`warnings.catch_warnings`](https://docs.python.org/3/library/warnings.html#warnings.catch_warnings)
has, which is to reset the deduplication history of the whole program, so
every warning already shown is shown again
([python/cpython#73858](https://github.com/python/cpython/issues/73858)):

```python
import warnings

from frequenz.core.warnings import ignoring_deprecations

def legacy_parse(raw: str) -> int:
    warnings.warn("legacy_parse() is deprecated", DeprecationWarning, stacklevel=2)
    return int(raw)

def parse(raw: str) -> int:
    # Only around the call that reaches the deprecated symbol.
    with ignoring_deprecations():
        return legacy_parse(raw)

with warnings.catch_warnings(record=True, action="default") as shown:
    for _ in range(10):
        warnings.warn("said once", UserWarning)
        parse("1")

assert len(shown) == 1  # ✅ `catch_warnings()` in `parse()` would show it 10 times
```

Keep the old import path of a symbol that moved working, serving the very same
object so `isinstance` keeps working through both paths:

```python
from typing import TYPE_CHECKING, TypeAlias

from frequenz.core.warnings import deprecated_aliases

if TYPE_CHECKING:
    # Type checkers can't see the runtime `__getattr__` in the `else` branch.
    from decimal import Decimal as _Decimal
    from fractions import Fraction as _Fraction

    Decimal: TypeAlias = _Decimal
    Rational: TypeAlias = _Fraction
else:
    # In the `else`, never at module level: a `__getattr__` mypy can see makes
    # every name it doesn't know in this module `Any`, typos in downstream
    # imports included.
    __getattr__ = deprecated_aliases(
        __name__,
        {
            "Decimal": "decimal",  # decimal.Decimal
            "Rational": "fractions:Fraction",  # Renamed on the way out
        },
    )
```

And check in a test that a piece of code doesn't warn, without the `"error"`
filter that would make `warnings.warn()` raise inside the code under test:

```python
from frequenz.core.warnings import asserting_no_deprecations

def parse(raw: str) -> int:
    return int(raw)

with asserting_no_deprecations():
    assert parse("1") == 1
```

### Strongly-Typed IDs

Create type-safe identifiers for different entities:

```python
from frequenz.core.id import BaseId

class UserId(BaseId, str_prefix="USR"):
    pass

class OrderId(BaseId, str_prefix="ORD"):
    pass

user_id = UserId(123)
order_id = OrderId(456)

print(f"User: {user_id}")  # User: USR123
print(f"Order: {order_id}")  # Order: ORD456

# Type safety prevents mixing different ID types
def process_user(user_id: UserId) -> None:
    print(f"Processing user: {user_id}")

process_user(user_id)  # ✅ Works
# process_user(order_id)  # ❌ Type error
```

## Documentation

For information on how to use this library, please refer to the
[documentation](https://frequenz-floss.github.io/frequenz-core-python/).

## Contributing

If you want to know how to build this project and contribute to it, please
check out the [Contributing Guide](CONTRIBUTING.md).
