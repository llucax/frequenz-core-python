# License: MIT
# Copyright © 2024 Frequenz Energy-as-a-Service GmbH

"""Module implementing the `Service` and `ServiceBase` classes."""


import abc
import asyncio
import collections.abc
import contextvars
import datetime
import enum
import logging
from collections.abc import AsyncIterator, Generator
from dataclasses import dataclass
from types import TracebackType
from typing import Any, Self

from typing_extensions import override

from ._task_group import PersistentTaskGroup
from ._util import TaskReturnT, get_unique_id

_logger = logging.getLogger(__name__)

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
    def start(self) -> bool:
        """Start this service.

        Does nothing if the service is already running or it is stopped but not awaited
        on yet.

        Returns:
            Whether the service was started.
        """

    @property
    @abc.abstractmethod
    def unique_id(self) -> str:
        """The unique ID of this service."""

    @property
    @abc.abstractmethod
    def is_running(self) -> bool:
        """Whether this service is running."""

    @abc.abstractmethod
    def cancel(self, msg: str | None = None) -> None:
        """Cancel this service.

        Args:
            msg: The message to be passed to the tasks being cancelled.
        """

    @abc.abstractmethod
    async def stop(self, msg: str | None = None) -> None:  # noqa: DOC502
        """Stop this service.

        This method cancels the service and waits for it to finish.

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
    def __await__(self) -> collections.abc.Generator[None, None, Self]:  # noqa: DOC502
        """Wait for this service to finish.

        An awaited service will wait for all its tasks to finish and reset the service
        so it can be started again.

        Returns:
            An implementation-specific generator for the awaitable.

        Raises:
            BaseExceptionGroup: If any of the tasks spawned by this service raised an
                exception (`CancelError` is not considered an error and not returned in
                the exception group).
        """


@enum.unique
class AutoRestart(enum.Flag):
    """When to automatically restart a service."""

    NEVER = 0
    """Never automatically restart the service."""

    ON_EXIT = enum.auto()
    """Automatically restart the service when it exits normally."""

    ON_ERROR = enum.auto()
    """Automatically restart the service when it exits due to an unhandled exception."""

    ON_CANCEL = enum.auto()
    """Automatically restart the service when it exits due to being cancelled."""

    ALWAYS = ON_EXIT | ON_ERROR | ON_CANCEL
    """Automatically restart the service when it exits for any reason."""


@dataclass
class _ServiceEntry:
    service: Service
    auto_restart: AutoRestart


class PersistentServiceGroup:  # TODO!!!
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

    def __init__(self, *, unique_id: str | None = None) -> None:
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
        self._unique_id: str = get_unique_id(unique_id, self)
        """The unique ID of this instance."""

        self._running: dict[Service, _ServiceEntry] = dict()
        """The set of tasks that are still running.

        Tasks are removed from this set automatically when they finish using the
        Task.add_done_callback method.
        """

    @property
    def unique_id(self) -> str:
        """The unique ID of this instance."""
        return self._unique_id

    @property
    def services(self) -> collections.abc.Set[Service]:
        """The set of tasks managed by this group.

        Users typically should not modify the tasks in the returned set and only use
        them for informational purposes.

        Both running tasks and tasks pending for acknowledgment are included in the
        returned set.

        Danger:
            Changing the returned tasks may lead to unexpected behavior, don't do it
            unless the class explicitly documents it is safe to do so.
        """
        return frozenset(self._running.keys())

    @property
    def is_running(self) -> bool:
        """Whether this task group is running.

        A task group is considered running when at least one task is running.
        """
        return any(service.is_running for service in self._running)

    def manage_service(
        self,
        service: Service,
        auto_restart: AutoRestart = AutoRestart.ON_ERROR,
    ) -> None:
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
        if service in self._running:
            return
        self._running[service] = _ServiceEntry(
            service=service, auto_restart=auto_restart
        )

    def cancel(self, msg: str | None = None) -> None:
        """Cancel all running tasks spawned by this group.

        Args:
            msg: The message to be passed to the tasks being cancelled.
        """
        for service in self._running:
            service.cancel(msg)

    async def stop(self, msg: str | None = None) -> None:
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
        """Iterate over completed tasks.

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
        # TODO: See how as_completed works in this case, if it will create more tasks
        for completed in asyncio.as_completed(self._running):
            try:
                service = await completed
            except BaseException as error:  # pylint: disable=broad-except
                _logger.error("Got an unknown service %r", service)
                continue
            entry = self._running.get(service)
            if entry is None:
                _logger.error("Got an unknown service %r", service)
                continue
            try:
                await service
            except BaseException as error:  # pylint: disable=broad-except
                if 
            
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
        for entry in self._running.values():
            entry.service.start()
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
        # TODO: Rename, not all in _running is actually running, rename to _managed or
        # something
        details = "not running"
        if self._running:
            details = f"running={len(self._running)}"
        return f"{type(self).__name__}<{self.unique_id} {details}>"

    def __str__(self) -> str:
        """Return a string representation of this instance.

        Returns:
            A string representation of this instance.
        """
        return f"{type(self).__name__}:{self._unique_id}"


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

    Example: Simple single-task example
        ```python
        import datetime
        import asyncio
        from typing_extensions import override

        class Clock(ServiceBase):
            def __init__(self, resolution_s: float, *, unique_id: str | None = None) -> None:
                super().__init__(unique_id=unique_id)
                self._resolution_s = resolution_s

            @override
            async def main(self) -> None:
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

    Example: Multi-tasks example
        ```python
        import asyncio
        import datetime
        from typing_extensions import override

        class MultiTaskService(ServiceBase):

            async def _print_every(self, *, seconds: float) -> None:
                while True:
                    await asyncio.sleep(seconds)
                    print(datetime.datetime.now())

            async def _fail_after(self, *, seconds: float) -> None:
                await asyncio.sleep(seconds)
                raise ValueError("I failed")

            @override
            async def main(self) -> None:
                self.create_task(self._print_every(seconds=1), name="print_1")
                self.create_task(self._print_every(seconds=11), name="print_11")
                failing = self.create_task(self._fail_after(seconds=5), name=f"fail_5")

                async for task in self.task_group.as_completed():
                    assert task.done()  # For demonstration purposes only
                    try:
                        task.result()
                    except ValueError as error:
                        if failing == task:
                            failing = self.create_task(
                                self._fail_after(seconds=5), name=f"fail_5"
                            )
                        else:
                            raise

        async def main() -> None:
            async with MultiTaskService():
                await asyncio.sleep(11)

        asyncio.run(main())
        ```

    """

    def __init__(self, *, unique_id: str | None = None) -> None:
        """Initialize this Service.

        Args:
            unique_id: The string to uniquely identify this service instance.
                If `None`, a string based on `hex(id(self))` will be used. This is
                used in `__repr__` and `__str__` methods, mainly for debugging
                purposes, to identify a particular instance of a service.
        """
        self._unique_id: str = get_unique_id(unique_id, self)
        self._main_task: asyncio.Task[None] | None = None
        self._task_group: PersistentTaskGroup = PersistentTaskGroup(
            unique_id=self._unique_id
        )

    @property
    @override
    def unique_id(self) -> str:
        """The unique ID of this service."""
        return self._unique_id

    @property
    def main_task(self) -> asyncio.Task[None] | None:
        """The main task of this service.

        If the service never started, this will be `None`. But if it started and
        stopped, the stopped task will be returned so it can be further inspected.
        """
        return self._main_task

    @property
    def task_group(self) -> PersistentTaskGroup:
        """The task group managing the tasks of this service."""
        return self._task_group

    @abc.abstractmethod
    async def main(self) -> None:
        """Execute the service logic."""

    @override
    def start(self) -> bool:
        """Start this service.

        Does nothing if the service is already running or it is stopped but not awaited
        on yet.

        Returns:
            Whether the service was started.
        """
        if self._main_task is not None:
            return False
        self._main_task = asyncio.create_task(self.main(), name=str(self))
        return True

    @property
    @override
    def is_running(self) -> bool:
        """Whether this service is running.

        A service is considered running when at least one task is running.
        """
        return self._main_task is not None and not self._main_task.done()

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

        Tasks are created using the
        [`task_group`][frequenz.core.asyncio.ServiceBase.task_group].

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
        return self._task_group.create_task(
            coro, name=f"{self}:{name}", context=context, log_exception=log_exception
        )

    @override
    def cancel(self, msg: str | None = None) -> None:
        """Cancel all running tasks spawned by this service.

        Args:
            msg: The message to be passed to the tasks being cancelled.
        """
        if self._main_task is not None:
            self._main_task.cancel(msg)
        self._task_group.cancel(msg)

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

    async def _wait(self) -> Self:
        """Wait for this service to finish.

        Wait until all the service tasks are finished and clear the main task.

        Raises:
            BaseExceptionGroup: If any of the tasks spawned by this service raised an
                exception (`CancelError` is not considered an error and not returned in
                the exception group).
        """
        exceptions: list[BaseException] = []

        if self._main_task is not None:
            try:
                await self._main_task
            except BaseException as error:  # pylint: disable=broad-except
                exceptions.append(error)
        self._main_task = None

        try:
            await self._task_group
        except BaseExceptionGroup as exc_group:
            exceptions.append(exc_group)

        if exceptions:
            raise BaseExceptionGroup(f"Error while stopping {self}", exceptions)

        return self

    @override
    def __await__(self) -> collections.abc.Generator[None, None, Self]:
        """Await this service.

        An awaited service will wait for all its tasks to finish and reset the main
        task so that the service can be started again.

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
        details = "main"
        if not self.is_running:
            details += " not"
        details += " running"
        if self._task_group.is_running:
            details += f", {len(self._task_group.tasks)} extra tasks"
        return f"{type(self).__name__}<{self._unique_id} {details}>"

    def __str__(self) -> str:
        """Return a string representation of this instance.

        Returns:
            A string representation of this instance.
        """
        return f"{type(self).__name__}:{self._unique_id}"
