# License: MIT
# Copyright © 2023 Frequenz Energy-as-a-Service GmbH

"""Logging tools."""

import logging


def get_public_logger(module_name: str) -> logging.Logger:
    """Get a logger for the public module containing the given module name.

    * Modules are considered private if they start with `_`.
    * All modules inside a private module are also considered private, even if they
      don't start with `_`.
    * If there is no leading public part, the root logger is returned.

    Example:
        Here are a few examples of how this function will resolve module names:

        * `some.pub` -> `some.pub`
        * `some.pub._some._priv` -> `some.pub`
        * `some.pub._some._priv.public` -> `some.pub`
        * `some.pub._some._priv.public._private` -> `some.pub`
        * `_priv` -> `root`

    Args:
        module_name: The fully qualified name of the module to get the logger for
            (normally the `__name__` built-in variable).

    Returns:
        The logger for the public module containing the given module name.
    """
    public_parts: list[str] = []
    for part in module_name.split("."):
        if part.startswith("_"):
            break
        public_parts.append(part)
    return logging.getLogger(".".join(public_parts))
