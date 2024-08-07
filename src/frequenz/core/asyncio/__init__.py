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

from ._service import Service, ServiceBase
from ._util import TaskCreator, TaskReturnT, cancel_and_await

__all__ = [
    "Service",
    "ServiceBase",
    "TaskCreator",
    "TaskReturnT",
    "cancel_and_await",
]
