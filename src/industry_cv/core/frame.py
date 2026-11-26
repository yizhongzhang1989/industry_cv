"""Decoded image contract shared by acquisition and pipelines."""

from dataclasses import dataclass, field

import numpy as np


@dataclass(frozen=True)
class Frame:
    image: np.ndarray = field(repr=False)
    sequence: int
    received_at_unix: float
    received_monotonic: float
    connection_id: int
