# License: MIT
# Copyright © 2024 Frequenz Energy-as-a-Service GmbH

"""General purpose async tools.

This module provides general purpose async tools that can be used to simplify the
development of asyncio-based applications.

The module provides the following classes and functions:

- [cancel_and_await][frequenz.core.asyncio.cancel_and_await]: A function that cancels a
  task and waits for it to finish, handling `CancelledError` exceptions.
- [Service][frequenz.core.asyncio.Service]: An interface for services running in the
  background.
- [ServiceBase][frequenz.core.asyncio.ServiceBase]: A base class for implementing
  services running in the background.
- [TaskCreator][frequenz.core.asyncio.TaskCreator]: A protocol for creating tasks.
"""


import abc
import asyncio
import collections.abc
import contextvars
import logging
from types import TracebackType
from typing import Any, Protocol, Self, TypeVar, runtime_checkable

from typing_extensions import override

_logger = logging.getLogger(__name__)


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


class Service(abc.ABC):
    """A service running in the background.

    A service swpawns one of more background tasks and can be
    [started][frequenz.core.asyncio.Service.start] and
    [stopped][frequenz.core.asyncio.Service.stop] and can work as an async context
    manager to provide deterministic cleanup.

    Warning:
        As services manage [`asyncio.Task`][] objects, a reference to a running service
        must be held for as long as the service is expected to be running. Otherwise, its
        tasks will be cancelled and the service will stop. For more information, please
        refer to the [Python `asyncio`
        documentation](https://docs.python.org/3/library/asyncio-task.html#asyncio.create_task).

    Example:
        ```python
        async def as_context_manager(service: Service) -> None:
            async with service:
                assert service.is_running
                await asyncio.sleep(5)
            assert not service.is_running

        async def manual_start_stop(service: Service) -> None:
            # Use only if necessary, as cleanup is more complicated
            service.start()
            await asyncio.sleep(5)
            await service.stop()
        ```
    """

    @abc.abstractmethod
    def start(self) -> None:
        """Start this service."""

    @property
    @abc.abstractmethod
    def unique_id(self) -> str:
        """The unique ID of this service."""

    @property
    @abc.abstractmethod
    def tasks(self) -> collections.abc.Set[asyncio.Task[Any]]:
        """The set of running tasks spawned by this service.

        Users typically should not modify the tasks in the returned set and only use
        them for informational purposes.

        Danger:
            Changing the returned tasks may lead to unexpected behavior, don't do it
            unless the class explicitly documents it is safe to do so.
        """

    @property
    @abc.abstractmethod
    def is_running(self) -> bool:
        """Whether this service is running.

        A service is considered running when at least one task is running.
        """

    @abc.abstractmethod
    def cancel(self, msg: str | None = None) -> None:
        """Cancel all running tasks spawned by this service.

        Args:
            msg: The message to be passed to the tasks being cancelled.
        """

    @abc.abstractmethod
    async def stop(self, msg: str | None = None) -> None:  # noqa: DOC502
        """Stop this service.

        This method cancels all running tasks spawned by this service and waits for them
        to finish.

        Args:
            msg: The message to be passed to the tasks being cancelled.

        Raises:
            BaseExceptionGroup: If any of the tasks spawned by this service raised an
                exception.
        """

    @abc.abstractmethod
    async def __aenter__(self) -> Self:
        """Enter an async context.

        Start this service.

        Returns:
            This service.
        """

    @abc.abstractmethod
    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> bool | None:
        """Exit an async context.

        Stop this service.

        Args:
            exc_type: The type of the exception raised, if any.
            exc_val: The exception raised, if any.
            exc_tb: The traceback of the exception raised, if any.

        Returns:
            Whether the exception was handled.
        """

    @abc.abstractmethod
    def __await__(self) -> collections.abc.Generator[None, None, None]:  # noqa: DOC502
        """Wait for this service to finish.

        Wait until all the service tasks are finished.

        Returns:
            An implementation-specific generator for the awaitable.

        Raises:
            BaseExceptionGroup: If any of the tasks spawned by this service raised an
                exception (`CancelError` is not considered an error and not returned in
                the exception group).
        """


class ServiceBase(Service, abc.ABC):
    """A base class for implementing a service running in the background.

    To implement a service, subclasses must implement the
    [`start()`][frequenz.core.asyncio.ServiceBase.start] method, which should start the
    background tasks needed by the service using the
    [`create_task()`][frequenz.core.asyncio.ServiceBase.create_task] method.

    If you need to collect results or handle exceptions of the tasks when stopping the
    service, then you need to also override the
    [`stop()`][frequenz.core.asyncio.ServiceBase.stop] method, as the base
    implementation does not collect any results and re-raises all exceptions.

    Example:
        ```python
        import datetime
        import asyncio

        class Clock(ServiceBase):
            def __init__(self, resolution_s: float, *, unique_id: str | None = None) -> None:
                super().__init__(unique_id=unique_id)
                self._resolution_s = resolution_s

            def start(self) -> None:
                # Managed tasks are automatically saved, so there is no need to hold a
                # reference to them if you don't need to further interact with them.
                self.create_task(self._tick())

            async def _tick(self) -> None:
                while True:
                    await asyncio.sleep(self._resolution_s)
                    print(datetime.datetime.now())

        async def main() -> None:
            # As an async context manager
            async with Clock(resolution_s=1):
                await asyncio.sleep(5)

            # Manual start/stop (only use if necessary, as cleanup is more complicated)
            clock = Clock(resolution_s=1)
            clock.start()
            await asyncio.sleep(5)
            await clock.stop()

        asyncio.run(main())
        ```
    """

    def __init__(
        self, *, unique_id: str | None = None, task_creator: TaskCreator = asyncio
    ) -> None:
        """Initialize this Service.

        Args:
            unique_id: The string to uniquely identify this service instance.
                If `None`, a string based on `hex(id(self))` will be used. This is
                used in `__repr__` and `__str__` methods, mainly for debugging
                purposes, to identify a particular instance of a service.
            task_creator: The object that will be used to create tasks. Usually one of:
                the [`asyncio`]() module, an [`asyncio.AbstractEventLoop`]() or
                an [`asyncio.TaskGroup`]().
        """
        # [2:] is used to remove the '0x' prefix from the hex representation of the id,
        # as it doesn't add any uniqueness to the string.
        self._unique_id: str = hex(id(self))[2:] if unique_id is None else unique_id
        self._tasks: set[asyncio.Task[Any]] = set()
        self._task_creator: TaskCreator = task_creator

    @override
    @abc.abstractmethod
    def start(self) -> None:
        """Start this service."""

    @property
    @override
    def unique_id(self) -> str:
        """The unique ID of this service."""
        return self._unique_id

    @property
    @override
    def tasks(self) -> collections.abc.Set[asyncio.Task[Any]]:
        """The set of running tasks spawned by this service.

        Users typically should not modify the tasks in the returned set and only use
        them for informational purposes.

        Danger:
            Changing the returned tasks may lead to unexpected behavior, don't do it
            unless the class explicitly documents it is safe to do so.
        """
        return self._tasks

    @property
    @override
    def is_running(self) -> bool:
        """Whether this service is running.

        A service is considered running when at least one task is running.
        """
        return any(not task.done() for task in self._tasks)

    def create_task(
        self,
        coro: collections.abc.Coroutine[Any, Any, TaskReturnT],
        *,
        name: str | None = None,
        context: contextvars.Context | None = None,
        log_exception: bool = True,
    ) -> asyncio.Task[TaskReturnT]:
        """Start a managed task.

        A reference to the task will be held by the service, so there is no need to save
        the task object.

        Tasks can be retrieved via the
        [`tasks`][frequenz.core.asyncio.ServiceBase.tasks] property.

        Managed tasks always have a `name` including information about the service
        itself. If you need to retrieve the final name of the task you can always do so
        by calling [`.get_name()`][asyncio.Task.get_name] on the returned task.

        Tasks created this way will also be automatically cancelled when calling
        [`cancel()`][frequenz.core.asyncio.ServiceBase.cancel] or
        [`stop()`][frequenz.core.asyncio.ServiceBase.stop], or when the service is used
        as a async context manager.

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
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

        if log_exception:

            def _log_exception(task: asyncio.Task[TaskReturnT]) -> None:
                try:
                    task.result()
                except asyncio.CancelledError:
                    pass
                except BaseException:  # pylint: disable=broad-except
                    _logger.exception("%s: Task %r raised an exception", self, task)

            task.add_done_callback(_log_exception)
        return task

    @override
    def cancel(self, msg: str | None = None) -> None:
        """Cancel all running tasks spawned by this service.

        Args:
            msg: The message to be passed to the tasks being cancelled.
        """
        for task in self._tasks:
            task.cancel(msg)

    @override
    async def stop(self, msg: str | None = None) -> None:
        """Stop this service.

        This method cancels all running tasks spawned by this service and waits for them
        to finish.

        Args:
            msg: The message to be passed to the tasks being cancelled.

        Raises:
            BaseExceptionGroup: If any of the tasks spawned by this service raised an
                exception.
        """
        if not self._tasks:
            return
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

    @override
    async def __aenter__(self) -> Self:
        """Enter an async context.

        Start this service.

        Returns:
            This service.
        """
        self.start()
        return self

    @override
    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> bool | None:
        """Exit an async context.

        Stop this service.

        Args:
            exc_type: The type of the exception raised, if any.
            exc_val: The exception raised, if any.
            exc_tb: The traceback of the exception raised, if any.

        Returns:
            Whether the exception was handled.
        """
        await self.stop()
        return None

    async def _wait(self) -> None:
        """Wait for this service to finish.

        Wait until all the service tasks are finished.

        Raises:
            BaseExceptionGroup: If any of the tasks spawned by this service raised an
                exception (`CancelError` is not considered an error and not returned in
                the exception group).
        """
        # We need to account for tasks that were created between when we started
        # awaiting and we finished awaiting.
        while self._tasks:
            done, pending = await asyncio.wait(self._tasks)
            assert not pending

            # We remove the done tasks, but there might be new ones created after we
            # started waiting.
            self._tasks = self._tasks - done

            exceptions: list[BaseException] = []
            for task in done:
                try:
                    # This will raise a CancelledError if the task was cancelled or any
                    # other exception if the task raised one.
                    _ = task.result()
                except BaseException as error:  # pylint: disable=broad-except
                    exceptions.append(error)
            if exceptions:
                raise BaseExceptionGroup(
                    f"Error while stopping service {self}", exceptions
                )

    @override
    def __await__(self) -> collections.abc.Generator[None, None, None]:
        """Await this service.

        An awaited service will wait for all its tasks to finish.

        Returns:
            An implementation-specific generator for the awaitable.
        """
        return self._wait().__await__()

    def __del__(self) -> None:
        """Destroy this instance.

        Cancel all running tasks spawned by this service.
        """
        self.cancel(f"{self!r} was deleted")

    def __repr__(self) -> str:
        """Return a string representation of this instance.

        Returns:
            A string representation of this instance.
        """
        return f"{type(self).__name__}<{self._unique_id} tasks={self._tasks!r}>"

    def __str__(self) -> str:
        """Return a string representation of this instance.

        Returns:
            A string representation of this instance.
        """
        return f"{type(self).__name__}[{self._unique_id}]"
