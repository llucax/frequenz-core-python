# License: MIT
# Copyright © 2024 Frequenz Energy-as-a-Service GmbH

"""General purpose async tools.

This module provides general purpose async tools that can be used to simplify the
development of asyncio-based applications.

The module provides the following classes and functions:

- [cancel_and_await][frequenz.core.asyncio.cancel_and_await]: A function that cancels a
  task and waits for it to finish, handling `CancelledError` exceptions.
- [PersistentTaskGroup][frequenz.core.asyncio.PersistentTaskGroup]: An alternative to
  [`asyncio.TaskGroup`][] to manage tasks that run until explicitly stopped.
- [Service][frequenz.core.asyncio.Service]: An interface for services running in the
  background.
- [ServiceBase][frequenz.core.asyncio.ServiceBase]: A base class for implementing
  services running in the background.
"""

from ._service import Service, ServiceBase
from ._task_group import PersistentTaskGroup
from ._util import TaskReturnT, cancel_and_await

__all__ = [
    "PersistentTaskGroup",
    "Service",
    "ServiceBase",
    "TaskReturnT",
    "cancel_and_await",
]
