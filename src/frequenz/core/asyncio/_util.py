# License: MIT
# Copyright © 2024 Frequenz Energy-as-a-Service GmbH

"""General purpose async utilities."""


import asyncio
import collections.abc
import contextvars
from typing import Any, Protocol, TypeVar, runtime_checkable

TaskReturnT = TypeVar("TaskReturnT")
"""The type of the return value of a task."""


@runtime_checkable
class TaskCreator(Protocol):
    """A protocol for creating tasks.

    Built-in asyncio functions and classes implementing this protocol:

    - [`asyncio`][]
    - [`asyncio.AbstractEventLoop`][] (returned by [`asyncio.get_event_loop`][] for
      example)
    - [`asyncio.TaskGroup`][]
    """

    def create_task(
        self,
        coro: collections.abc.Coroutine[Any, Any, TaskReturnT],
        *,
        name: str | None = None,
        context: contextvars.Context | None = None,
    ) -> asyncio.Task[TaskReturnT]:
        """Create a task.

        Args:
            coro: The coroutine to be executed.
            name: The name of the task.
            context: The context to be used for the task.

        Returns:
            The new task.
        """
        ...  # pylint: disable=unnecessary-ellipsis


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
