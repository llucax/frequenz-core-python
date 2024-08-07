# License: MIT
# Copyright © 2024 Frequenz Energy-as-a-Service GmbH

"""Tests for PersistentTaskGroup."""

import asyncio

import async_solipsism
import pytest

from frequenz.core.asyncio import PersistentTaskGroup, TaskCreator


# This method replaces the event loop for all tests in the file.
@pytest.fixture
def event_loop_policy() -> async_solipsism.EventLoopPolicy:
    """Return an event loop policy that uses the async solipsism event loop."""
    return async_solipsism.EventLoopPolicy()


async def test_construction_defaults() -> None:
    """Test the construction of a group with default arguments."""
    group = PersistentTaskGroup()
    assert group.unique_id == hex(id(group))[2:]
    assert group.tasks == set()
    assert group.is_running is False
    assert str(group) == f"PersistentTaskGroup:{group.unique_id}"
    assert repr(group) == f"PersistentTaskGroup<{group.unique_id}>"


async def test_construction_custom() -> None:
    """Test the construction of a group with a custom unique ID."""
    group = PersistentTaskGroup(unique_id="test")
    assert group.unique_id == "test"
    assert group.tasks == set()
    assert group.is_running is False
    assert str(group) == "PersistentTaskGroup:test"
    assert repr(group) == "PersistentTaskGroup<test>"


async def test_task_name() -> None:
    """Test a group with some task can be awaited when finishing successfully."""
    group = PersistentTaskGroup(unique_id="test")

    task = group.create_task(asyncio.sleep(0), name="sleep_1")

    assert group.tasks == {task}
    assert group.is_running is True
    assert str(group) == "PersistentTaskGroup:test"
    assert repr(group) == f"PersistentTaskGroup<{group.unique_id} running=1>"
    assert task.get_name() == "PersistentTaskGroup:test:sleep_1"
    await task


async def test_cancel() -> None:
    """Test a group cancel all tasks when cancel is called."""
    group = PersistentTaskGroup(unique_id="test")

    task = group.create_task(asyncio.sleep(0), name="sleep_1")
    group.cancel()

    await asyncio.sleep(1)  # Make sure the task is cancelled

    assert group.is_running is False
    assert task.cancelled()


async def test_as_completed_with_timeout() -> None:
    """Test tasks in a group can be iterated as the complete."""
    group = PersistentTaskGroup(unique_id="test")

    group.create_task(asyncio.sleep(1), name="sleep_1")

    async with asyncio.timeout(1):  # Make sure this doesn't hang
        async for _ in group.as_completed(timeout=0.5):
            assert False, "Should not have any task completed"

    assert group.is_running is True
    assert len(group.tasks) == 1


async def test_as_completed() -> None:
    """Test tasks in a group can be iterated as they complete."""
    group = PersistentTaskGroup(unique_id="test")

    expected_exception = RuntimeError("Boom!")

    async def _boom_at_2() -> None:
        await asyncio.sleep(2)
        raise expected_exception

    async def _cancel_at_3() -> None:
        await asyncio.sleep(3)
        self = asyncio.current_task()
        assert self is not None
        self.cancel()
        await asyncio.sleep(10)

    task_sleep_1 = group.create_task(asyncio.sleep(1), name="sleep_1")
    task_boom_at_2 = group.create_task(_boom_at_2(), name="boom_at_2")
    task_cancel_at_3 = group.create_task(_cancel_at_3(), name="cancel_at_3")

    assert len(group.tasks) == 3

    async with asyncio.timeout(4):  # Make sure this doesn't hang
        order = iter([task_sleep_1, task_boom_at_2, task_cancel_at_3])
        async for task in group.as_completed():
            expected_task = next(order)
            assert task is expected_task
            if task is task_sleep_1:
                assert task.result() is None
            elif task is task_boom_at_2:
                assert task.exception() is expected_exception
            elif task is task_cancel_at_3:
                assert task.cancelled() is True

        assert group.is_running is False
        assert next(order, None) is None


async def test_repr() -> None:
    """Test the representation of a group."""
    group = PersistentTaskGroup(unique_id="test")

    tasks: set[asyncio.Task[None]] = set()
    tasks.add(group.create_task(asyncio.sleep(0), name="sleep_1"))

    assert repr(group) == f"PersistentTaskGroup<{group.unique_id} running=1>"

    tasks.add(group.create_task(asyncio.sleep(0), name="sleep_2"))
    tasks.add(group.create_task(asyncio.sleep(2), name="sleep_3"))

    assert repr(group) == f"PersistentTaskGroup<{group.unique_id} running=3>"

    await asyncio.sleep(1)  # Make sure 2 tasks are done

    assert (
        repr(group) == f"PersistentTaskGroup<{group.unique_id} running=1 waiting_ack=2>"
    )
    as_completed_iter = group.as_completed()
    task = await anext(as_completed_iter, None)
    assert task is not None
    assert (
        repr(group) == f"PersistentTaskGroup<{group.unique_id} running=1 waiting_ack=2>"
    )

    task = await anext(as_completed_iter, None)
    assert task is not None
    assert (
        repr(group) == f"PersistentTaskGroup<{group.unique_id} running=1 waiting_ack=1>"
    )

    task = await anext(as_completed_iter, None)
    assert task is not None
    assert repr(group) == f"PersistentTaskGroup<{group.unique_id} waiting_ack=1>"

    task = await anext(as_completed_iter, None)
    assert task is None
    assert repr(group) == f"PersistentTaskGroup<{group.unique_id}>"

    await asyncio.gather(*tasks)


async def test_await_success() -> None:
    """Test a group with some task can be awaited when finishing successfully."""
    group = PersistentTaskGroup(unique_id="test")

    # Is a no-op if the group is not running
    await group.stop()
    assert group.is_running is False

    task = group.create_task(asyncio.sleep(0), name="sleep_1")
    assert group.is_running is True

    # Should stop immediately
    async with asyncio.timeout(1):
        await group

    assert group.is_running is False
    assert task.done()
    assert not task.cancelled()
    assert task.exception() is None


async def test_await_error() -> None:
    """Test a group with some task can be awaited when finishing with an error."""
    group = PersistentTaskGroup(unique_id="test")

    expected_exception = RuntimeError("Boom!")

    async def _boom() -> None:
        raise expected_exception

    task = group.create_task(_boom(), name="boom")
    assert group.is_running is True

    # Should stop immediately
    async with asyncio.timeout(1):
        with pytest.raises(BaseExceptionGroup) as exc_info:
            await group
        assert exc_info.value.args == (
            "Error while stopping PersistentTaskGroup:test",
            [expected_exception],
        )

    assert group.is_running is False
    assert task.done()
    assert not task.cancelled()
    assert task.exception() is expected_exception


async def test_await_cancelled() -> None:
    """Test a group with some task can be awaited when cancelled."""
    group = PersistentTaskGroup(unique_id="test")

    task = group.create_task(asyncio.sleep(1), name="sleep_1")
    assert group.is_running is True
    cancelled = task.cancel("bye bye")
    assert cancelled is True

    # Should stop immediately
    async with asyncio.timeout(1):
        with pytest.raises(BaseExceptionGroup) as exc_info:
            await group
        assert exc_info.value.args[0] == "Error while stopping PersistentTaskGroup:test"
        exceptions = exc_info.value.exceptions
        assert len(exceptions) == 1
        assert isinstance(exceptions[0], asyncio.CancelledError)

    assert group.is_running is False
    assert task.cancelled()


async def test_stop_success() -> None:
    """Test a group with some task can be stopped when finishing successfully."""
    group = PersistentTaskGroup(unique_id="test")

    task = group.create_task(asyncio.sleep(2), name="sleep_1")
    assert group.is_running is True

    await asyncio.sleep(1)
    assert group.is_running is True

    await group.stop()
    assert group.is_running is False

    assert task.cancelled()

    await group.stop()
    assert group.is_running is False


async def test_stop_error() -> None:
    """Test a group with some task can be stopped when finishing with an error."""
    group = PersistentTaskGroup(unique_id="test")

    expected_exception = RuntimeError("Boom!")

    async def _boom() -> None:
        raise expected_exception

    task = group.create_task(_boom(), name="boom")
    assert group.is_running is True

    await asyncio.sleep(1)
    assert group.is_running is False

    with pytest.raises(BaseExceptionGroup) as exc_info:
        await group.stop()
    assert exc_info.value.args == (
        "Error while stopping PersistentTaskGroup:test",
        [expected_exception],
    )

    assert group.is_running is False
    assert task.done()
    assert not task.cancelled()
    assert task.exception() is expected_exception

    await group.stop()
    assert group.is_running is False


async def test_stop_cancelled() -> None:
    """Test a group with some task can be stopped when cancelled."""
    group = PersistentTaskGroup(unique_id="test")

    task = group.create_task(asyncio.sleep(1), name="sleep_1")
    assert group.is_running is True

    cancelled = task.cancel("bye bye")
    assert cancelled is True

    # If we give it some time, then the task will be cancelled and the group will be
    # stopped
    await asyncio.sleep(0.5)
    assert group.is_running is False

    await group.stop()

    assert group.is_running is False
    assert task.cancelled()

    await group.stop()
    assert group.is_running is False


async def test_async_context_manager_success() -> None:
    """Test a group works as an async context manager when finishing successfully."""
    async with PersistentTaskGroup(unique_id="test") as group:
        assert group.is_running is False

        task = group.create_task(asyncio.sleep(1), name="sleep_1")

        assert group.is_running is True
        assert task.done() is False
        assert task.cancelled() is False

        await asyncio.sleep(2)

        assert group.is_running is False
        assert task.done()
        assert not task.cancelled()
        assert task.exception() is None

    assert group.is_running is False
    assert task.done()
    assert not task.cancelled()
    assert task.exception() is None


async def test_async_context_manager_error() -> None:
    """Test a group works as an async context manager when finishing with an error."""
    expected_exception = RuntimeError("Boom!")

    async def _boom() -> None:
        raise expected_exception

    async_with_block_finished = False
    group: PersistentTaskGroup | None = None
    task: asyncio.Task[None] | None = None

    with pytest.raises(BaseExceptionGroup) as exc_info:
        async with PersistentTaskGroup(unique_id="test") as group:
            task = group.create_task(_boom(), name="boom")

            assert group.is_running is True
            assert task.done() is False
            assert task.cancelled() is False

            await asyncio.sleep(1)

            assert group.is_running is False
            assert task.done()
            assert not task.cancelled()
            assert task.exception() is expected_exception
            async_with_block_finished = True

    assert exc_info.value.args == (
        "Error while stopping PersistentTaskGroup:test",
        [expected_exception],
    )
    assert async_with_block_finished is True
    assert group is not None
    assert group.is_running is False
    assert task is not None
    assert task.done()
    assert not task.cancelled()
    assert task.exception() is expected_exception


async def test_async_context_manager_cancelled() -> None:
    """Test a group works as an async context manager when cancelled."""
    async with PersistentTaskGroup(unique_id="test") as group:
        task = group.create_task(asyncio.sleep(1), name="sleep_1")
        assert group.is_running is True

        cancelled = task.cancel("bye bye")
        assert cancelled is True

    assert group.is_running is False
    assert task.cancelled()


def test_is_task_creator() -> None:
    """Test that a persistent task group is a TaskCreator."""
    assert isinstance(PersistentTaskGroup(), TaskCreator)
