# License: MIT
# Copyright © 2024 Frequenz Energy-as-a-Service GmbH

"""Type hints and utility functions for type checking and types.

For now this module only provides a decorator to disable the `__init__` constructor of
a class, to force the use of a factory method to create instances. See
[disable_init][frequenz.core.typing.disable_init] for more information.
"""

from collections.abc import Callable
from typing import Any, NoReturn, TypeVar, cast, overload

TypeT = TypeVar("TypeT", bound=type)
"""A type variable that is bound to a type."""


@overload
def disable_init(
    cls: None = None,
    *,
    error: Exception | None = None,
) -> Callable[[TypeT], TypeT]: ...


@overload
def disable_init(cls: TypeT) -> TypeT: ...


def disable_init(
    cls: TypeT | None = None,
    *,
    error: Exception | None = None,
) -> TypeT | Callable[[TypeT], TypeT]:
    """Disable the `__init__` constructor of a class.

    This decorator can be used to disable the `__init__` constructor of a class. It is
    intended to be used with classes that don't provide a default constructor and
    require the use of a factory method to create instances.

    When marking a class with this decorator, the class cannot be even declared with a
    `__init__` method, as it will raise a `TypeError` when the class is created, as soon
    as the class is parsed by the Python interpreter. It will also raise a `TypeError`
    when the `__init__` method is called.

    To create an instance you must provide a factory method, using `__new__`.

    Warning:
        This decorator will use a custom metaclass to disable the `__init__` constructor
        of the class, so if your class already uses a custom metaclass, you should be
        aware of potential conflicts.

    Example: Basic example defining a class with a factory method
        To be able to type hint the class correctly, you can declare the instance
        attributes in the class body, and then use a factory method to create instances.

        ```python
        from typing import Self

        @disable_init
        class MyClass:
            value: int

            @classmethod
            def new(cls, value: int = 1) -> Self:
                self = cls.__new__(cls)
                self.value = value
                return self

        instance = MyClass.new()

        # Calling the default constructor (__init__) will raise a TypeError
        try:
            instance = MyClass()
        except TypeError as e:
            print(e)
        ```

    Example: Class wrongly providing an `__init__` constructor
        ```python
        try:
            @disable_init
            class MyClass:
                def __init__(self) -> None:
                    pass
        except TypeError as e:
            assert isinstance(e, TypeError)
            print(e)
        ```

    Example: Using a custom error message when the default constructor is called
        ```python
        from typing import Self

        class NoInitError(TypeError):
            def __init__(self) -> None:
                super().__init__("Please create instances of MyClass using MyClass.new()")

        @disable_init(error=NoInitError())
        class MyClass:
            @classmethod
            def new(cls) -> Self:
                return cls.__new__(cls)

        try:
            instance = MyClass()
        except NoInitError as e:
            assert str(e) == "Please create instances of MyClass using MyClass.new()"
            print(e)
        ```

    Args:
        cls: The class to be decorated.
        error: The error to raise if __init__ is called, if `None` a default
            [TypeError][] will be raised.

    Returns:
        A decorator that disables the `__init__` constructor of `cls`.
    """

    def decorator(inner_cls: TypeT) -> TypeT:
        return cast(
            TypeT,
            _NoInitConstructibleMeta(
                inner_cls.__name__,
                inner_cls.__bases__,
                dict(inner_cls.__dict__),
                no_init_constructible_error=error,
            ),
        )

    if cls is None:
        return decorator
    return decorator(cls)


class _NoInitConstructibleMeta(type):
    """A metaclass that disables the __init__ constructor."""

    def __new__(
        mcs,
        name: str,
        bases: tuple[type, ...],
        namespace: dict[str, Any],
        **kwargs: Any,
    ) -> type:
        """Create a new class with a disabled __init__ constructor.

        Args:
            name: The name of the new class.
            bases: The base classes of the new class.
            namespace: The namespace of the new class.
            **kwargs: Additional keyword arguments.

        Returns:
            The new class with a disabled __init__ constructor.

        Raises:
            TypeError: If the class provides a default constructor.
        """
        if "__init__" in namespace:
            raise _get_no_init_constructible_error(name, bases, kwargs)
        return super().__new__(mcs, name, bases, namespace)

    def __init__(
        cls,
        name: str,
        bases: tuple[type, ...],
        namespace: dict[str, Any],
        **kwargs: Any,
    ) -> None:
        """Initialize the new class."""
        super().__init__(name, bases, namespace)
        cls._no_init_constructible_error = kwargs.get("no_init_constructible_error")

    def __call__(cls, *args: Any, **kwargs: Any) -> NoReturn:
        """Raise an error when the __init__ constructor is called.

        Args:
            *args: ignored positional arguments.
            **kwargs: ignored keyword arguments.

        Raises:
            TypeError: Always.
        """
        raise _get_no_init_constructible_error(
            cls.__name__,
            cls.__bases__,
            {"no_init_constructible_error": cls._no_init_constructible_error},
        )


def _get_no_init_constructible_error(
    name: str, bases: tuple[type, ...], kwargs: Any
) -> Exception:
    error = kwargs.get("no_init_constructible_error")
    if error is None:
        for base in bases:
            if attr := getattr(base, "_no_init_constructible_error", None):
                error = attr
                break
        else:
            error = TypeError(
                f"{name} doesn't provide a default constructor, you must use a "
                "factory method to create instances."
            )
    assert isinstance(error, Exception)
    return error
