"""Planar localization from correspondences or explicitly identified size estimates."""

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path

import cv2
import numpy as np


@dataclass
class PlanarCalibration:
    homography: list[list[float]]
    image_size: list[int]
    valid_polygon_px: list[list[float]]  # raw/distorted pixel hull
    frame_id: str
    plane_z_mm: float
    rmse_mm: float | None
    max_error_mm: float | None
    camera_matrix: list[list[float]] | None = None
    distortion: list[float] | None = None
    fit_pixels: list[list[float]] | None = None
    source: str = "correspondences"
    estimation: dict | None = None

    def __post_init__(self):
        h = np.asarray(self.homography, dtype=float)
        p = np.asarray(self.valid_polygon_px, dtype=np.float32)
        if h.shape != (3, 3) or not np.isfinite(h).all() or np.linalg.matrix_rank(h) != 3:
            raise ValueError("Invalid homography")
        if (
            p.ndim != 2
            or p.shape[1] != 2
            or len(p) < 3
            or not np.isfinite(p).all()
            or not cv2.isContourConvex(p)
        ):
            raise ValueError("Calibration requires a convex validity polygon")
        if len(self.image_size) != 2 or any(
            not isinstance(v, int) or v <= 0 for v in self.image_size
        ):
            raise ValueError("Invalid image_size")
        if (p < 0).any() or (p >= self.image_size).any():
            raise ValueError("Calibration hull is outside image_size")
        if not self.frame_id or not np.isfinite(self.plane_z_mm):
            raise ValueError("Frame and finite calibration metadata are required")
        if self.source not in ("correspondences", "estimated"):
            raise ValueError("Unknown calibration source")
        if self.source == "estimated":
            if self.rmse_mm is not None or self.max_error_mm is not None or not self.estimation:
                raise ValueError("Estimated calibration requires assumptions and unknown error")
        elif (
            self.rmse_mm is None
            or self.max_error_mm is None
            or not np.isfinite([self.rmse_mm, self.max_error_mm]).all()
            or min(self.rmse_mm, self.max_error_mm) < 0
        ):
            raise ValueError("Calibration errors must be finite and nonnegative")
        corrected = _undistort(p, self.camera_matrix, self.distortion)
        hp = cv2.perspectiveTransform(corrected.reshape(-1, 1, 2), h).reshape(-1, 2)
        den = np.c_[corrected, np.ones(len(p))] @ h[2]
        if (np.abs(den) < 1e-9).any() or not ((den > 0).all() or (den < 0).all()):
            raise ValueError("Homography has a singularity inside the valid region")
        if not np.isfinite(hp).all():
            raise ValueError("Invalid plane projection")
        if self.fit_pixels is not None:
            fit = np.asarray(self.fit_pixels, dtype=float)
            if (
                fit.ndim != 2
                or fit.shape[1] != 2
                or len(fit) < 4
                or not np.isfinite(fit).all()
                or (fit < 0).any()
                or (fit >= self.image_size).any()
            ):
                raise ValueError("Invalid fit_pixels provenance")

    @classmethod
    def fit(
        cls,
        pixels,
        xy_mm,
        image_size,
        frame_id,
        plane_z_mm,
        max_error_mm=1.0,
        camera_matrix=None,
        distortion=None,
    ):
        pixels = np.asarray(pixels, dtype=np.float64)
        xy = np.asarray(xy_mm, dtype=np.float64)
        if (
            pixels.ndim != 2
            or pixels.shape[1] != 2
            or len(pixels) < 4
            or pixels.shape != xy.shape
            or not np.isfinite(pixels).all()
            or not np.isfinite(xy).all()
        ):
            raise ValueError("At least four finite corresponding 2D points are required")
        if not np.isfinite(max_error_mm) or max_error_mm <= 0:
            raise ValueError("max_error_mm must be positive")
        for points in (pixels, xy):
            if len(np.unique(points, axis=0)) != len(points):
                raise ValueError("Duplicate calibration points")
            if np.linalg.matrix_rank(points - points.mean(axis=0)) < 2:
                raise ValueError("Calibration points must not be collinear")
        corrected = _undistort(pixels, camera_matrix, distortion)
        # All correspondences must pass; do not hide a mismeasured point with RANSAC.
        h, _ = cv2.findHomography(corrected, xy, method=0)
        if h is None:
            raise ValueError("Cannot fit homography")
        predicted = cv2.perspectiveTransform(corrected.reshape(-1, 1, 2), h).reshape(-1, 2)
        errors = np.linalg.norm(predicted - xy, axis=1)
        if not np.isfinite(errors).all() or errors.max() > max_error_mm:
            raise ValueError("Calibration residual exceeds max_error_mm")
        hull = cv2.convexHull(pixels.astype(np.float32)).reshape(-1, 2).tolist()
        return cls(
            h.tolist(),
            list(image_size),
            hull,
            frame_id,
            float(plane_z_mm),
            float(np.sqrt(np.mean(errors**2))),
            float(errors.max()),
            camera_matrix,
            distortion,
            pixels.tolist(),
        )

    @classmethod
    def from_nominal_diameter(
        cls,
        diameters_px,
        image_size,
        valid_polygon_px,
        diameter_mm,
        plane_z_mm=0.0,
        frame_id="work_surface_estimated",
        origin_px=None,
    ):
        """Estimate a near-normal work-plane scale using known circular part size.

        Part diameter is supplied by the caller. Coordinates use image-right X,
        image-up Y and outward Z. The origin defaults to the ROI area centroid.
        This defines a local work frame, not the unknown physical robot base.
        """
        diameters = np.asarray(diameters_px, dtype=float)
        if (
            diameters.ndim != 1
            or len(diameters) == 0
            or not np.isfinite(diameters).all()
            or (diameters <= 0).any()
        ):
            raise ValueError("At least one finite positive observed diameter is required")
        if not np.isfinite(diameter_mm) or diameter_mm <= 0:
            raise ValueError("Nominal diameter must be positive")
        polygon = np.asarray(valid_polygon_px, dtype=np.float32)
        if (
            polygon.ndim != 2
            or polygon.shape[1] != 2
            or len(polygon) < 3
            or not np.isfinite(polygon).all()
            or not cv2.isContourConvex(polygon)
        ):
            raise ValueError("Estimate requires a finite convex work region")
        if origin_px is None:
            moments = cv2.moments(polygon)
            if moments["m00"] <= 0:
                raise ValueError("Empty work region")
            origin = np.array([moments["m10"] / moments["m00"], moments["m01"] / moments["m00"]])
        else:
            origin = np.asarray(origin_px, dtype=float)
        if origin.shape != (2,) or not np.isfinite(origin).all():
            raise ValueError("Invalid estimated origin")
        observed = float(np.median(diameters))
        scale = float(diameter_mm / observed)
        return cls(
            [[scale, 0, -scale * origin[0]], [0, -scale, scale * origin[1]], [0, 0, 1]],
            list(image_size),
            polygon.tolist(),
            frame_id,
            float(plane_z_mm),
            None,
            None,
            source="estimated",
            estimation={
                "method": "median_nominal_diameter",
                "diameter_mm": float(diameter_mm),
                "observed_diameter_px": observed,
                "sample_count": len(diameters),
                "diameter_mad_px": float(np.median(np.abs(diameters - observed))),
                "mm_per_pixel": scale,
                "origin_px": origin.tolist(),
                "axes": "X image-right, Y image-up, Z toward camera",
                "assumptions": [
                    "same nominal part diameter",
                    "near-normal view",
                    "single plane",
                    "negligible lens distortion",
                ],
                "robot_base_transform": "unknown",
            },
        )

    def summary(self):
        return {
            "source": self.source,
            "frame_id": self.frame_id,
            "plane_z_mm": self.plane_z_mm,
            "rmse_mm": self.rmse_mm,
            "max_error_mm": self.max_error_mm,
            "estimation": self.estimation,
        }

    def project(self, pixel, image_size):
        if list(image_size) != self.image_size:
            raise ValueError("Calibration/frame resolution mismatch")
        p = np.asarray(pixel, dtype=float)
        if p.shape != (2,) or not np.isfinite(p).all():
            raise ValueError("Invalid pixel point")
        if cv2.pointPolygonTest(np.float32(self.valid_polygon_px), tuple(p), False) < 0:
            raise ValueError("Point outside calibrated region")
        point = _undistort(p.reshape(1, 2), self.camera_matrix, self.distortion)
        q = np.asarray(self.homography) @ np.r_[point[0], 1.0]
        if abs(q[2]) < 1e-9 or not np.isfinite(q).all():
            raise ValueError("Singular projection")
        return {
            "x_mm": float(q[0] / q[2]),
            "y_mm": float(q[1] / q[2]),
            "z_mm": self.plane_z_mm,
            "frame_id": self.frame_id,
        }

    def save(self, path):
        Path(path).write_text(json.dumps(asdict(self), indent=2, allow_nan=False) + "\n")

    def validate(
        self,
        pixels,
        xy_mm,
        image_size,
        frame_id,
        plane_z_mm,
        max_error_mm=1.0,
        min_separation_px=1.0,
    ):
        """Measure errors at holdout points without refitting the transform.

        Distinct locations are a necessary check, not proof that the supplied
        robot measurements were independently acquired. Results apply only to
        the sampled points and their stated plane/frame.
        """
        p, truth = np.asarray(pixels, dtype=float), np.asarray(xy_mm, dtype=float)
        if (
            p.ndim != 2
            or p.shape[1] != 2
            or len(p) == 0
            or p.shape != truth.shape
            or not np.isfinite(p).all()
            or not np.isfinite(truth).all()
        ):
            raise ValueError("Validation requires finite corresponding 2D points")
        if len(np.unique(p, axis=0)) != len(p):
            raise ValueError("Duplicate validation points")
        if list(image_size) != self.image_size:
            raise ValueError("Validation/frame resolution mismatch")
        if frame_id != self.frame_id:
            raise ValueError("Validation coordinate frame differs from calibration")
        if not np.isfinite(plane_z_mm) or abs(plane_z_mm - self.plane_z_mm) > 1e-6:
            raise ValueError("Validation plane height differs from calibration")
        if not all(np.isfinite(v) and v > 0 for v in (max_error_mm, min_separation_px)):
            raise ValueError("Validation tolerance and point separation must be positive")
        predicted = [self.project(point, image_size) for point in p]
        xy = np.array([[value["x_mm"], value["y_mm"]] for value in predicted])
        errors = np.linalg.norm(xy - truth, axis=1)
        reasons = []
        if self.source == "estimated":
            reasons.append("estimated_calibration")
        reused_indices = []
        if self.fit_pixels is None:
            reasons.append("fit_points_unavailable")
        else:
            distance = np.linalg.norm(
                p[:, None, :] - np.asarray(self.fit_pixels)[None, :, :], axis=2
            )
            reused_indices = np.flatnonzero(distance.min(axis=1) < min_separation_px).tolist()
            if reused_indices:
                reasons.append("validation_reuses_fit_locations")
        if errors.max() > max_error_mm:
            reasons.append("error_exceeds_tolerance")
        fingerprint = hashlib.sha256(
            json.dumps(asdict(self), sort_keys=True, allow_nan=False).encode()
        ).hexdigest()
        return {
            "schema_version": "1.0",
            "calibration_sha256": fingerprint,
            "frame_id": self.frame_id,
            "plane_z_mm": self.plane_z_mm,
            "image_size": self.image_size,
            "sample_count": len(p),
            "tolerance_mm": float(max_error_mm),
            "min_separation_px": float(min_separation_px),
            "rmse_mm": float(np.sqrt(np.mean(errors**2))),
            "max_error_mm": float(errors.max()),
            "passed": not reasons,
            "failure_reasons": reasons,
            "reused_point_indices": reused_indices,
            "points": [
                {
                    "pixel": pixel.tolist(),
                    "expected_xy_mm": actual.tolist(),
                    "predicted_xy_mm": estimated.tolist(),
                    "error_mm": float(error),
                }
                for pixel, actual, estimated, error in zip(p, truth, xy, errors, strict=True)
            ],
            "scope": "XY errors at supplied measured points only; does not validate Z, TCP, "
            "image recognition, unsampled locations or robot motion",
        }

    @classmethod
    def load(cls, path):
        return cls(**json.loads(Path(path).read_text()))


def _undistort(points, camera_matrix, distortion):
    if camera_matrix is None and distortion is None:
        return np.asarray(points, dtype=float)
    if camera_matrix is None or distortion is None:
        raise ValueError("camera_matrix and distortion must be provided together")
    k, d = np.asarray(camera_matrix, dtype=float), np.asarray(distortion, dtype=float)
    if (
        k.shape != (3, 3)
        or d.ndim != 1
        or d.size not in (4, 5, 8, 12, 14)
        or not np.isfinite(k).all()
        or not np.isfinite(d).all()
        or min(k[0, 0], k[1, 1]) <= 0
        or not np.allclose(k[2], [0, 0, 1])
    ):
        raise ValueError("Invalid lens calibration")
    return cv2.undistortPoints(
        np.asarray(points, dtype=float).reshape(-1, 1, 2), k, d, P=k
    ).reshape(-1, 2)
