# License: MIT
# Copyright © 2024 Frequenz Energy-as-a-Service GmbH

"""Timeseries basic types."""

from datetime import datetime, timezone

UNIX_EPOCH = datetime.fromtimestamp(0.0, tz=timezone.utc)
"""The UNIX epoch (in UTC)."""
