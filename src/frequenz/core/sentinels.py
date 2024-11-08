# License: MIT
# Copyright © 2021-2022 Tal Einat
# Copyright © 2024 Frequenz Energy-as-a-Service GmbH
# Based on:
# https://github.com/taleinat/python-stdlib-sentinels/blob/9fdf9628d7bf010f0a66c72b717802c715c7d564/sentinels/sentinels.py

"""Create unique sentinel objects.

This module provides a class, [`Sentinel`][frequenz.core.sentinels], which can be used
to create unique sentinel objects as specified by [`PEP
661`](https://peps.python.org/pep-0661/).
"""


import sys as _sys
from threading import Lock as _Lock
from typing import Self, cast

__all__ = ["Sentinel"]


# Design and implementation decisions:
#
# The first implementations created a dedicated class for each instance.
# However, once it was decided to use Sentinel for type signatures, there
# was no longer a need for a dedicated class for each sentinel value on order
# to enable strict type signatures.  Since class objects consume a relatively
# large amount of memory, the implementation was changed to avoid this.
#
# With this change, the mechanism used for unpickling/copying objects needed
# to be changed too, since we could no longer count on each dedicated class
# simply returning its singleton instance as before.  __reduce__ can return
# a string, upon which an attribute with that name is looked up in the module
# and returned.  However, that would have meant that pickling/copying support
# would depend on the "name" argument being exactly the name of the variable
# used in the module, and simply wouldn't work for sentinels created in
# functions/methods.  Instead, a registry for sentinels was added, where all
# sentinel objects are stored keyed by their name + module name.  This is used
# to look up existing sentinels both during normal object creation and during
# copying/unpickling.


class Sentinel:
    """Create a unique sentinel object.

    Sentinel objects are used to represent special values, such as "no value" or "not
    computed yet". They are used in place of [`None`][] to avoid ambiguity, since `None`
    can be a valid value in some cases.

    For more details, please check [`PEP 661`](https://peps.python.org/pep-0661/).

    Example:
        ```python
        from frequenz.core.sentinels import Sentinel
        from typing import assert_type

        MISSING = Sentinel('MISSING')

        def func(value: int | MISSING) -> None:
            if value is MISSING:
                assert_type(value, MISSING)
            else:
                assert_type(value, int)
        ```
    """

    _name: str
    _repr: str
    _module_name: str

    def __new__(
        cls,
        name: str,
        repr: str | None = None,  # pylint: disable=redefined-builtin
        module_name: str | None = None,
    ) -> Self:
        """Create a new sentinel object.

        Args:
            name: The fully-qualified name of the variable to which the return value
                shall be assigned.
            repr: The `repr` of the sentinel object. If not provided, "<name>" will be
                used (with any leading class names removed).
            module_name: The fully-qualified name of the module in which the sentinel is
                created. If not provided, the module name will be inferred from the call
                stack.

        Returns:
            A unique sentinel object.
        """
        name = str(name)
        repr = str(repr) if repr else f'<{name.split(".")[-1]}>'
        if not module_name:
            parent_frame = _get_parent_frame()
            module_name = (
                parent_frame.f_globals.get("__name__", "__main__")
                if parent_frame is not None
                else __name__
            )

        # Include the class's module and fully qualified name in the
        # registry key to support sub-classing.
        registry_key = _sys.intern(
            f"{cls.__module__}-{cls.__qualname__}-{module_name}-{name}"
        )
        sentinel = _registry.get(registry_key, None)
        if sentinel is not None:
            return cast(Self, sentinel)
        sentinel = super().__new__(cls)
        sentinel._name = name
        sentinel._repr = repr
        sentinel._module_name = module_name
        with _lock:
            return cast(Self, _registry.setdefault(registry_key, sentinel))

    def __repr__(self):
        """Return a string representation of the sentinel object."""
        return self._repr

    def __reduce__(self):
        """Return the sentinel object's representation for pickling and copying."""
        return (
            self.__class__,
            (
                self._name,
                self._repr,
                self._module_name,
            ),
        )


# We ignore checks for the rest of the file, as this is an external implementation and
# we hope this module gets added to the Python standard library eventually.
# pylint: disable-all
# mypy: ignore-errors
# type: ignore

_lock = _Lock()
_registry: dict[str, Sentinel] = {}


# The following implementation attempts to support Python
# implementations which don't support sys._getframe(2), such as
# Jython and IronPython.
#
# The version added to the stdlib may simply return sys._getframe(2),
# without the fallbacks.
#
# For reference, see the implementation of namedtuple:
# https://github.com/python/cpython/blob/67444902a0f10419a557d0a2d3b8675c31b075a9/Lib/collections/__init__.py#L503
def _get_parent_frame():
    """Return the frame object for the caller's parent stack frame."""
    try:
        # Two frames up = the parent of the function which called this.
        return _sys._getframe(2)
    except (AttributeError, ValueError):
        global _get_parent_frame

        def _get_parent_frame():
            """Return the frame object for the caller's parent stack frame."""
            try:
                raise Exception
            except Exception:
                try:
                    return _sys.exc_info()[2].tb_frame.f_back.f_back
                except Exception:
                    global _get_parent_frame

                    def _get_parent_frame():
                        """Return the frame object for the caller's parent stack frame."""
                        return None

                    return _get_parent_frame()

        return _get_parent_frame()
