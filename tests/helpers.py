import time
from pathlib import Path

import cv2
import numpy as np

from industry_cv import Frame

ROOT = Path(__file__).resolve().parents[1]


def scene(circles, shape=(220, 320)):
    image = np.full((*shape, 3), 30, np.uint8)
    for x, y, radius in circles:
        cv2.circle(image, (x, y), radius, (180, 180, 180), -1)
        cv2.putText(image, "+", (x - 8, y + 6), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (60, 60, 60), 2)
    return image


def frame(seq, circles=None, age=0, connection=1):
    return Frame(
        scene(circles if circles is not None else [(90, 90, 24)]),
        seq,
        time.time() - age,
        time.monotonic() - age,
        connection,
    )
