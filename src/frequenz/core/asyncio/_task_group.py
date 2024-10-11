# License: MIT
# Copyright © 2024 Frequenz Energy-as-a-Service GmbH

"""Module implementing the `PersistentTaskGroup` class."""


import asyncio
import contextvars
import datetime
import logging
from collections.abc import AsyncIterator, Coroutine, Generator, Set
from types import TracebackType
from typing import Any, Self

from ._util import TaskCreator, TaskReturnT

_logger = logging.getLogger(__name__)


class PersistentTaskGroup:
    """A group of tasks that should run until explicitly stopped.

    [`asyncio.TaskGroup`][] is a very convenient construct when using parallelization
    for doing calculations for example, where the results for all the tasks need to be
    merged together to produce a final result. In this case if one of the tasks fails,
    it makes sense to cancel the others and abort as soon as possible, as any further
    calculations would be thrown away.

    This class is intended to help managing a group of tasks that should persist even if
    other tasks in the group fail, usually by either only discarding the failed task or
    by restarting it somehow.

    This class is also typically used as a context manager, but in this case when the
    context manager is exited, the tasks are not only awaited, they are first cancelled,
    so all the background tasks are stopped. If any task was ended due to an unhandled
    exception, the exception will be re-raised when the context manager exits as
    [`BaseExceptionGroup`][].

    As with [`asyncio.TaskGroup`][], the tasks should be created using the
    [`create_task()`][frequenz.core.asyncio.PersistentTaskGroup.create_task] method.

    To monitor the subtasks and handle exceptions or early termination,
    a [`as_completed()`][frequenz.core.asyncio.PersistentTaskGroup.as_completed] method
    is provided, similar to [`asyncio.as_completed`][] but not quite the same. Using
    this method is the only way to acknowledge tasks failures, so they are not raised
    when the service is `await`ed or when the context manager is exited.

    Example:
        This program will run forever, printing the current time now and then and
        restarting the failing task each time it crashes.

        ```python
        import asyncio
        import datetime

        async def print_every(*, seconds: float) -> None:
            while True:
                await asyncio.sleep(seconds)
                print(datetime.datetime.now())

        async def fail_after(*, seconds: float) -> None:
            await asyncio.sleep(seconds)
            raise ValueError("I failed")

        async def main() -> None:

            async with PersistentTaskGroup() as group:
                group.create_task(print_every(seconds=1), name="print_1")
                group.create_task(print_every(seconds=11), name="print_11")
                failing = group.create_task(fail_after(seconds=5), name=f"fail_5")

                async for task in group.as_completed():
                    assert task.done()  # For demonstration purposes only
                    try:
                        task.result()
                    except ValueError as error:
                        if failing == task:
                            failing = group.create_task(fail_after(seconds=5), name=f"fail_5")
                        else:
                            raise

        asyncio.run(main())
        ```
    """

    def __init__(
        self, *, unique_id: str | None = None, task_creator: TaskCreator = asyncio
    ) -> None:
        """Initialize this instance.

        Args:
            unique_id: The string to uniquely identify this instance. If `None`,
                a string based on `hex(id(self))` will be used. This is used in
                `__repr__` and `__str__` methods, mainly for debugging purposes, to
                identify a particular instance of a persistent task group.
            task_creator: The object that will be used to create tasks. Usually one of:
                the [`asyncio`]() module, an [`asyncio.AbstractEventLoop`]() or
                an [`asyncio.TaskGroup`]().
        """
        # [2:] is used to remove the '0x' prefix from the hex representation of the id,
        # as it doesn't add any uniqueness to the string.
        self._unique_id: str = hex(id(self))[2:] if unique_id is None else unique_id
        """The unique ID of this instance."""

        self._task_creator: TaskCreator = task_creator
        """The object that will be used to create tasks."""

        self._running: set[asyncio.Task[Any]] = set()
        """The set of tasks that are still running.

        Tasks are removed from this set automatically when they finish using the
        Task.add_done_callback method.
        """

        self._waiting_ack: set[asyncio.Task[Any]] = set()
        """The set of tasks that have finished but waiting for the user's ACK.

        Tasks are added to this set automatically when they finish using the
        Task.add_done_callback method.
        """

    @property
    def unique_id(self) -> str:
        """The unique ID of this instance."""
        return self._unique_id

    @property
    def tasks(self) -> Set[asyncio.Task[Any]]:
        """The set of tasks managed by this group.

        Users typically should not modify the tasks in the returned set and only use
        them for informational purposes.

        Both running tasks and tasks pending for acknowledgment are included in the
        returned set.

        Danger:
            Changing the returned tasks may lead to unexpected behavior, don't do it
            unless the class explicitly documents it is safe to do so.
        """
        return self._running | self._waiting_ack

    @property
    def task_creator(self) -> TaskCreator:
        """The object that will be used to create tasks."""
        return self._task_creator

    @property
    def is_running(self) -> bool:
        """Whether this task group is running.

        A task group is considered running when at least one task is running.
        """
        return bool(self._running)

    def create_task(
        self,
        coro: Coroutine[Any, Any, TaskReturnT],
        *,
        name: str | None = None,
        context: contextvars.Context | None = None,
        log_exception: bool = True,
    ) -> asyncio.Task[TaskReturnT]:
        """Start a managed task.

        A reference to the task will be held by the task group, so there is no need to
        save the task object.

        Tasks can be retrieved via the
        [`tasks`][frequenz.core.asyncio.PersistentTaskGroup.tasks] property.

        Managed tasks always have a `name` including information about the task group
        itself. If you need to retrieve the final name of the task you can always do so
        by calling [`.get_name()`][asyncio.Task.get_name] on the returned task.

        Tasks created this way will also be automatically cancelled when calling
        [`cancel()`][frequenz.core.asyncio.ServiceBase.cancel] or
        [`stop()`][frequenz.core.asyncio.ServiceBase.stop], or when the service is used
        as a async context manager.

        To inform that a finished task was properly handled, the method
        [`as_completed()`][frequenz.core.asyncio.PersistentTaskGroup.as_completed]
        should be used.

        Args:
            coro: The coroutine to be managed.
            name: The name of the task. Names will always have the form
                `f"{self}:{name}"`. If `None` or empty, the default name will be
                `hex(id(coro))[2:]`. If you need the final name of the task, it can
                always be retrieved
            context: The context to be used for the task.
            log_exception: Whether to log exceptions raised by the task.

        Returns:
            The new task.
        """
        if not name:
            name = hex(id(coro))[2:]
        task = self._task_creator.create_task(
            coro, name=f"{self}:{name}", context=context
        )
        self._running.add(task)
        task.add_done_callback(self._running.discard)
        task.add_done_callback(self._waiting_ack.add)

        if log_exception:

            def _log_exception(task: asyncio.Task[TaskReturnT]) -> None:
                try:
                    task.result()
                except asyncio.CancelledError:
                    pass
                except BaseException:  # pylint: disable=broad-except
                    _logger.exception(
                        "Task %s raised an unhandled exception", task.get_name()
                    )

            task.add_done_callback(_log_exception)
        return task

    def cancel(self, msg: str | None = None) -> None:
        """Cancel all running tasks spawned by this group.

        Args:
            msg: The message to be passed to the tasks being cancelled.
        """
        for task in self._running:
            task.cancel(msg)

    # We need to use noqa here because pydoclint can't figure out that rest is actually
    # an instance of BaseExceptionGroup.
    async def stop(self, msg: str | None = None) -> None:  # noqa: DOC503
        """Stop this task group.

        This method cancels all running tasks spawned by this group and waits for them
        to finish.

        Args:
            msg: The message to be passed to the tasks being cancelled.

        Raises:
            BaseExceptionGroup: If any of the tasks spawned by this group raised an
                exception.
        """
        self.cancel(msg)
        try:
            await self
        except BaseExceptionGroup as exc_group:
            # We want to ignore CancelledError here as we explicitly cancelled all the
            # tasks.
            _, rest = exc_group.split(asyncio.CancelledError)
            if rest is not None:
                # We are filtering out from an exception group, we really don't want to
                # add the exceptions we just filtered by adding a from clause here.
                raise rest  # pylint: disable=raise-missing-from

    async def as_completed(
        self, *, timeout: float | datetime.timedelta | None = None
    ) -> AsyncIterator[asyncio.Task[Any]]:
        """Iterate over running tasks yielding as they complete.

        Stops iterating when there are no more running tasks and all done tasks have
        been acknowledged, or if the timeout is reached.

        Note:
            If an exception is raised while yielding a task, the task will be considered
            not handled and will be yielded again until it is handled without raising
            any exceptions.

        Args:
            timeout: The maximum time to wait for the next task to complete. If `None`,
                the function will wait indefinitely.

        Yields:
            The tasks as they complete.
        """
        while True:
            while task := next(iter(self._waiting_ack), None):
                yield task
                # We discard instead of removing in case someone else already ACKed
                # the task.
                self._waiting_ack.discard(task)

            if not self._running:
                break

            done, _ = await asyncio.wait(
                self._running,
                return_when=asyncio.FIRST_COMPLETED,
                timeout=(
                    timeout.total_seconds()
                    if isinstance(timeout, datetime.timedelta)
                    else timeout
                ),
            )

            if not done:  # wait timed out
                break

            # We don't need to add done tasks to _waiting_ack, as they are added there
            # automatically via add_done_callback().

    async def __aenter__(self) -> Self:
        """Enter an async context.

        Returns:
            This instance.
        """
        return self

    async def __aexit__(  # noqa: DOC502
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> bool | None:
        """Exit an async context.

        Stop this instance.

        Args:
            exc_type: The type of the exception raised, if any.
            exc_val: The exception raised, if any.
            exc_tb: The traceback of the exception raised, if any.

        Returns:
            Whether the exception was handled.

        Raises:
            BaseExceptionGroup: If any of the tasks spawned by this group raised an
                exception.
        """
        await self.stop()
        return None

    async def _wait(self) -> None:
        """Wait for this instance to finish.

        Wait until all the group tasks are finished.

        Raises:
            BaseExceptionGroup: If any of the tasks spawned by this group raised an
                exception.
        """
        exceptions: list[BaseException] = []

        async for task in self.as_completed():
            try:
                await task
            except BaseException as error:  # pylint: disable=broad-except
                exceptions.append(error)

        if exceptions:
            raise BaseExceptionGroup(f"Error while stopping {self}", exceptions)

    def __await__(self) -> Generator[None, None, None]:  # noqa: DOC502
        """Await for all tasks managed by this group to finish.

        Returns:
            An implementation-specific generator for the awaitable.

        Raises:
            BaseExceptionGroup: If any of the tasks spawned by this group raised an
                exception.
        """
        return self._wait().__await__()

    def __del__(self) -> None:
        """Destroy this instance.

        Cancel all running tasks spawned by this group.
        """
        self.cancel("{self!r} was deleted")

    def __repr__(self) -> str:
        """Return a string representation of this instance.

        Returns:
            A string representation of this instance.
        """
        details = ""
        if self._running:
            details += f" running={len(self._running)}"
        if self._waiting_ack:
            details += f" waiting_ack={len(self._waiting_ack)}"
        return f"{type(self).__name__}<{self.unique_id}{details}>"

    def __str__(self) -> str:
        """Return a string representation of this instance.

        Returns:
            A string representation of this instance.
        """
        return f"{type(self).__name__}:{self._unique_id}"
