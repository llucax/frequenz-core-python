# License: MIT
# Copyright © 2024 Frequenz Energy-as-a-Service GmbH

"""Test cases for the typing module."""

from typing import Self

import pytest

from frequenz.core.typing import disable_init


def test_disable_init_declaration_with_custom_error() -> None:
    """Test that the custom error is raised when trying to declare the class."""

    class CustomError(TypeError):
        """Custom error to raise when trying to declare the class."""

        def __init__(self) -> None:
            """Initialize the custom error."""
            super().__init__("Please use the factory method to create instances.")

    with pytest.raises(
        CustomError, match="Please use the factory method to create instances."
    ):

        @disable_init(error=CustomError())
        class MyClass:
            """Base class that doesn't provide a default constructor."""

            def __init__(self) -> None:
                """Raise an exception when parsed."""


def test_disable_init_instantiation_with_custom_error() -> None:
    """Test that the custom error is raised when trying to instantiate the class."""

    class CustomError(TypeError):
        """Custom error to raise when trying to instantiate the class."""

        def __init__(self) -> None:
            """Initialize the custom error."""
            super().__init__("Please use the factory method to create instances.")

    @disable_init(error=CustomError())
    class MyClass:
        """Base class that doesn't provide a default constructor."""

    with pytest.raises(
        CustomError, match="Please use the factory method to create instances."
    ):
        _ = MyClass()


def test_disable_init_declaration_subclass_with_custom_error() -> None:
    """Test that the custom error is raised when trying to declare a subclass."""

    class CustomError(TypeError):
        """Custom error to raise when trying to declare the class."""

        def __init__(self) -> None:
            """Initialize the custom error."""
            super().__init__("Please use the factory method to create instances.")

    @disable_init(error=CustomError())
    class MyClass:
        """Base class that doesn't provide a default constructor."""

    with pytest.raises(
        CustomError, match="Please use the factory method to create instances."
    ):

        class Sub(MyClass):
            """Base class that doesn't provide a default constructor."""

            def __init__(self) -> None:
                """Raise an exception when parsed."""


def test_disable_init_instantiation_subclass_with_custom_error() -> None:
    """Test that the custom error is raised when trying to instantiate a subclass."""

    class CustomError(TypeError):
        """Custom error to raise when trying to instantiate the class."""

        def __init__(self) -> None:
            """Initialize the custom error."""
            super().__init__("Please use the factory method to create instances.")

    @disable_init(error=CustomError())
    class MyClass:
        """Base class that doesn't provide a default constructor."""

    class Sub(MyClass):
        """Subclass that doesn't provide a default constructor."""

    with pytest.raises(
        CustomError, match="Please use the factory method to create instances."
    ):
        _ = Sub()


def test_disable_init_default_error() -> None:
    """Test that the default error is raised when trying to instantiate the class."""

    @disable_init
    class MyClass:
        """Base class that doesn't provide a default constructor."""

        @classmethod
        def new(cls) -> Self:
            """Create a new instance of the class."""
            return cls.__new__(cls)

    with pytest.raises(
        TypeError,
        match="MyClass doesn't provide a default constructor, you must use a "
        "factory method to create instances.",
    ):
        MyClass()

    instance = MyClass.new()
    assert isinstance(instance, MyClass)


def test_disable_init_subclass() -> None:
    """Test that the default error is raised when trying to instantiate a subclass."""

    @disable_init
    class MyClass:
        """Base class that doesn't provide a default constructor."""

        @classmethod
        def new(cls) -> Self:
            return cls.__new__(cls)

    class Sub(MyClass):
        """Subclass that doesn't provide a default constructor."""

    with pytest.raises(
        TypeError,
        match=r"Sub doesn't provide a default constructor, you must use a factory "
        "method to create instances.",
    ):
        Sub()

    instance = Sub.new()
    assert isinstance(instance, Sub)


def test_disable_init_subclass_with_init() -> None:
    """Test that the default error is raised when trying to instantiate a subclass."""

    @disable_init
    class MyClass:
        """Base class that doesn't provide a default constructor."""

    with pytest.raises(
        TypeError,
        match=r"Sub doesn't provide a default constructor, you must use a factory "
        "method to create instances.",
    ):

        class Sub(MyClass):
            """Subclass that doesn't provide a default constructor."""

            def __init__(self) -> None:
                """Raise an exception when parsed."""


def test_disable_init_no_init_allowed() -> None:
    """Test that the default error is raised when trying to define an __init__ method."""
    with pytest.raises(
        TypeError,
        match="MyClass doesn't provide a default constructor, you must use a "
        "factory method to create instances.",
    ):

        @disable_init
        class MyClass:
            """Base class that doesn't provide a default constructor."""

            def __init__(self) -> None:
                """Raise an exception when parsed."""


def test_disable_init_with_factory_method() -> None:
    """Test that the factory method works when used to create instances."""

    @disable_init
    class MyClass:
        """Base class that doesn't provide a default constructor."""

        value: int

        @classmethod
        def new(cls, value: int = 1) -> Self:
            """Create a new instance of the class."""
            self = cls.__new__(cls)
            self.value = value
            return self

    instance = MyClass.new(42)
    assert isinstance(instance, MyClass)
    assert instance.value == 42
