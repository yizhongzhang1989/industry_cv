"""Evaluate ROI center annotations; timings exclude decode and disk I/O.

python examples/button_battery/evaluate.py --image tests/data/button_battery/button_cells_100.jpg \
  --labels tests/data/button_battery/button_cells_100.json \
  --config examples/button_battery/configs/vision.json --repeat 50
"""

import argparse
import json
from pathlib import Path

import cv2
import numpy as np

from industry_cv import BatteryDetector, DetectorConfig


def evaluate(detector, image, truth, tolerance_px):
    detections = detector.detect(image)
    predicted = np.array([d.center_px for d in detections]).reshape(-1, 2)
    truth = np.asarray(truth, dtype=float).reshape(-1, 2)
    # Maximum-cardinality bipartite matching under tolerance; duplicate detections are FP.
    distances = np.linalg.norm(truth[:, None, :] - predicted[None, :, :], axis=2)
    edges = [list(np.argsort(row)[np.sort(row) <= tolerance_px]) for row in distances]
    matched = {}

    def assign(i, seen):
        for j in edges[i]:
            if j in seen:
                continue
            seen.add(j)
            if j not in matched or assign(matched[j], seen):
                matched[j] = i
                return True
        return False

    for i in range(len(truth)):
        assign(i, set())
    errors = [float(distances[i, j]) for j, i in matched.items()]
    tp = len(matched)
    return {
        "true_positive": tp,
        "false_positive": len(predicted) - tp,
        "false_negative": len(truth) - tp,
        "precision": tp / len(predicted) if len(predicted) else None,
        "recall": tp / len(truth) if len(truth) else None,
        "center_error_px_mean": float(np.mean(errors)) if errors else None,
        "center_error_px_max": max(errors) if errors else None,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True)
    parser.add_argument("--labels", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--repeat", type=int, default=30)
    args = parser.parse_args()
    if args.repeat < 1:
        parser.error("--repeat must be positive")
    image = cv2.imread(args.image)
    labels = json.loads(Path(args.labels).read_text())
    detector = BatteryDetector(DetectorConfig(**json.loads(Path(args.config).read_text())))
    result = evaluate(detector, image, labels["centers_px"], labels.get("tolerance_px", 3))
    times = []
    for _ in range(args.repeat):
        detector.detect(image)
        times.append(detector.last_diagnostics["processing_ms"])
    result.update(
        algorithm_ms_p50=float(np.percentile(times, 50)),
        algorithm_ms_p95=float(np.percentile(times, 95)),
        opencv=cv2.__version__,
        numpy=np.__version__,
        annotation_method=labels.get("annotation_method"),
        timing_scope="detector only; excludes stream decode and robot latency",
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
