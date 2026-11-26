"""Render detector results independently of CLI or capture source."""

import cv2
import numpy as np


def annotate(image, targets, roi=None):
    image = image.copy()
    if roi is not None:
        cv2.polylines(image, [np.int32(roi)], True, (255, 160, 0), 2)
    for i, target in enumerate(targets):
        x, y = map(round, target["center_px"])
        color = (0, 220, 0) if not target["blocked_reasons"] else (0, 180, 255)
        cv2.circle(image, (x, y), round(target["radius_px"]), color, 2)
        cv2.drawMarker(image, (x, y), (0, 0, 255), cv2.MARKER_CROSS, 9, 1)
        cv2.putText(
            image,
            str(target.get("track_id", i + 1)),
            (x - 10, y - 28),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.38,
            color,
            1,
        )
    cv2.putText(
        image, f"Detected: {len(targets)}", (20, 38), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 200, 0), 2
    )
    return image
