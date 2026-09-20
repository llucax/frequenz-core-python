# License: MIT
# Copyright © 2026 Frequenz Energy-as-a-Service GmbH

"""Keeping the old import path of a symbol that moved to another module.

See the package documentation for the background.
"""

import importlib
import warnings
from collections.abc import Callable, Mapping
from typing import Any


def _checked_aliases(module: str, aliases: Mapping[str, str]) -> dict[str, str]:
    """Check a set of deprecated aliases and take a snapshot of it.

    Everything here is checked when the aliases are declared rather than when one
    of them is reached, which can be a release later and in somebody else's code,
    where the failure no longer looks like a typo in an alias table.

    Args:
        module: The fully qualified name of the module defining the aliases.
        aliases: The mapping to check.

    Returns:
        A copy of the mapping, so a later change to it can't get past these checks.

    Raises:
        TypeError: If `module` is not a string, or a name or target is not one.
        ValueError: If a target is empty.
    """
    if not isinstance(module, str):
        raise TypeError(f"module must be a str, got {module!r}")
    checked = dict(aliases)
    for name, target in checked.items():
        if not isinstance(name, str):
            raise TypeError(f"alias names must be str, got {name!r}")
        if not isinstance(target, str):
            raise TypeError(f"the target of {name!r} must be a str, got {target!r}")
        if not target:
            raise ValueError(f"the target of {name!r} is empty")
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

    Warning: Security Warning
        This function imports the target module, so the mapping is as trusted
        as an `import` statement in this module. Write it out as a literal;
        don't build it from anything that comes from outside the program.

    Args:
        module: The fully qualified name of the module defining the aliases.
        aliases: A mapping of each deprecated name to the fully qualified name of the
            module that now owns it. It is copied, so changing it afterwards has no
            effect.

    Returns:
        A function suitable for use as the module's `__getattr__`.

    Raises:
        TypeError: If `module` is not a string, or a name or target is not one.
        ValueError: If a target is empty.
    """
    aliases = _checked_aliases(module, aliases)

    def module_getattr(name: str) -> Any:
        """Return a deprecated alias, warning about its new location.

        Args:
            name: The name being looked up in the module.

        Returns:
            The aliased object.

        Raises:
            AttributeError: If the name is not one of the deprecated aliases.
        """
        target_module = aliases.get(name)
        if target_module is None:
            raise AttributeError(f"module {module!r} has no attribute {name!r}")
        warnings.warn(
            f"{module}.{name} is deprecated. Use {target_module}.{name} instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return getattr(importlib.import_module(target_module), name)

    return module_getattr
