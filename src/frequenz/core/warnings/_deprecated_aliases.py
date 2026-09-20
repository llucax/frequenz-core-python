# License: MIT
# Copyright © 2026 Frequenz Energy-as-a-Service GmbH

"""Keeping the old import path of a symbol that moved to another module.

See the package documentation for the background.
"""

import importlib
import warnings
from collections.abc import Callable, Mapping
from typing import Any


def _checked_aliases(
    module: str, aliases: Mapping[str, str]
) -> dict[str, tuple[str, str]]:
    """Check a set of deprecated aliases and resolve them.

    Everything here is checked when the aliases are declared rather than when one
    of them is reached, which can be a release later and in somebody else's code,
    where the failure no longer looks like a typo in an alias table.

    Args:
        module: The fully qualified name of the module defining the aliases.
        aliases: The mapping to check.

    Returns:
        Each deprecated name mapped to the module its target lives in and the name
            it has there, so a later change to `aliases` can't get past these
            checks and the string doesn't have to be taken apart on every lookup.

    Raises:
        TypeError: If `module` is not a string, or a name or target is not one.
        ValueError: If a target is empty, carries more than one `:`, or has
            nothing after it.
    """
    if not isinstance(module, str):
        raise TypeError(f"module must be a str, got {module!r}")
    checked: dict[str, tuple[str, str]] = {}
    for name, target in dict(aliases).items():
        if not isinstance(name, str):
            raise TypeError(f"alias names must be str, got {name!r}")
        if not isinstance(target, str):
            raise TypeError(f"the target of {name!r} must be a str, got {target!r}")
        target_module, renamed, target_name = target.partition(":")
        # `partition()` stops at the first colon, so a second one would silently
        # end up inside the name, and the warning would point at `a.b:c`.
        if ":" in target_name:
            raise ValueError(
                f"the target of {name!r} has more than one ':': {target!r}"
            )
        if not target_module:
            raise ValueError(f"the target of {name!r} names no module: {target!r}")
        if renamed and not target_name:
            raise ValueError(
                f"the target of {name!r} has nothing after the ':': {target!r}"
            )
        checked[name] = (target_module, target_name or name)
    return checked


def deprecated_aliases(  # noqa: DOC502
    module: str, aliases: Mapping[str, str]
) -> Callable[[str], Any]:
    """Build a module `__getattr__` that warns about deprecated aliases.

    Use this for symbols that moved to another module but should keep working from
    their old import path, when a [`typing_extensions.deprecated`][] decorator is not
    an option because the object is not yours to mark: decorating it would deprecate
    it for everybody, including the users of its new home. The alias also stays the
    very same object, so [`isinstance`][] keeps working through both paths.

    Danger:
        Follow the usage example structure strictly. In particular never drop
        the `else:`, otherwise a type checker will see the `__getattr__`
        assignment and treat every symbol in the module as [`Any`][typing.Any],
        effectively disabling type checking for the entire module.

    Example: Usage
        This is how a module that used to define `Decimal` itself, and now gets it
        from [`decimal`][], keeps the old import path working:

        ```python
        from typing import TYPE_CHECKING, TypeAlias

        from frequenz.core.warnings import deprecated_aliases

        if TYPE_CHECKING:
            # Private import, only for type checkers
            from decimal import Decimal as _Decimal

            Decimal: TypeAlias = _Decimal
        else:
            __getattr__ = deprecated_aliases(__name__, {"Decimal": "decimal"})
        ```

        Reaching `Decimal` through this module now emits a `DeprecationWarning`
        saying to use `decimal.Decimal` instead.

    Example: Renaming
        When the symbol was also renamed on the way out, the new name goes after a
        colon, as in an entry point:

        ```python
        from typing import TYPE_CHECKING, TypeAlias

        from frequenz.core.warnings import deprecated_aliases

        if TYPE_CHECKING:
            from fractions import Fraction as _Fraction

            Rational: TypeAlias = _Fraction
        else:
            __getattr__ = deprecated_aliases(
                __name__,
                {
                    "Rational": "fractions:Fraction",
                },
            )
        ```

    Warning: Security Warning
        This function imports the target module, so the mapping is as trusted
        as an `import` statement in this module. Write it out as a literal;
        don't build it from anything that comes from outside the program.

    Args:
        module: The fully qualified name of the module defining the aliases.
        aliases: A mapping of each deprecated symbol to where it lives now, as the
            fully qualified name of the module that owns it, optionally followed by
            `:` and the name it has there, when it is not the deprecated one. It is
            copied, so changing it afterwards has no effect.

    Returns:
        A function suitable for use as the module's `__getattr__`.

    Raises:
        TypeError: If `module` is not a string, or a name or target is not one.
        ValueError: If a target is empty, carries more than one `:`, or has
            nothing after it.
    """
    targets = _checked_aliases(module, aliases)

    def module_getattr(name: str) -> Any:
        """Return a deprecated alias, warning about its new location.

        Args:
            name: The name being looked up in the module.

        Returns:
            The aliased object.

        Raises:
            AttributeError: If the name is not one of the deprecated aliases.
        """
        target = targets.get(name)
        if target is None:
            raise AttributeError(f"module {module!r} has no attribute {name!r}")
        target_module, target_name = target
        warnings.warn(
            f"{module}.{name} is deprecated. "
            f"Use {target_module}.{target_name} instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return getattr(importlib.import_module(target_module), target_name)

    return module_getattr
