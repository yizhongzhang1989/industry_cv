"""Bright button cells on a dark, planar picking surface.

Connected components propose objects; distance peaks split touching objects;
robust ellipse fits on the original external arcs give subpixel centers.
Geometry cannot distinguish a battery from an equally sized metal disk.
"""

import math
import time
from dataclasses import asdict, dataclass

import cv2
import numpy as np


@dataclass(frozen=True)
class DetectorConfig:
    min_radius_px: float = 18.0
    max_radius_px: float = 30.0
    roi: list[list[float]] | None = None
    image_size: list[int] | None = None  # [width, height]; mandatory with a site ROI
    threshold: float | None = None  # None = Otsu within ROI
    min_axis_ratio: float = 0.8
    min_arc_coverage: float = 0.72
    min_contrast: float = 25.0
    clearance_px: float = 4.0
    border_margin_px: float = 3.0
    normalize_lighting: bool = True

    def __post_init__(self):
        if not isinstance(self.normalize_lighting, bool):
            raise TypeError("normalize_lighting must be boolean")
        numbers = [
            self.min_radius_px,
            self.max_radius_px,
            self.min_axis_ratio,
            self.min_arc_coverage,
            self.min_contrast,
            self.clearance_px,
            self.border_margin_px,
        ]
        if not all(math.isfinite(v) for v in numbers):
            raise ValueError("Detector parameters must be finite")
        if not 3 <= self.min_radius_px < self.max_radius_px:
            raise ValueError("Require 3 <= min_radius_px < max_radius_px")
        if not 0 < self.min_axis_ratio <= 1 or not 0 < self.min_arc_coverage <= 1:
            raise ValueError("Invalid geometry thresholds")
        if min(self.min_contrast, self.clearance_px, self.border_margin_px) < 0:
            raise ValueError("Contrast and margins must be nonnegative")
        if self.threshold is not None and not 0 <= self.threshold <= 255:
            raise ValueError("threshold must be in [0,255]")
        if self.image_size is not None and (
            len(self.image_size) != 2
            or any(not isinstance(v, int) or v <= 0 for v in self.image_size)
        ):
            raise ValueError("image_size must be positive integer [width,height]")
        if self.roi is not None:
            p = np.asarray(self.roi, dtype=np.float32)
            if (
                p.ndim != 2
                or p.shape[1] != 2
                or len(p) < 3
                or not np.isfinite(p).all()
                or not cv2.isContourConvex(p)
            ):
                raise ValueError("roi must be a finite convex polygon")
            if self.image_size is None:
                raise ValueError("A site ROI requires image_size to prevent silent rescaling")
            if np.any(p < 0) or np.any(p >= np.asarray(self.image_size)):
                raise ValueError("ROI lies outside image_size")


@dataclass
class Detection:
    center_px: tuple[float, float]
    radius_px: float
    axes_px: tuple[float, float]
    ellipse_angle_deg: float  # geometric ellipse, NOT battery/gripper yaw
    score: float  # geometric quality, not a calibrated class probability
    arc_coverage: float
    contrast: float
    blocked_reasons: list[str]

    def to_dict(self):
        return asdict(self)


class BatteryDetector:
    def __init__(self, config: DetectorConfig | None = None):
        self.config = config or DetectorConfig()
        self.last_diagnostics: dict = {}

    def detect(self, image: np.ndarray) -> list[Detection]:
        start = time.perf_counter()
        cfg = self.config
        if not isinstance(image, np.ndarray) or image.dtype != np.uint8 or image.size == 0:
            raise ValueError("Expected nonempty uint8 BGR or grayscale image")
        if image.ndim == 3 and image.shape[2] == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        elif image.ndim == 2:
            gray = image
        else:
            raise ValueError("Expected HxW or HxWx3 image")
        h, w = gray.shape
        if cfg.image_size is not None and cfg.image_size != [w, h]:
            raise ValueError("Frame resolution differs from site configuration")
        polygon = np.float32(
            cfg.roi if cfg.roi is not None else [[0, 0], [w - 1, 0], [w - 1, h - 1], [0, h - 1]]
        )
        x0, y0, rw, rh = cv2.boundingRect(polygon)
        gray = gray[y0 : y0 + rh, x0 : x0 + rw]
        if cfg.normalize_lighting:
            # Divide out slowly varying illumination before segmentation and contrast tests.
            # Middle-gray gain leaves headroom for highlights; scale follows expected part size.
            background = cv2.GaussianBlur(
                gray.astype(np.float32), (0, 0), cfg.max_radius_px * 2 / 3
            )
            gray = np.clip(gray / np.maximum(background, 1) * 110, 0, 255).astype(np.uint8)
        local_polygon = polygon - [x0, y0]
        mask = np.zeros(gray.shape, np.uint8)
        cv2.fillPoly(mask, [local_polygon.astype(np.int32)], 255)
        smooth = cv2.GaussianBlur(gray, (3, 3), 0)
        threshold = cfg.threshold
        if threshold is None:
            threshold, _ = cv2.threshold(
                smooth[mask > 0], 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
            )
        detections = []
        rejected = 0
        recovered = 0
        thresholds = [threshold]
        if cfg.normalize_lighting and cfg.threshold is None:
            thresholds.extend([threshold * 0.9, threshold * 0.8])
        min_area = math.pi * cfg.min_radius_px**2 * 0.65
        for pass_index, level in enumerate(thresholds):
            binary = ((smooth > level) & (mask > 0)).astype(np.uint8) * 255
            contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
            for contour in contours:
                if cv2.contourArea(contour) < min_area:
                    continue
                if pass_index:
                    bx, by, bw, bh = cv2.boundingRect(contour)
                    center = (bx + bw / 2 + x0, by + bh / 2 + y0)
                    if max(bw, bh) <= 2.2 * cfg.max_radius_px and any(
                        math.dist(center, d.center_px) < cfg.min_radius_px for d in detections
                    ):
                        continue
                # Prefer the whole rim; split only shapes that fail single-object fitting.
                whole = self._fit(contour[:, 0, :].astype(np.float32), gray)
                if whole is not None:
                    candidates = [whole]
                else:
                    arcs = self._split_arcs(contour)
                    candidates = [self._fit(arc, gray) for arc in arcs]
                    if not arcs:
                        rejected += 1
                for result in candidates:
                    if result is None:
                        rejected += 1
                        continue
                    cx, cy = result.center_px
                    global_center = (cx + x0, cy + y0)
                    # Lower thresholds recover shadowed rims but may join background patches.
                    # Keep the primary fit and require stronger evidence for additional objects.
                    if pass_index and (
                        result.score < 0.5
                        or any(
                            math.dist(global_center, d.center_px)
                            < 1.4 * min(result.radius_px, d.radius_px)
                            for d in detections
                        )
                    ):
                        continue
                    clearance = cv2.pointPolygonTest(
                        local_polygon.astype(np.float32), (cx, cy), True
                    )
                    if clearance < max(result.axes_px) / 2 + cfg.border_margin_px:
                        result.blocked_reasons.append("roi_border")
                    result.center_px = global_center
                    detections.append(result)
                    recovered += int(pass_index > 0)
        # Suppress duplicate circles, favoring better observed arcs.
        unique = []
        for d in sorted(detections, key=lambda d: d.score, reverse=True):
            if all(
                math.dist(d.center_px, p.center_px) > min(d.radius_px, p.radius_px) for p in unique
            ):
                unique.append(d)
        for i, d in enumerate(unique):
            for other in unique[i + 1 :]:
                if math.dist(d.center_px, other.center_px) < (
                    max(d.axes_px) / 2 + max(other.axes_px) / 2 + cfg.clearance_px
                ):
                    for obj in (d, other):
                        if "neighbor_clearance" not in obj.blocked_reasons:
                            obj.blocked_reasons.append("neighbor_clearance")
        unique.sort(key=lambda d: (d.center_px[1], d.center_px[0]))
        self.last_diagnostics = {
            "lighting_normalized": cfg.normalize_lighting,
            "shadow_recovered": recovered,
            "threshold": float(threshold),
            "rejected_candidates": rejected,
            "processing_ms": (time.perf_counter() - start) * 1000,
        }
        return unique

    def _split_arcs(self, contour):
        cfg = self.config
        points = contour[:, 0, :].astype(np.float32)
        bx, by, bw, bh = cv2.boundingRect(contour)
        # Fill interior markings before distance transform; pad to handle border objects.
        component = np.zeros((bh + 4, bw + 4), np.uint8)
        shift = np.array([bx - 2, by - 2])
        cv2.drawContours(component, [contour - shift], -1, 255, -1)
        distance = cv2.distanceTransform(component, cv2.DIST_L2, cv2.DIST_MASK_PRECISE)
        k = int(cfg.min_radius_px * 2) + 1
        maxima = cv2.dilate(distance, np.ones((k, k), np.uint8))
        peak_mask = ((distance >= maxima - 1e-5) & (distance >= cfg.min_radius_px * 0.75)).astype(
            np.uint8
        )
        count, _labels, _stats, centers = cv2.connectedComponentsWithStats(peak_mask)
        seeds = []
        for i in range(1, count):
            seed = centers[i]
            if distance[round(seed[1]), round(seed[0])] <= cfg.max_radius_px * 1.25:
                seeds.append(seed + shift)
        if not seeds:
            return []
        assignment = np.argmin(
            np.linalg.norm(points[:, None, :] - np.asarray(seeds)[None, :, :], axis=2), axis=1
        )
        return [points[assignment == i] for i in range(len(seeds))]

    def _fit(self, points, gray):
        cfg = self.config
        if len(points) < 16:
            return None
        # Iteratively exclude local edge damage / contact seams, retaining measured arcs.
        arc = points
        for _ in range(3):
            if len(arc) < 16:
                return None
            (cx, cy), (a, b), angle = cv2.fitEllipse(arc)
            if min(a, b) <= 0:
                return None
            theta = np.deg2rad(angle)
            delta = arc - [cx, cy]
            u = delta[:, 0] * np.cos(theta) + delta[:, 1] * np.sin(theta)
            v = -delta[:, 0] * np.sin(theta) + delta[:, 1] * np.cos(theta)
            residual = np.abs(np.sqrt((u / (a / 2)) ** 2 + (v / (b / 2)) ** 2) - 1)
            keep = residual <= max(0.08, float(np.median(residual)) * 3)
            if keep.all():
                break
            arc = arc[keep]
        (cx, cy), (a, b), angle = cv2.fitEllipse(arc)
        radius = math.sqrt(a * b) / 2
        if not cfg.min_radius_px <= radius <= cfg.max_radius_px:
            return None
        if min(a, b) / max(a, b) < cfg.min_axis_ratio:
            return None
        theta = np.deg2rad(angle)
        delta = arc - [cx, cy]
        u = delta[:, 0] * np.cos(theta) + delta[:, 1] * np.sin(theta)
        v = -delta[:, 0] * np.sin(theta) + delta[:, 1] * np.cos(theta)
        radial_error = np.sqrt((u / (a / 2)) ** 2 + (v / (b / 2)) ** 2) - 1
        if float(np.sqrt(np.mean(radial_error**2))) > 0.06:
            return None
        angles = np.arctan2(arc[:, 1] - cy, arc[:, 0] - cx)
        coverage = (
            len(np.unique(np.floor((angles + np.pi) / (2 * np.pi) * 36).astype(int) % 36)) / 36
        )
        if coverage < cfg.min_arc_coverage:
            return None
        h, w = gray.shape
        # Sample a solid central disk and outer ring; medians resist print and highlights.
        x1, x2 = max(0, int(cx - radius * 1.5)), min(w, int(cx + radius * 1.5) + 1)
        y1, y2 = max(0, int(cy - radius * 1.5)), min(h, int(cy + radius * 1.5) + 1)
        yy, xx = np.ogrid[y1:y2, x1:x2]
        rr = np.hypot(xx - cx, yy - cy)
        patch = gray[y1:y2, x1:x2]
        inside = patch[rr < radius * 0.75]
        outside = patch[(rr > radius * 1.15) & (rr < radius * 1.45)]
        if len(inside) == 0 or len(outside) == 0:
            return None
        contrast = float(np.median(inside)) - float(np.median(outside))
        if contrast < cfg.min_contrast:
            return None
        score = float(coverage * min(a, b) / max(a, b) * min(1, contrast / 80))
        return Detection(
            (float(cx), float(cy)),
            radius,
            (float(a), float(b)),
            float(angle),
            score,
            coverage,
            contrast,
            [],
        )
