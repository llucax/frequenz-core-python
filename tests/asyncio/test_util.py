# License: MIT
# Copyright © 2022 Frequenz Energy-as-a-Service GmbH

"""Tests for the asyncio util module."""

import asyncio

from frequenz.core.asyncio import TaskCreator


def test_task_creator_asyncio() -> None:
    """Test that the asyncio module is a TaskCreator."""
    assert isinstance(asyncio, TaskCreator)


async def test_task_creator_loop() -> None:
    """Test that the asyncio event loop is a TaskCreator."""
    assert isinstance(asyncio.get_event_loop(), TaskCreator)


def test_task_creator_task_group() -> None:
    """Test that the asyncio task group is a TaskCreator."""
    assert isinstance(asyncio.TaskGroup(), TaskCreator)
