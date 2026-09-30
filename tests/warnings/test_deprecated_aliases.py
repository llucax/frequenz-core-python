# License: MIT
# Copyright © 2026 Frequenz Energy-as-a-Service GmbH

"""Tests for `deprecated_aliases()`."""

import decimal
import fractions
from types import ModuleType
from typing import Any

import pytest

from frequenz.core.warnings import (
    _deprecated_aliases,
    asserting_no_deprecations,
    deprecated_aliases,
)
from tests.warnings import documented_aliases


def test_deprecated_aliases_warns_and_returns_the_real_object() -> None:
    """Test that reaching an alias warns and yields the object from its new home."""
    module = ModuleType("old_home")
    module.__getattr__ = deprecated_aliases(  # type: ignore[method-assign]
        module.__name__, {"Decimal": "decimal", "Fraction": "fractions"}
    )

    with pytest.warns(DeprecationWarning) as caught:
        assert module.Decimal is decimal.Decimal
        assert module.Fraction is fractions.Fraction

    assert [str(warning.message) for warning in caught] == [
        "old_home.Decimal is deprecated. Use decimal.Decimal instead.",
        "old_home.Fraction is deprecated. Use fractions.Fraction instead.",
    ]
    # stacklevel=2, so the warning is attributed to this file, not to the helper.
    assert all(warning.filename == __file__ for warning in caught)


def test_deprecated_aliases_rejects_unknown_names() -> None:
    """Test that a name that is not an alias raises as a missing attribute would."""
    module = ModuleType("old_home_missing")
    module.__getattr__ = deprecated_aliases(  # type: ignore[method-assign]
        module.__name__, {"Decimal": "decimal"}
    )

    with pytest.raises(
        AttributeError, match="module 'old_home_missing' has no attribute 'Nope'"
    ):
        _ = module.Nope


@pytest.mark.parametrize(
    "args, error",
    [
        ((0, {"Decimal": "decimal"}), TypeError),
        (("old_home_bad", {0: "decimal"}), TypeError),
        (("old_home_bad", {"Decimal": 0}), TypeError),
        (("old_home_bad", {"Decimal": ""}), ValueError),
        (("old_home_bad", {"Decimal": ":Decimal"}), ValueError),
        (("old_home_bad", {"Decimal": "decimal:"}), ValueError),
        (("old_home_bad", {"Decimal": "a:b:c"}), ValueError),
    ],
    ids=[
        "module",
        "name",
        "target-type",
        "target-empty",
        "target-no-module",
        "target-no-name",
        "target-two-colons",
    ],
)
def test_deprecated_aliases_rejects_a_bad_table(
    args: tuple[Any, Any], error: type[Exception]
) -> None:
    """Test that the alias table is checked when it is declared.

    Left to the lookup, a table like this fails wherever the alias happens to be
    reached, with an error that says nothing about deprecated aliases: an
    `AttributeError` about `str.partition` for a target that is not a string, say.
    """
    with pytest.raises(error):
        deprecated_aliases(*args)


def test_deprecated_aliases_copies_the_table() -> None:
    """Test that changing the mapping afterwards doesn't get past the checks."""
    aliases: dict[str, str] = {"Decimal": "decimal"}
    module = ModuleType("old_home_copied")
    module.__getattr__ = deprecated_aliases(  # type: ignore[method-assign]
        module.__name__, aliases
    )
    aliases["Fraction"] = ""

    with pytest.raises(AttributeError):
        _ = module.Fraction


def test_deprecated_aliases_follows_renames() -> None:
    """Test that an alias can point to a symbol with a different name."""
    module = ModuleType("old_home_renamed")
    module.__getattr__ = deprecated_aliases(  # type: ignore[method-assign]
        module.__name__, {"Rational": "fractions:Fraction"}
    )

    with pytest.warns(
        DeprecationWarning,
        match=(
            "^old_home_renamed.Rational is deprecated. "
            "Use fractions.Fraction instead.$"
        ),
    ):
        assert module.Rational is fractions.Fraction


def test_deprecated_aliases_customises_the_warning() -> None:
    """Test the message, category and stacklevel overrides."""
    module = ModuleType("old_home_custom")
    module.__getattr__ = deprecated_aliases(  # type: ignore[method-assign]
        module.__name__,
        {"Decimal": "decimal"},
        message="{old} moved to {new} in v2",
        category=FutureWarning,
        stacklevel=1,
    )

    with pytest.warns(
        FutureWarning, match="^old_home_custom.Decimal moved to decimal.Decimal in v2$"
    ) as caught:
        assert module.Decimal is decimal.Decimal

    # stacklevel=1, so the warning is attributed to the helper itself.
    assert caught[0].filename == _deprecated_aliases.__file__


@pytest.mark.parametrize(
    "kwargs, error",
    [
        ({"message": None}, TypeError),
        ({"message": "{old} moved, see {'here': 1}"}, ValueError),
        ({"message": "{old} moved to {where}"}, ValueError),
        ({"category": int}, TypeError),
        ({"stacklevel": "2"}, TypeError),
        ({"stacklevel": 0}, ValueError),
    ],
    ids=[
        "message-type",
        "message-stray-brace",
        "message-unknown-field",
        "category",
        "stacklevel-type",
        "stacklevel-range",
    ],
)
def test_deprecated_aliases_rejects_bad_customisation(
    kwargs: dict[str, Any], error: type[Exception]
) -> None:
    """Test that the overrides are checked when the aliases are declared.

    A template is checked by formatting it once here, since a stray brace would
    otherwise raise a `KeyError` from inside `warnings.warn()`, at the lookup.
    """
    with pytest.raises(error):
        deprecated_aliases("old_home_bad", {"Decimal": "decimal"}, **kwargs)


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
            "^tests.warnings.documented_aliases.Decimal is deprecated. "
            "Use decimal.Decimal instead.$"
        ),
    ):
        assert documented_aliases.Decimal is decimal.Decimal

    with pytest.warns(
        DeprecationWarning,
        match=(
            "^tests.warnings.documented_aliases.Rational is deprecated. "
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
        "tests.warnings.documented_aliases.Decimal is deprecated. "
        "Use decimal.Decimal instead.",
        "tests.warnings.documented_aliases.Rational is deprecated. "
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
        module.__name__, {"path": "os"}  # os.path is a module
    )

    with pytest.raises(TypeError, match="^the target of old_home_package.path is"):
        _ = module.path

    # And the refusal wins over the warning, which would otherwise announce a move
    # that can't be made.
    with asserting_no_deprecations():
        with pytest.raises(TypeError):
            _ = module.path
