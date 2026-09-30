# License: MIT
# Copyright © 2026 Frequenz Energy-as-a-Service GmbH

"""Tests for `deprecated_aliases()`."""

import dataclasses
import decimal
import fractions
import sys
from types import ModuleType
from typing import Any

import pytest

from frequenz.core.warnings import (
    DeprecatedAlias,
    _deprecated_aliases,
    asserting_no_deprecations,
    deprecated_aliases,
)
from tests.warnings import documented_aliases

_MESSAGE = "{old} is deprecated since v1.2.3. Use {new} instead."


def test_deprecated_alias_keeps_what_it_was_given() -> None:
    """Test that an alias keeps its fields as given, and can't be changed."""
    alias = DeprecatedAlias(
        "Rational", new_module="fractions", new_name="Fraction", message=_MESSAGE
    )

    assert alias.name == "Rational"
    assert alias.new_module == "fractions"
    assert alias.new_name == "Fraction"
    assert alias.since is None
    assert alias.message == _MESSAGE
    assert alias == DeprecatedAlias(
        "Rational", new_module="fractions", new_name="Fraction", message=_MESSAGE
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        alias.new_name = ""  # type: ignore[misc]

    since = DeprecatedAlias("Decimal", new_module="decimal", since="v1.2.3")
    assert since.since == "v1.2.3"
    assert since.message is None


def test_deprecated_alias_defaults_the_target() -> None:
    """Test that a missing `new_name` is `name`, and a missing `new_module` `None`."""
    moved = DeprecatedAlias("Decimal", new_module="decimal", since="v1.2.3")
    assert moved.new_module == "decimal"
    assert moved.new_name == "Decimal"
    assert moved == DeprecatedAlias(
        "Decimal", new_module="decimal", new_name="Decimal", since="v1.2.3"
    )

    renamed = DeprecatedAlias("OldName", new_name="NewName", since="v1.2.3")
    assert renamed.new_module is None
    assert renamed.new_name == "NewName"


@pytest.mark.parametrize(
    "args, kwargs",
    [
        (("Decimal", "decimal", _MESSAGE), {}),
        ((), {"name": "Decimal", "new_module": "decimal", "message": _MESSAGE}),
        (("Decimal", "decimal"), {"since": "v1.2.3"}),
    ],
    ids=["all-positional", "name-by-keyword", "new-module-positional"],
)
def test_deprecated_alias_signature(
    args: tuple[Any, ...], kwargs: dict[str, Any]
) -> None:
    """Test that the name is positional-only and the rest keyword-only."""
    with pytest.raises(TypeError):
        DeprecatedAlias(*args, **kwargs)


def test_deprecated_alias_needs_exactly_one_of_since_and_message() -> None:
    """Test that giving both `since` and `message`, or neither, is refused.

    The `type: ignore` comments are part of the test: mypy reports them as unused,
    and fails, if the overloads ever accept these calls.
    """
    with pytest.raises(TypeError, match="exactly one of since and message, got both"):
        DeprecatedAlias(  # type: ignore[call-overload]
            "Decimal", new_module="decimal", since="v1.2.3", message=_MESSAGE
        )
    with pytest.raises(
        TypeError, match="exactly one of since and message, got neither"
    ):
        DeprecatedAlias("Decimal", new_module="decimal")  # type: ignore[call-overload]


def test_deprecated_alias_needs_a_new_module_or_name() -> None:
    """Test that an alias saying neither where nor under which name is refused.

    The `type: ignore` comments are part of the test: mypy reports them as unused,
    and fails, if the overloads ever accept these calls.
    """
    with pytest.raises(TypeError, match="needs new_module, new_name or both"):
        DeprecatedAlias("Decimal", since="v1.2.3")  # type: ignore[call-overload]
    with pytest.raises(TypeError, match="needs new_module, new_name or both"):
        DeprecatedAlias(  # type: ignore[call-overload]
            "Decimal", new_module=None, new_name=None, message=_MESSAGE
        )


@pytest.mark.parametrize(
    "name, new_module, new_name, message, error",
    [
        (0, "decimal", None, _MESSAGE, TypeError),
        ("", "decimal", None, _MESSAGE, ValueError),
        ("Dec imal", "decimal", None, _MESSAGE, ValueError),
        ("Decimal", 0, None, _MESSAGE, TypeError),
        ("Decimal", "", None, _MESSAGE, ValueError),
        ("Decimal", "a..b", None, _MESSAGE, ValueError),
        ("Decimal", "a.b-c", None, _MESSAGE, ValueError),
        ("Decimal", "decimal", 0, _MESSAGE, TypeError),
        ("Decimal", "decimal", "", _MESSAGE, ValueError),
        ("Decimal", "decimal", "decimal.Decimal", _MESSAGE, ValueError),
        ("Decimal", "decimal", None, 0, TypeError),
        ("Decimal", "decimal", None, "{old} moved, see {'here': 1}", ValueError),
        ("Decimal", "decimal", None, "{old} moved to {where}", ValueError),
        ("Decimal", "decimal", None, "{} moved to {new}", ValueError),
        ("Decimal", "decimal", None, "{0} moved to {new}", ValueError),
        ("Decimal", "decimal", None, "{old.missing} moved to {new}", ValueError),
        ("Decimal", "decimal", None, "{old[0]} moved to {new}", ValueError),
        ("Decimal", "decimal", None, "{old!r} moved to {new}", ValueError),
        ("Decimal", "decimal", None, "{old:>20} moved to {new}", ValueError),
        ("Decimal", "decimal", None, "{old:{new}} moved", ValueError),
    ],
    ids=[
        "name-type",
        "name-empty",
        "name-not-identifier",
        "new-module-type",
        "new-module-empty",
        "new-module-empty-part",
        "new-module-not-identifier",
        "new-name-type",
        "new-name-empty",
        "new-name-dotted",
        "message-type",
        "message-stray-brace",
        "message-unknown-field",
        "message-auto-numbered-field",
        "message-numbered-field",
        "message-attribute",
        "message-index",
        "message-conversion",
        "message-format-spec",
        "message-nested-field",
    ],
)
def test_deprecated_alias_rejects_bad_arguments(
    name: Any, new_module: Any, new_name: Any, message: Any, error: type[Exception]
) -> None:
    """Test that an alias is checked when it is created.

    Left to the lookup, an alias like this fails wherever it happens to be reached,
    with an error that says nothing about deprecated aliases: a `ModuleNotFoundError`
    for a module name with a typo, say, or a `KeyError` from inside
    `warnings.warn()` for a stray brace in the message.
    """
    with pytest.raises(error):
        DeprecatedAlias(name, new_module=new_module, new_name=new_name, message=message)


@pytest.mark.parametrize(
    "since, error",
    [(0, TypeError), ("", ValueError), ("  ", ValueError)],
    ids=["type", "empty", "blank"],
)
def test_deprecated_alias_rejects_a_bad_since(
    since: Any, error: type[Exception]
) -> None:
    """Test that `since` is checked when the alias is created, like the rest."""
    with pytest.raises(error):
        DeprecatedAlias("Decimal", new_module="decimal", since=since)


def test_deprecated_alias_formats_its_message() -> None:
    """Test the message of an alias with `since` and of one with `message`.

    `since` is inserted as written, braces included, rather than being read as part
    of a template.
    """
    names = {"old": "old_home.Decimal", "new": "decimal.Decimal"}

    since = DeprecatedAlias("Decimal", new_module="decimal", since="v{1}.2")
    assert since.format_message(**names) == (
        "old_home.Decimal is deprecated since v{1}.2. Use decimal.Decimal instead."
    )

    message = DeprecatedAlias(
        "Decimal", new_module="decimal", message="{old} is gone, use {new} ({{v2}})"
    )
    assert message.format_message(**names) == (
        "old_home.Decimal is gone, use decimal.Decimal ({v2})"
    )


_DECIMAL = DeprecatedAlias("Decimal", new_module="decimal", since="v1.2.3")


def test_deprecated_aliases_warns_and_returns_the_real_object() -> None:
    """Test that reaching an alias warns with its own message and yields the object.

    `Decimal` gives `since`, and its expected warning spells out the standard
    wording; `Fraction` gives a message of its own.
    """
    module = ModuleType("old_home")
    module.__getattr__ = deprecated_aliases(  # type: ignore[method-assign]
        module.__name__,
        _DECIMAL,
        DeprecatedAlias(
            "Fraction",
            new_module="fractions",
            message="{old} is gone since v2, see {new}",
        ),
    )

    with pytest.warns(DeprecationWarning) as caught:
        assert module.Decimal is decimal.Decimal
        assert module.Fraction is fractions.Fraction

    assert [str(warning.message) for warning in caught] == [
        "old_home.Decimal is deprecated since v1.2.3. Use decimal.Decimal instead.",
        "old_home.Fraction is gone since v2, see fractions.Fraction",
    ]
    # stacklevel=2, so the warning is attributed to this file, not to the helper.
    assert all(warning.filename == __file__ for warning in caught)


def test_deprecated_aliases_rejects_unknown_names() -> None:
    """Test that a name that is not an alias raises as a missing attribute would."""
    module = ModuleType("old_home_missing")
    module.__getattr__ = deprecated_aliases(  # type: ignore[method-assign]
        module.__name__, _DECIMAL
    )

    with pytest.raises(
        AttributeError, match="module 'old_home_missing' has no attribute 'Nope'"
    ):
        _ = module.Nope


@pytest.mark.parametrize(
    "args, kwargs, error",
    [
        ((0, _DECIMAL), {}, TypeError),
        ((_DECIMAL,), {"module": "old_home_bad"}, TypeError),
        (("old_home_bad",), {}, ValueError),
        (("old_home_bad", {"Decimal": "decimal"}), {}, TypeError),
        (("old_home_bad", "Decimal"), {}, TypeError),
        (
            (
                "old_home_bad",
                _DECIMAL,
                DeprecatedAlias("Decimal", new_module="fractions", message=_MESSAGE),
            ),
            {},
            ValueError,
        ),
        (
            (
                "old_home_bad",
                DeprecatedAlias("Decimal", new_name="Decimal", since="v1.2.3"),
            ),
            {},
            ValueError,
        ),
        (
            (
                "old_home_bad",
                _DECIMAL,
                DeprecatedAlias("Dec", new_name="Decimal", since="v1.2.3"),
            ),
            {},
            ValueError,
        ),
        (
            (
                "old_home_bad",
                _DECIMAL,
                DeprecatedAlias(
                    "Dec", new_module="old_home_bad", new_name="Decimal", since="v1.2.3"
                ),
            ),
            {},
            ValueError,
        ),
    ],
    ids=[
        "module",
        "module-by-keyword",
        "no-aliases",
        "mapping",
        "not-an-alias",
        "duplicate-name",
        "points-at-itself",
        "points-at-an-alias",
        "points-at-an-alias-by-module",
    ],
)
def test_deprecated_aliases_rejects_a_bad_table(
    args: tuple[Any, ...], kwargs: dict[str, Any], error: type[Exception]
) -> None:
    """Test that the aliases are checked as a whole when they are declared.

    Each alias checks its own fields when it is created; what's left is the module,
    the entries not being aliases at all, two aliases with the same name, where
    one would silently win over the other, and an alias pointing at another one in
    the same module, which would call the `__getattr__` again, forever if they
    point at each other.
    """
    with pytest.raises(error):
        deprecated_aliases(*args, **kwargs)


def test_deprecated_aliases_follows_renames() -> None:
    """Test that an alias can point to a symbol with a different name."""
    module = ModuleType("old_home_renamed")
    module.__getattr__ = deprecated_aliases(  # type: ignore[method-assign]
        module.__name__,
        DeprecatedAlias(
            "Rational", new_module="fractions", new_name="Fraction", message=_MESSAGE
        ),
    )

    with pytest.warns(
        DeprecationWarning,
        match=(
            "^old_home_renamed.Rational is deprecated since v1.2.3. "
            "Use fractions.Fraction instead.$"
        ),
    ):
        assert module.Rational is fractions.Fraction


def test_deprecated_aliases_follows_renames_in_place(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that an alias without `new_module` points into its own module.

    The module is looked up through the import system like any other, so it has to
    be in `sys.modules`, as a real one always is by the time it is reached.
    """
    module = ModuleType("old_home_in_place")
    module.Widget = fractions.Fraction  # type: ignore[attr-defined]
    module.__getattr__ = deprecated_aliases(  # type: ignore[method-assign]
        module.__name__,
        DeprecatedAlias("Gadget", new_name="Widget", since="v1.2.3"),
    )
    monkeypatch.setitem(sys.modules, module.__name__, module)

    with pytest.warns(
        DeprecationWarning,
        match=(
            "^old_home_in_place.Gadget is deprecated since v1.2.3. "
            "Use old_home_in_place.Widget instead.$"
        ),
    ):
        assert module.Gadget is fractions.Fraction


def test_deprecated_aliases_customises_the_warning() -> None:
    """Test the category and stacklevel overrides."""
    module = ModuleType("old_home_custom")
    module.__getattr__ = deprecated_aliases(  # type: ignore[method-assign]
        module.__name__,
        _DECIMAL,
        category=FutureWarning,
        stacklevel=1,
    )

    with pytest.warns(
        FutureWarning,
        match=(
            "^old_home_custom.Decimal is deprecated since v1.2.3. "
            "Use decimal.Decimal instead.$"
        ),
    ) as caught:
        assert module.Decimal is decimal.Decimal

    # stacklevel=1, so the warning is attributed to the helper itself.
    assert caught[0].filename == _deprecated_aliases.__file__


@pytest.mark.parametrize(
    "kwargs, error",
    [
        ({"category": int}, TypeError),
        ({"stacklevel": "2"}, TypeError),
        ({"stacklevel": 0}, ValueError),
    ],
    ids=[
        "category",
        "stacklevel-type",
        "stacklevel-range",
    ],
)
def test_deprecated_aliases_rejects_bad_customisation(
    kwargs: dict[str, Any], error: type[Exception]
) -> None:
    """Test that the overrides are checked when the aliases are declared."""
    with pytest.raises(error):
        deprecated_aliases("old_home_bad", _DECIMAL, **kwargs)


def test_deprecated_aliases_in_a_real_module() -> None:
    """Test the documented shape in a package written the way the docstring says.

    The tests above assign the `__getattr__` onto a `ModuleType` they build
    themselves, so none of them says anything about the `if TYPE_CHECKING:` and
    `else:` pattern the documentation tells people to write. This one imports a
    package written that way, where the `__getattr__` is reached through the
    import system like a user's would be.
    """
    with pytest.warns(
        DeprecationWarning,
        match=(
            "^tests.warnings.documented_aliases.Decimal is deprecated since v1.2.0. "
            "Use decimal.Decimal instead.$"
        ),
    ):
        assert documented_aliases.Decimal is decimal.Decimal

    with pytest.warns(
        DeprecationWarning,
        match=(
            "^tests.warnings.documented_aliases.Rational is deprecated since v1.3.0. "
            "Use fractions.Fraction instead.$"
        ),
    ):
        assert documented_aliases.Rational is fractions.Fraction

    # What the package defines itself is untouched: the `__getattr__` is only
    # consulted for names the module doesn't have.
    with asserting_no_deprecations():
        assert documented_aliases.kept() == "kept"

    with pytest.raises(
        AttributeError,
        match="module 'tests.warnings.documented_aliases' has no attribute 'Nope'",
    ):
        # The `type: ignore` is the point of the `else:` branch, not a nuisance:
        # with the `__getattr__` at module level mypy would type this `Any` and
        # say nothing, here and in every downstream import of a name that never
        # existed.
        _ = documented_aliases.Nope  # type: ignore[attr-defined]


def test_deprecated_aliases_reach_star_imports() -> None:
    """Test that the aliases come through a wildcard import, warning as they go.

    `__all__` is the only thing a wildcard import consults, and the names in it
    that the module doesn't define are looked up one by one, so they go through
    the `__getattr__` and warn like any other access.
    """
    namespace: dict[str, Any] = {}

    with pytest.warns(DeprecationWarning) as caught:
        # pylint: disable-next=exec-used
        exec("from tests.warnings.documented_aliases import *", namespace)

    assert documented_aliases.__all__ == ["Decimal", "Rational", "kept"]
    assert namespace["Decimal"] is decimal.Decimal
    assert namespace["Rational"] is fractions.Fraction
    assert namespace["kept"] is documented_aliases.kept
    # Each name in a package's `__all__` is asked for twice, once by the import
    # machinery finding out whether it names a submodule and once by the wildcard
    # import itself, so every alias warns more than once here. Which messages come
    # out is the part worth asserting; how many times CPython looks them up is not.
    assert {str(warning.message) for warning in caught} == {
        "tests.warnings.documented_aliases.Decimal is deprecated since v1.2.0. "
        "Use decimal.Decimal instead.",
        "tests.warnings.documented_aliases.Rational is deprecated since v1.3.0. "
        "Use fractions.Fraction instead.",
    }


def test_deprecated_aliases_refuses_a_module_target() -> None:
    """Test that an alias landing on a module is refused instead of served.

    Serving it would half work: `from old import sub` would find it, while
    `import old.sub` and `from old.sub import X` would still raise
    `ModuleNotFoundError`, because the import system never asks a package's
    `__getattr__`. A module that moved needs a real `__init__.py` at the old
    path.
    """
    module = ModuleType("old_home_package")
    module.__getattr__ = deprecated_aliases(  # type: ignore[method-assign]
        module.__name__,
        # os.path is a module
        DeprecatedAlias("path", new_module="os", message=_MESSAGE),
    )

    with pytest.raises(TypeError, match="^the target of old_home_package.path is"):
        _ = module.path

    # And the refusal wins over the warning, which would otherwise announce a move
    # that can't be made.
    with asserting_no_deprecations():
        with pytest.raises(TypeError):
            _ = module.path
