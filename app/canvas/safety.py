from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from app.canvas.detector import AnimalDetector


@dataclass(slots=True)
class SafetyCheckResult:
    passed: bool
    reason: str | None = None


def _count_changed_pixels(
    base_image_bgr: np.ndarray,
    candidate_image_bgr: np.ndarray,
    mask: np.ndarray,
    diff_threshold: int = 8,
) -> tuple[int, int]:
    if base_image_bgr.shape != candidate_image_bgr.shape:
        raise ValueError("base_image_bgr and candidate_image_bgr shape mismatch")
    if mask.shape != base_image_bgr.shape[:2]:
        raise ValueError("mask shape mismatch")

    # Per-pixel absolute difference, max over channels.
    diff = np.abs(candidate_image_bgr.astype(np.int16) - base_image_bgr.astype(np.int16))
    diff_max = diff.max(axis=2)
    changed = (diff_max > diff_threshold) & (mask > 0)

    changed_count = int(changed.sum())
    total_count = int((mask > 0).sum())
    return changed_count, total_count


def check_protected_region_unchanged(
    base_image_bgr: np.ndarray,
    candidate_image_bgr: np.ndarray,
    protected_mask: np.ndarray,
    *,
    max_changed_ratio: float = 0.001,
    diff_threshold: int = 8,
) -> SafetyCheckResult:
    changed, total = _count_changed_pixels(
        base_image_bgr,
        candidate_image_bgr,
        protected_mask,
        diff_threshold=diff_threshold,
    )
    if total == 0:
        return SafetyCheckResult(passed=False, reason="protected mask is empty")

    ratio = changed / total
    if ratio > max_changed_ratio:
        return SafetyCheckResult(
            passed=False,
            reason=(
                f"protected region changed too much: ratio={ratio:.6f}, "
                f"threshold={max_changed_ratio:.6f}"
            ),
        )
    return SafetyCheckResult(passed=True)


def check_no_new_animals_in_generated_region(
    candidate_image_bgr: np.ndarray,
    generation_mask: np.ndarray,
    detector: AnimalDetector,
    *,
    strict_mode: bool,
) -> SafetyCheckResult:
    if generation_mask.shape != candidate_image_bgr.shape[:2]:
        return SafetyCheckResult(passed=False, reason="generation mask shape mismatch")

    if not detector.available:
        if strict_mode and int((generation_mask > 0).sum()) > 0:
            return SafetyCheckResult(
                passed=False,
                reason="animal detector unavailable in strict mode",
            )
        return SafetyCheckResult(passed=True)

    detections = detector.detect_animals(candidate_image_bgr)
    for det in detections:
        # If detection bbox intersects generated region, treat as policy violation.
        x1 = max(0, min(det.x1, candidate_image_bgr.shape[1] - 1))
        y1 = max(0, min(det.y1, candidate_image_bgr.shape[0] - 1))
        x2 = max(0, min(det.x2, candidate_image_bgr.shape[1]))
        y2 = max(0, min(det.y2, candidate_image_bgr.shape[0]))
        if x2 <= x1 or y2 <= y1:
            continue

        region = generation_mask[y1:y2, x1:x2]
        if int((region > 0).sum()) > 0:
            return SafetyCheckResult(
                passed=False,
                reason=(
                    f"new animal detected in generated region: "
                    f"{det.label}({det.confidence:.2f})"
                ),
            )

    return SafetyCheckResult(passed=True)
