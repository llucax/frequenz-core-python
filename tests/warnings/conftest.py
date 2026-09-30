# License: MIT
# Copyright © 2026 Frequenz Energy-as-a-Service GmbH

"""Fixtures shared by the warnings tests."""

import sys
from collections.abc import Callable, Iterator
from types import ModuleType

import pytest

from frequenz.core.warnings import _ignoring

_MODULE_SOURCE = """
import warnings

# Messages include the module name so the "once" action, which deduplicates by
# message and category only, doesn't see repeated messages across tests.
DEFAULT_MESSAGE = f"warned in {__name__}"

def warn(message=DEFAULT_MESSAGE, category=UserWarning):
    warnings.warn(message, category, stacklevel=1)

def warn_then_block(block, message=DEFAULT_MESSAGE, category=UserWarning):
    warnings.warn(message, category, stacklevel=1)
    with block():
        pass
"""


@pytest.fixture(name="make_module")
def make_module_fixture() -> Iterator[Callable[[str], ModuleType]]:
    """Create fresh modules, each with its own (initially missing) registry."""
    created: list[str] = []

    def make(name: str) -> ModuleType:
        module = ModuleType(name)
        module.__file__ = f"<{name}>"
        # pylint: disable-next=exec-used
        exec(compile(_MODULE_SOURCE, f"<{name}>", "exec"), module.__dict__)
        sys.modules[name] = module
        created.append(name)
        return module

    yield make
    for name in created:
        sys.modules.pop(name, None)


@pytest.fixture(name="restore_filters", autouse=True)
def restore_filters_fixture() -> Iterator[None]:
    """Leave the process filters as they were, whatever a test does to them."""
    live = _ignoring._live_filters()  # pylint: disable=protected-access
    saved = None if live is None else live[:]
    yield
    if saved is not None:
        live = _ignoring._live_filters()  # pylint: disable=protected-access
        assert live is not None
        live[:] = saved
