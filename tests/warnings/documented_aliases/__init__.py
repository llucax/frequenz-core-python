# License: MIT
# Copyright © 2026 Frequenz Energy-as-a-Service GmbH

"""A package written the way `deprecated_aliases()` documents, for the tests.

The other tests build a `ModuleType` and assign the `__getattr__` onto it, which
exercises the function but not the shape the docstring tells people to write: the
aliases declared under `if TYPE_CHECKING:`, the assignment in the `else:` branch,
and a real module the import system loads. This package is that shape, so the
tests importing from here fail if the documented pattern stops working.
"""

from typing import TYPE_CHECKING, TypeAlias

from frequenz.core.warnings import deprecated_aliases

__all__ = ["Decimal", "Rational", "kept"]

if TYPE_CHECKING:
    # Only for type checkers, which can't see the runtime `__getattr__` in the
    # `else` branch.
    from decimal import Decimal as _Decimal
    from fractions import Fraction as _Fraction

    Decimal: TypeAlias = _Decimal
    """A decimal number.

    Deprecated:
        `tests.warnings.documented_aliases.Decimal` is deprecated. Use
        [decimal.Decimal][] instead.
    """

    Rational: TypeAlias = _Fraction
    """A rational number.

    Deprecated:
        `tests.warnings.documented_aliases.Rational` is deprecated. Use
        [fractions.Fraction][] instead.
    """
else:
    __getattr__ = deprecated_aliases(
        __name__, {"Decimal": "decimal", "Rational": "fractions:Fraction"}
    )


def kept() -> str:
    """Return the name of a symbol this package still defines itself."""
    return "kept"
