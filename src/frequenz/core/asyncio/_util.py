# License: MIT
# Copyright © 2024 Frequenz Energy-as-a-Service GmbH

"""General purpose async utilities."""


import asyncio
from typing import Any, TypeVar

TaskReturnT = TypeVar("TaskReturnT")
"""The type of the return value of a task."""


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
