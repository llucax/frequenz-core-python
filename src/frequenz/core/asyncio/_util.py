# License: MIT
# Copyright © 2024 Frequenz Energy-as-a-Service GmbH

"""General purpose async utilities."""


import asyncio
from typing import Any, TypeVar

TaskReturnT = TypeVar("TaskReturnT")
"""The type of the return value of a task."""


def get_unique_id(unique_id: str | None, instance: Any) -> str:
    """Get a unique identifier for an instance.

    If a `unique_id` is provided, it is returned as is. Otherwise, a string based on
    `hex(id(instance))` is returned.

    Args:
        unique_id: The unique identifier to use.
        instance: The instance to get the `id` from if `unique_id` is `None`.

    Returns:
        A unique identifier for the instance.
    """
    # [2:] is used to remove the '0x' prefix from the hex representation of the id, as
    # it doesn't add any uniqueness to the string.
    return hex(id(instance))[2:] if unique_id is None else unique_id


async def cancel_and_await(task: asyncio.Task[Any]) -> None:
    """Cancel a task and wait for it to finish.

    Exits immediately if the task is already done.

    The `CancelledError` is suppressed, but any other exception will be propagated.

    Args:
        task: The task to be cancelled and waited for.
    """
    if task.done():
        return
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
