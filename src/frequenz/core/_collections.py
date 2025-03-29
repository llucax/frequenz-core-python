# License: MIT
# Copyright © 2022 Frequenz Energy-as-a-Service GmbH

"""Utility collections."""

from collections.abc import Callable, Hashable, Iterable, Iterator, MutableSet
from typing import Generic, Self, TypeVar

T = TypeVar("T")
"""Type of the items in the set."""

K = TypeVar("K", bound=Hashable)
"""Type of the keys in the set."""


class SetWithKey(MutableSet, Generic[T, K]):
    """A set that ensures uniqueness based on a specified key function.

    This class works as the built-in `set`, but instead of requiring the items to be
    hashable, it uses a key function to determine if two items are duplicates.

    It is enough to consider items to be present in the set if their key are the same,
    but when mutating the set, items with the same key are compared for equality. If they
    are equal, the item is not added again. If they are not equal, an exception is
    raised instead of adding the item. Optionally items can be replaced if they have the
    same key but are not equal using the optional `replace` argument.

    Examples:
        >>> def get_key(obj):
        ...     return obj.id
        ...
        >>> s = SetWithKey(get_key)
        >>> s.add(obj1)
        >>> s.add(obj2)
    """

    def __init__(
        self,
        iterable: Iterable[T] | None = None,
        *,
        key: Callable[[T], K],
        replace: bool = False,
    ) -> None:
        """Create an instance.

        Args:
            iterable: An optional iterable to initialize the set.
            key: A function that extracts a key from each element.
            replace: Whether to replace existing elements with the same key.

        Raises:
            ValueError: If duplicate keys are found during initialization and
                `replace` is `False`.
        """
        self._key_func = key
        self._items: dict[K, T] = {}
        if iterable is not None:
            for item in iterable:
                self.add(item, replace=replace)

    def __contains__(self, item: T) -> bool:
        """Return whether an item's key is in the set."""
        return self._key_func(item) in self._items

    def __iter__(self) -> Iterator[T]:
        """Return an iterator over the items in the set."""
        return iter(self._items.values())

    def __len__(self) -> int:
        """Return the number of items in the set."""
        return len(self._items)

    def add(self, item: T, *, replace: bool = False) -> None:
        """Add an item to the set.

        If the key of the item to add is the same as the key of an existing item, the
        items are compared for equality. If they are equal, the item is not added again.
        If they are not equal, the item will be added if `replace` is `True`, otherwise
        a `ValueError` will be raised.

        Args:
            item: The item to add.
            replace: Whether to replace existing elements with the same key.

        Raises:
            ValueError: If an item with the same key exists and `replace` is False.
        """
        key = self._key_func(item)
        if key in self._items:
            if self._items[key] == item:
                # Same object, do nothing
                return
            if not replace:
                raise ValueError(f"Duplicate key detected for key: {key}")
        self._items[key] = item

    def discard(self, item: T) -> None:
        """Remove an item from the set if its key exists.

        Args:
            item: The item to remove.
        """
        self._items.pop(self._key_func(item), None)

    def remove(self, item: T) -> None:
        """Remove an item from the set based on its key.

        Args:
            item: The item to remove.

        Raises:
            KeyError: If the item's key is not present.
        """
        key = self._key_func(item)
        try:
            del self._items[key]
        except KeyError as e:
            raise KeyError(f"Item's key not found: {key}") from e

    def pop(self) -> T:
        """Remove and return an arbitrary element from the set.

        Raises:
            KeyError: If the set is empty.

        Returns:
            The removed element.
        """
        if not self._items:
            raise KeyError("pop from an empty SetWithKey")
        _, item = self._items.popitem()
        return item

    def clear(self) -> None:
        """Remove all elements from the set."""
        self._items.clear()

    def __repr__(self) -> str:
        """Return a string representation of the set."""
        items = ", ".join(repr(item) for item in self)
        return f"{self.__class__.__name__}({{{items}}})"

    def __eq__(self, other: object) -> bool:
        """Return whether this set contains the same elements as another set."""
        if isinstance(other, SetWithKey):
            return self._items.keys() == other._items.keys()
        return False

    def __le__(self, other: object) -> bool:
        """Return whether this set is a subset of another set."""
        if isinstance(other, SetWithKey):
            return self._items.keys() <= other._items.keys()
        return False

    def __lt__(self, other: object) -> bool:
        """Return whether this set is a strict subset of another set."""
        if isinstance(other, SetWithKey):
            return self._items.keys() < other._items.keys()
        return False

    def __ge__(self, other: object) -> bool:
        """Return whether this set is a superset of another set."""
        if isinstance(other, SetWithKey):
            return self._items.keys() >= other._items.keys()
        return False

    def __gt__(self, other: object) -> bool:
        """Return whether this set is a strict superset of another set."""
        if isinstance(other, SetWithKey):
            return self._items.keys() > other._items.keys()
        return False

    def union(
        self, *others: MutableSet[T], replace: bool = False
    ) -> Self:  # noqa: DOC502
        """Return a new set with elements from this set and all others.

        Args:
            *others: Other sets to union with.
            replace: Whether to replace existing elements with the same key.

        Returns:
            The union set.

        Raises:
            ValueError: If duplicate keys are found and `replace` is False.
        """
        new_set = type(self)(self, key=self._key_func)
        for other in others:
            for item in other:
                new_set.add(item, replace=replace)
        return new_set

    def intersection(
        self, *others: MutableSet[T], replace: bool = False
    ) -> Self:  # noqa: DOC502
        """Return a new set with elements common to this set and all others.

        Args:
            *others: Other sets to intersect with.
            replace: Whether to replace existing elements with the same key.

        Returns:
            The intersection set.

        Raises:
            ValueError: If duplicate keys are found and `replace` is False.
        """
        new_set = type(self)(self, key=self._key_func)
        for item in self:
            if all(item in other for other in others):
                new_set.add(item, replace=replace)
        return new_set

    def difference(self, *others: MutableSet[T], replace: bool = False) -> Self:
        """Return a new set with elements in this set that are not in the others.

        Args:
            *others: Other sets to difference with.
            replace: Whether to replace existing elements with the same key.

        Returns:
            The difference set.
        """
        new_set = type(self)(self, key=self._key_func)
        for item in self:
            if not any(item in other for other in others):
                new_set.add(item, replace=replace)
        return new_set

    def symmetric_difference(self, other: MutableSet[T], replace: bool = False) -> Self:
        """Return a new set with elements in either this set or other but not both.

        Args:
            other: The other set to symmetric difference with.
            replace: Whether to replace existing elements with the same key.

        Returns:
            The symmetric difference set.
        """
        new_set = type(self)(self, key=self._key_func)
        for item in self:
            if item not in other:
                new_set.add(item, replace=replace)
        for item in other:
            if item not in self:
                new_set.add(item, replace=replace)
        return new_set

    def update(  # noqa: DOC502
        self, *others: MutableSet[T], replace: bool = False
    ) -> None:
        """Update this set, adding elements from all others.

        Args:
            *others: Other sets to add elements from.
            replace: Whether to replace existing elements with the same key.

        Raises:
            ValueError: If duplicate keys are found and `replace` is False.
        """
        for other in others:
            for item in other:
                self.add(item, replace=replace)

    def intersection_update(
        self, *others: MutableSet[T], replace: bool = False
    ) -> None:
        """Update this set to keep only elements found in it and all others.

        Args:
            *others: Other sets to intersect with.
            replace: Whether to replace existing elements with the same key.

        Raises:
            ValueError: If duplicate keys are found and `replace` is False.
        """
        keys_to_remove = set()
        for key, item in self._items.items():
            if not all(item in other for other in others):
                keys_to_remove.add(key)
        for key in keys_to_remove:
            del self._items[key]

    def difference_update(self, *others: MutableSet[T], replace: bool = False) -> None:
        """Update this set by removing elements found in the others.

        Args:
            *others: Other sets to remove elements from.
        """
        keys_to_remove = set()
        for other in others:
            for item in other:
                key = self._key_func(item)
                existing = self._items.get(key)
                if existing is item:
                    keys_to_remove.add(key)
        for key in keys_to_remove:
            del self._items[key]

    def symmetric_difference_update(
        self, other: MutableSet[T], replace: bool = False
    ) -> None:
        """Update this set with the symmetric difference of itself and other.

        Args:
            other (MutableSet[T]): The other set to symmetric difference with.
        """
        to_add = set()
        to_remove = set()
        for item in other:
            key = self._key_func(item)
            if key in self._items:
                existing = self._items[key]
                if existing is not item:
                    to_remove.add(key)
            else:
                to_add.add(item)
        for key in to_remove:
            del self._items[key]
        for item in to_add:
            self._items[self._key_func(item)] = item
