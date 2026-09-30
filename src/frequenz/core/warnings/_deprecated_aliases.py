# License: MIT
# Copyright © 2026 Frequenz Energy-as-a-Service GmbH

"""Keeping the old import path of a symbol that moved to another module.

See the package documentation for the background.
"""

import importlib
import warnings
from collections.abc import Callable, Mapping
from types import ModuleType
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
    module: str,
    aliases: Mapping[str, str],
    *,
    message: str = "{old} is deprecated. Use {new} instead.",
    category: type[Warning] = DeprecationWarning,
    stacklevel: int = 2,
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

    Example: Custom deprecation message
        The message is a template that gets the old and new fully qualified names,
        so it can carry a version, a link, or anything else the default doesn't
        say:

        ```python
        from typing import TYPE_CHECKING, TypeAlias

        from frequenz.core.warnings import deprecated_aliases

        if TYPE_CHECKING:
            from decimal import Decimal as _Decimal

            Decimal: TypeAlias = _Decimal
        else:
            __getattr__ = deprecated_aliases(
                __name__,
                {
                    "Decimal": "decimal",
                },
                message="{old} is deprecated since v2, use {new} instead.",
            )
        ```

    Tip: Deprecating whole modules
        This function can't be used to deprecate a whole module. If you need to
        do that, you can keep a real `__init__.py` at the old path, with a
        `__getattr__ = deprecated_aliases(...)` that includes all the symbols
        that used to be reachable there.

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
        message: The template for the warning message, formatted with `{old}` and
            `{new}`, the fully qualified names of the alias and of the symbol it
            resolves to.
        category: The category of the warning to emit.
        stacklevel: How far up the stack the warning is reported, counting from the
            `__getattr__` itself. The default of 2 points at the code reaching for
            the alias, and only needs raising if something wraps the returned
            function.

    Returns:
        A function suitable for use as the module's `__getattr__`.

    Raises:
        TypeError: If an argument has the wrong type, including a name or target
            that is not a string. Also later, when an alias is reached, if it
            resolves to a module rather than to a symbol in one.
        ValueError: If a target is empty, carries more than one `:`, or has
            nothing after it, if `message` is not a template taking `{old}` and
            `{new}`, or if `stacklevel` is smaller than 1.
    """
    if not isinstance(message, str):
        raise TypeError(f"message must be a str, got {message!r}")
    if not (isinstance(category, type) and issubclass(category, Warning)):
        raise TypeError(f"category must be a Warning subclass, got {category!r}")
    if not isinstance(stacklevel, int):
        raise TypeError(f"stacklevel must be an int, got {stacklevel!r}")
    if stacklevel < 1:
        raise ValueError(f"stacklevel must be 1 or more, got {stacklevel!r}")
    try:
        # Formatting it once here is the only way to find a stray brace, which
        # would otherwise raise from inside `warnings.warn()` at lookup time.
        message.format(old="", new="")
    except (IndexError, KeyError, ValueError) as error:
        raise ValueError(
            f"message must be a template taking {{old}} and {{new}}, "
            f"got {message!r}"
        ) from error
    targets = _checked_aliases(module, aliases)

    def module_getattr(name: str) -> Any:
        """Return a deprecated alias, warning about its new location.

        Args:
            name: The name being looked up in the module.

        Returns:
            The aliased object.

        Raises:
            AttributeError: If the name is not one of the deprecated aliases.
            TypeError: If the alias resolves to a module, which this can't keep
                reachable from its old path.
        """
        target = targets.get(name)
        if target is None:
            raise AttributeError(f"module {module!r} has no attribute {name!r}")
        target_module, target_name = target
        # Resolved before the warning is raised, so an alias that can't work says
        # so instead of warning about a move that didn't happen. It also keeps the
        # `TypeError` below from being masked by an "error" filter turning that
        # warning into an exception first.
        value = getattr(importlib.import_module(target_module), target_name)
        if isinstance(value, ModuleType):
            raise TypeError(
                f"the target of {module}.{name} is the module "
                f"{target_module}.{target_name}, and this aliases names, not "
                "modules: the import system never consults a package's "
                f"__getattr__, so `import {module}.{name}` would fail anyway. "
                f"Keep a real __init__.py at {module}.{name}, with the aliases "
                "for the names it used to hold in it."
            )
        warnings.warn(
            message.format(
                old=f"{module}.{name}", new=f"{target_module}.{target_name}"
            ),
            category,
            stacklevel=stacklevel,
        )
        return value

    return module_getattr
