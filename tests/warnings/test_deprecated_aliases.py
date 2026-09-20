# License: MIT
# Copyright © 2026 Frequenz Energy-as-a-Service GmbH

"""Tests for `deprecated_aliases()`."""

import decimal
import fractions
from types import ModuleType
from typing import Any

import pytest

from frequenz.core.warnings import deprecated_aliases


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
    ],
    ids=["module", "name", "target-type", "target-empty"],
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
