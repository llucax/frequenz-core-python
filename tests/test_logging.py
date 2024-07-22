# License: MIT
# Copyright © 2024 Frequenz Energy-as-a-Service GmbH

"""Tests for the log module."""


import pytest

from frequenz.core.logging import get_public_logger


@pytest.mark.parametrize(
    "module_name, expected_logger_name",
    [
        ("some.pub", "some.pub"),
        ("some.pub._some._priv", "some.pub"),
        ("some.pub._some._priv.public", "some.pub"),
        ("some.pub._some._priv.public._private", "some.pub"),
        ("some._priv.pub", "some"),
        ("_priv.some.pub", "root"),
        ("some", "some"),
        ("some._priv", "some"),
        ("_priv", "root"),
    ],
)
def test_get_public_logger(module_name: str, expected_logger_name: str) -> None:
    """Test that the logger name is as expected."""
    logger = get_public_logger(module_name)
    assert logger.name == expected_logger_name
