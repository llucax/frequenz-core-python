# License: MIT
# Copyright © 2026 Frequenz Energy-as-a-Service GmbH

"""Keeping the old import path of a symbol that moved to another module.

See the package documentation for the background.
"""

import importlib
import string
import warnings
from collections.abc import Callable
from dataclasses import dataclass
from types import ModuleType
from typing import Any, overload


@dataclass(frozen=True, init=False, slots=True)
class DeprecatedAlias:
    """A symbol kept reachable from its old name.

    Each one is an entry for [`deprecated_aliases`][..deprecated_aliases], which
    has the examples.

    The symbol moved to another module, `new_module`, was renamed, `new_name`, or
    both. Without `new_module` it is still in the module defining the alias, under
    its new name.

    An alias says either since which version it is deprecated, with `since`, or
    its whole warning message, with `message`, but not both. `since="v1.2.0"`
    warns with `<old> is deprecated since v1.2.0. Use <new> instead.`, which is
    what the deprecations guide suggests, so `message` is only needed to say
    something else.

    Everything is checked when the alias is created rather than when it is
    reached.
    """

    name: str
    """The deprecated name, in the module defining the alias."""

    new_module: str | None
    """The fully qualified name of the module the symbol lives in now.

    `None` if it is still in the module defining the alias, under
    [`new_name`][..new_name].
    """

    new_name: str
    """The name the symbol has now, [`name`][..name] if it was not renamed."""

    since: str | None
    """The version the alias is deprecated since, or `None` if it has a `message`.

    The warning says `<old> is deprecated since <since>. Use <new> instead.`
    """

    message: str | None
    """The template for the warning message, or `None` if it has a `since`.

    It is formatted with `{old}` and `{new}`, the fully qualified names of the
    alias and of the symbol it resolves to, as plain fields, without attributes,
    indexes, conversions or format specs.
    """

    # One pair of overloads with `new_module` and one with only `new_name`, so a call
    # with neither matches none of them.
    @overload
    def __init__(  # noqa: D107
        self,
        name: str,
        /,
        *,
        new_module: str,
        new_name: str | None = None,
        since: str,
    ) -> None: ...

    @overload
    def __init__(  # noqa: D107
        self,
        name: str,
        /,
        *,
        new_module: str,
        new_name: str | None = None,
        message: str,
    ) -> None: ...

    @overload
    def __init__(  # noqa: D107
        self,
        name: str,
        /,
        *,
        new_module: None = None,
        new_name: str,
        since: str,
    ) -> None: ...

    @overload
    def __init__(  # noqa: D107
        self,
        name: str,
        /,
        *,
        new_module: None = None,
        new_name: str,
        message: str,
    ) -> None: ...

    def __init__(  # noqa: DOC502
        self,
        name: str,
        /,
        *,
        new_module: str | None = None,
        new_name: str | None = None,
        since: str | None = None,
        message: str | None = None,
    ) -> None:
        """Initialize this instance.

        At least one of `new_module` and `new_name` must be given, and exactly one
        of `since` and `message`.

        Args:
            name: The deprecated name, in the module defining the alias.
            new_module: The fully qualified name of the module the symbol lives in
                now, if it moved out of the module defining the alias.
            new_name: The name the symbol has now, if it was renamed.
            since: The version the alias is deprecated since, such as `"v1.2.0"`.
                The warning then says `<old> is deprecated since <since>. Use
                <new> instead.`
            message: The template for the whole warning message instead, formatted
                with `{old}` and `{new}`, the fully qualified names of the alias
                and of the symbol it resolves to, as plain fields, without
                attributes, indexes, conversions or format specs.

        Raises:
            TypeError: If an argument is not a string, if neither `new_module` nor
                `new_name` is given, or if not exactly one of `since` and
                `message` is.
            ValueError: If `name`, `new_name` or a part of `new_module` is not an
                identifier, if `since` is empty, or if `message` is not a template
                with only plain `{old}` and `{new}` fields.
        """
        # The class is frozen, which blocks plain assignment here too.
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "new_module", new_module)
        object.__setattr__(self, "new_name", name if new_name is None else new_name)
        object.__setattr__(self, "since", since)
        object.__setattr__(self, "message", message)
        self._validate(new_name)

    def format_message(self, *, old: str, new: str) -> str:
        """Format the warning message for this alias.

        Args:
            old: The fully qualified name of the alias.
            new: The fully qualified name of the symbol it resolves to.

        Returns:
            `<old> is deprecated since <since>. Use <new> instead.` if the alias
                has a `since`, or its `message` formatted with `old` and `new`.
        """
        if self.message is None:
            return f"{old} is deprecated since {self.since}. Use {new} instead."
        return self.message.format(old=old, new=new)

    def _validate(self, new_name: str | None) -> None:
        """Check the fields.

        Args:
            new_name: The `new_name` given to `__init__()`, before it defaulted to
                `name`, to tell whether it was given at all.

        Raises:
            TypeError: If neither `new_module` nor `new_name` is given, or if not
                exactly one of `since` and `message` is.
        """
        if self.new_module is None and new_name is None:
            raise TypeError(
                f"the alias {self.name!r} needs new_module, new_name or both, "
                "got neither"
            )
        if (self.since is None) == (self.message is None):
            raise TypeError(
                f"the alias {self.name!r} needs exactly one of since and message, "
                f"got {'both' if self.since is not None else 'neither'}"
            )
        self._validate_name()
        self._validate_new_module()
        self._validate_new_name()
        self._validate_since()
        self._validate_message()

    def _validate_name(self) -> None:
        """Check that `name` is an identifier.

        Raises:
            TypeError: If it is not a string.
            ValueError: If it is not an identifier.
        """
        if not isinstance(self.name, str):
            raise TypeError(f"alias names must be str, got {self.name!r}")
        if not self.name.isidentifier():
            raise ValueError(f"alias names must be identifiers, got {self.name!r}")

    def _validate_new_module(self) -> None:
        """Check that `new_module`, if given, is a module name.

        Raises:
            TypeError: If it is not a string.
            ValueError: If one of its dotted parts is not an identifier.
        """
        if self.new_module is None:
            return
        if not isinstance(self.new_module, str):
            raise TypeError(
                f"the new_module of {self.name!r} must be a str, "
                f"got {self.new_module!r}"
            )
        if not all(part.isidentifier() for part in self.new_module.split(".")):
            raise ValueError(
                f"the new_module of {self.name!r} is not a module name: "
                f"{self.new_module!r}"
            )

    def _validate_new_name(self) -> None:
        """Check that `new_name` is an identifier.

        Raises:
            TypeError: If it is not a string.
            ValueError: If it is not an identifier.
        """
        if not isinstance(self.new_name, str):
            raise TypeError(
                f"the new_name of {self.name!r} must be a str, got {self.new_name!r}"
            )
        if not self.new_name.isidentifier():
            raise ValueError(
                f"the new_name of {self.name!r} is not an identifier: "
                f"{self.new_name!r}"
            )

    def _validate_since(self) -> None:
        """Check that `since`, if given, is not empty.

        Raises:
            TypeError: If it is not a string.
            ValueError: If it is empty or blank.
        """
        if self.since is None:
            return
        if not isinstance(self.since, str):
            raise TypeError(
                f"the since of {self.name!r} must be a str, got {self.since!r}"
            )
        if not self.since.strip():
            raise ValueError(f"the since of {self.name!r} is empty")

    def _validate_message(self) -> None:
        """Check that `message`, if given, is a template with plain `{old}` and `{new}`.

        Raises:
            TypeError: If it is not a string.
            ValueError: If it has a stray brace, or a replacement field other than a
                plain `{old}` or `{new}`.
        """
        if self.message is None:
            return
        if not isinstance(self.message, str):
            raise TypeError(
                f"the message of {self.name!r} must be a str, got {self.message!r}"
            )
        problem = (
            f"the message of {self.name!r} must be a template with only plain "
            f"{{old}} and {{new}} fields, got {self.message!r}"
        )
        try:
            # A stray brace raises here.
            parsed = list(string.Formatter().parse(self.message))
        except ValueError as error:
            raise ValueError(problem) from error
        # Anything more than a plain field can fail depending on the names it is
        # formatted with, which are only known when the alias is reached, so
        # formatting it once here can't tell: `{old.missing}` raises
        # `AttributeError`, and `{old:{new}}` makes the new name a format spec.
        if not all(
            field in (None, "old", "new") and not spec and conversion is None
            for _, field, spec, conversion in parsed
        ):
            raise ValueError(problem)


def deprecated_aliases(  # noqa: DOC502
    module: str,
    /,
    *aliases: DeprecatedAlias,
    category: type[Warning] = DeprecationWarning,
    stacklevel: int = 2,
) -> Callable[[str], Any]:
    """Build a module `__getattr__` that warns about deprecated aliases.

    Use this for symbols that moved to another module, or were renamed, but should
    keep working from their old import path, when a [`typing_extensions.deprecated`][]
    decorator is not an option because the object is not yours to mark: decorating
    it would deprecate it for everybody, including the users of its new home or name.
    The alias also stays the very same object, so [`isinstance`][] keeps working
    through both paths.

    Each alias is a [`DeprecatedAlias`][..DeprecatedAlias] saying since which version
    it is deprecated, so aliases deprecated in different releases each warn with
    their own, or carrying a message of its own instead.

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

        from frequenz.core.warnings import DeprecatedAlias, deprecated_aliases

        if TYPE_CHECKING:
            # Private import, only for type checkers
            from decimal import Decimal as _Decimal

            Decimal: TypeAlias = _Decimal
        else:
            __getattr__ = deprecated_aliases(
                __name__,
                DeprecatedAlias("Decimal", new_module="decimal", since="v1.2.0"),
            )
        ```

        Reaching `Decimal` through this module, say `mypkg.Decimal`, now emits a
        `DeprecationWarning` saying `mypkg.Decimal is deprecated since v1.2.0. Use
        decimal.Decimal instead.`

    Example: Renaming
        When the symbol was also renamed on the way out, `new_name` gives the name
        it has now:

        ```python
        from typing import TYPE_CHECKING, TypeAlias

        from frequenz.core.warnings import DeprecatedAlias, deprecated_aliases

        if TYPE_CHECKING:
            from fractions import Fraction as _Fraction

            Rational: TypeAlias = _Fraction
        else:
            __getattr__ = deprecated_aliases(
                __name__,
                DeprecatedAlias(
                    "Rational",
                    new_module="fractions",
                    new_name="Fraction",
                    since="v1.3.0",
                ),
            )
        ```

        Without `new_module`, the symbol was renamed in this very module:

        ```python
        from typing import TYPE_CHECKING, TypeAlias

        from frequenz.core.warnings import DeprecatedAlias, deprecated_aliases


        class Widget:
            ...  # Called Gadget before v1.4.0


        if TYPE_CHECKING:
            Gadget: TypeAlias = Widget
        else:
            __getattr__ = deprecated_aliases(
                __name__,
                DeprecatedAlias("Gadget", new_name="Widget", since="v1.4.0"),
            )
        ```

    Example: Custom message
        When the standard wording is not enough, an alias can give its whole
        message instead of `since`, as a template that gets the fully qualified old
        and new names as `{old}` and `{new}`:

        ```python
        from typing import TYPE_CHECKING, TypeAlias

        from frequenz.core.warnings import DeprecatedAlias, deprecated_aliases

        if TYPE_CHECKING:
            from decimal import Decimal as _Decimal

            Decimal: TypeAlias = _Decimal
        else:
            __getattr__ = deprecated_aliases(
                __name__,
                DeprecatedAlias(
                    "Decimal",
                    new_module="decimal",
                    message="{old} is deprecated since v1.2.0 and will be removed "
                    "in v2.0.0. Use {new} instead.",
                ),
            )
        ```

    Tip: Deprecating whole modules
        This function can't be used to deprecate a whole module. If you need to
        do that, you can keep a real `__init__.py` at the old path, with a
        `__getattr__ = deprecated_aliases(...)` that includes all the symbols
        that used to be reachable there.

    Warning: Security Warning
        This function imports the modules the aliases point at, so the aliases are
        as trusted as an `import` statement in this module. Write them out as
        literals; don't build them from anything that comes from outside the
        program.

    Args:
        module: The fully qualified name of the module defining the aliases.
        *aliases: The deprecated aliases, at least one, each with its own name.
        category: The category of the warning to emit.
        stacklevel: How far up the stack the warning is reported, counting from the
            `__getattr__` itself. The default of 2 points at the code reaching for
            the alias, and only needs raising if something wraps the returned
            function.

    Returns:
        A function suitable for use as the module's `__getattr__`.

    Raises:
        TypeError: If an argument has the wrong type, including an alias that is
            not a [`DeprecatedAlias`][..DeprecatedAlias]. Also later, when an alias
            is reached, if it resolves to a module rather than to a symbol in one.
        ValueError: If there are no aliases, if two of them have the same name, if
            one points at another alias in the same module, itself included, or if
            `stacklevel` is smaller than 1.
    """
    if not isinstance(module, str):
        raise TypeError(f"module must be a str, got {module!r}")
    if not (isinstance(category, type) and issubclass(category, Warning)):
        raise TypeError(f"category must be a Warning subclass, got {category!r}")
    if not isinstance(stacklevel, int):
        raise TypeError(f"stacklevel must be an int, got {stacklevel!r}")
    if stacklevel < 1:
        raise ValueError(f"stacklevel must be 1 or more, got {stacklevel!r}")
    if not aliases:
        raise ValueError(f"no aliases given for module {module!r}")
    by_name: dict[str, DeprecatedAlias] = {}
    for alias in aliases:
        # Also what a mapping, the form this function used to take, runs into.
        if not isinstance(alias, DeprecatedAlias):
            raise TypeError(f"aliases must be DeprecatedAlias instances, got {alias!r}")
        # A dict literal would keep the last of two entries silently; this is the
        # one place that can tell.
        if alias.name in by_name:
            raise ValueError(f"alias {alias.name!r} is given more than once")
        by_name[alias.name] = alias
    for alias in aliases:
        # Reaching it would call this `__getattr__` again, and never stop if the
        # aliases point at each other.
        if alias.new_module in (None, module) and alias.new_name in by_name:
            raise ValueError(
                f"the alias {alias.name!r} points at {module}.{alias.new_name}, "
                "which is a deprecated alias too"
            )

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
        alias = by_name.get(name)
        if alias is None:
            raise AttributeError(f"module {module!r} has no attribute {name!r}")
        new_module = module if alias.new_module is None else alias.new_module
        new = f"{new_module}.{alias.new_name}"
        # Resolved before the warning is raised, so an alias that can't work says
        # so instead of warning about a move that didn't happen. It also keeps the
        # `TypeError` below from being masked by an "error" filter turning that
        # warning into an exception first.
        value = getattr(importlib.import_module(new_module), alias.new_name)
        if isinstance(value, ModuleType):
            raise TypeError(
                f"the target of {module}.{name} is the module {new}, and this "
                "aliases names, not modules: the import system never consults a "
                f"package's __getattr__, so `import {module}.{name}` would fail "
                f"anyway. Keep a real __init__.py at {module}.{name}, with the "
                "aliases for the names it used to hold in it."
            )
        warnings.warn(
            alias.format_message(old=f"{module}.{name}", new=new),
            category,
            stacklevel=stacklevel,
        )
        return value

    return module_getattr
