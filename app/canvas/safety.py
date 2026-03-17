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
        raise ValueError(
            "base_image_bgr and candidate_image_bgr shape mismatch: "
            f"base={base_image_bgr.shape}, candidate={candidate_image_bgr.shape}"
        )
    if mask.shape != base_image_bgr.shape[:2]:
        raise ValueError(
            "mask shape mismatch: "
            f"mask={mask.shape}, base_hw={base_image_bgr.shape[:2]}"
        )

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


def check_generation_boundary_continuity(
    candidate_image_bgr: np.ndarray,
    protected_mask: np.ndarray,
    generation_mask: np.ndarray,
    *,
    max_mean_diff: float = 34.0,
    max_p95_diff: float = 86.0,
    min_pair_count: int = 120,
) -> SafetyCheckResult:
    if protected_mask.shape != candidate_image_bgr.shape[:2]:
        return SafetyCheckResult(passed=False, reason="protected mask shape mismatch")
    if generation_mask.shape != candidate_image_bgr.shape[:2]:
        return SafetyCheckResult(passed=False, reason="generation mask shape mismatch")

    h, w = candidate_image_bgr.shape[:2]
    if h == 0 or w < 2:
        return SafetyCheckResult(passed=True)

    protected = protected_mask > 0
    gen = generation_mask > 0
    if not gen.any():
        return SafetyCheckResult(passed=True)

    left_pairs = gen[:, :-1] & protected[:, 1:]
    right_pairs = protected[:, :-1] & gen[:, 1:]

    diff = np.abs(candidate_image_bgr[:, :-1, :].astype(np.int16) - candidate_image_bgr[:, 1:, :].astype(np.int16))
    diff_max = diff.max(axis=2).astype(np.float32)

    values = []
    if left_pairs.any():
        values.append(diff_max[left_pairs])
    if right_pairs.any():
        values.append(diff_max[right_pairs])
    if not values:
        return SafetyCheckResult(passed=True)

    boundary_diff = np.concatenate(values)
    pair_count = int(boundary_diff.size)
    if pair_count < min_pair_count:
        return SafetyCheckResult(passed=True)

    mean_diff = float(boundary_diff.mean())
    p95_diff = float(np.percentile(boundary_diff, 95.0))

    if mean_diff > max_mean_diff or p95_diff > max_p95_diff:
        return SafetyCheckResult(
            passed=False,
            reason=(
                "generation boundary mismatch: "
                f"mean_diff={mean_diff:.4f}, p95_diff={p95_diff:.4f}, pairs={pair_count}, "
                f"limit_mean={max_mean_diff:.4f}, limit_p95={max_p95_diff:.4f}"
            ),
        )

    return SafetyCheckResult(passed=True)


def _gray(image_bgr: np.ndarray) -> np.ndarray:
    return (
        image_bgr[:, :, 0].astype(np.float32) * 0.114
        + image_bgr[:, :, 1].astype(np.float32) * 0.587
        + image_bgr[:, :, 2].astype(np.float32) * 0.299
    )


def _grad_magnitude(gray: np.ndarray) -> np.ndarray:
    gx = np.zeros_like(gray, dtype=np.float32)
    gy = np.zeros_like(gray, dtype=np.float32)
    gx[:, 1:-1] = gray[:, 2:] - gray[:, :-2]
    gy[1:-1, :] = gray[2:, :] - gray[:-2, :]
    return np.hypot(gx, gy)


def _masked_region_stats(
    image_bgr: np.ndarray,
    grad: np.ndarray,
    mask: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, float, float, int] | None:
    if mask.shape != image_bgr.shape[:2]:
        return None
    count = int(mask.sum())
    if count <= 0:
        return None

    pixels = image_bgr[mask]
    grad_vals = grad[mask]

    mean = pixels.mean(axis=0).astype(np.float32)
    std = pixels.std(axis=0).astype(np.float32)
    grad_mean = float(grad_vals.mean())
    edge_density = float((grad_vals >= 26.0).mean())
    return mean, std, grad_mean, edge_density, count


def check_generated_region_naturalness(
    candidate_image_bgr: np.ndarray,
    protected_mask: np.ndarray,
    generation_mask: np.ndarray,
    *,
    ref_band_width: int = 72,
    min_pixels_per_side: int = 1800,
    max_mean_delta_norm: float = 0.26,
    max_std_delta_norm: float = 0.36,
    max_grad_ratio: float = 3.0,
    max_edge_density_ratio: float = 3.5,
) -> SafetyCheckResult:
    if protected_mask.shape != candidate_image_bgr.shape[:2]:
        return SafetyCheckResult(passed=False, reason="protected mask shape mismatch")
    if generation_mask.shape != candidate_image_bgr.shape[:2]:
        return SafetyCheckResult(passed=False, reason="generation mask shape mismatch")

    h, w = candidate_image_bgr.shape[:2]
    if h == 0 or w == 0:
        return SafetyCheckResult(passed=True)

    protected = protected_mask > 0
    generation = generation_mask > 0
    if not generation.any() or not protected.any():
        return SafetyCheckResult(passed=True)

    gray = _gray(candidate_image_bgr)
    grad = _grad_magnitude(gray)
    x = np.arange(w)[None, :]

    protected_cols = np.where(protected.any(axis=0))[0]
    if protected_cols.size == 0:
        return SafetyCheckResult(passed=True)

    left_boundary = int(protected_cols.min())
    right_boundary = int(protected_cols.max()) + 1

    side_failures: list[str] = []

    # Left generated side vs adjacent protected band
    if left_boundary > 0:
        left_gen = generation & (x < left_boundary)
        left_ref_end = min(w, left_boundary + ref_band_width)
        left_ref = protected & (x >= left_boundary) & (x < left_ref_end)
        gen_stats = _masked_region_stats(candidate_image_bgr, grad, left_gen)
        ref_stats = _masked_region_stats(candidate_image_bgr, grad, left_ref)
        if gen_stats is not None and ref_stats is not None:
            g_mean, g_std, g_grad_mean, g_edge_density, g_count = gen_stats
            r_mean, r_std, r_grad_mean, r_edge_density, r_count = ref_stats
            if g_count >= min_pixels_per_side and r_count >= min_pixels_per_side:
                mean_delta_norm = float(np.linalg.norm(g_mean - r_mean) / 255.0)
                std_delta_norm = float(np.linalg.norm(g_std - r_std) / 255.0)
                grad_ratio = float(max(
                    g_grad_mean / (r_grad_mean + 1e-4),
                    r_grad_mean / (g_grad_mean + 1e-4),
                ))
                edge_density_ratio = float(max(
                    g_edge_density / (r_edge_density + 1e-4),
                    r_edge_density / (g_edge_density + 1e-4),
                ))
                if (
                    mean_delta_norm > max_mean_delta_norm
                    or std_delta_norm > max_std_delta_norm
                    or grad_ratio > max_grad_ratio
                    or edge_density_ratio > max_edge_density_ratio
                ):
                    side_failures.append(
                        "left("
                        f"mean={mean_delta_norm:.4f},std={std_delta_norm:.4f},"
                        f"grad={grad_ratio:.4f},edge={edge_density_ratio:.4f})"
                    )

    # Right generated side vs adjacent protected band
    if right_boundary < w:
        right_gen = generation & (x >= right_boundary)
        right_ref_start = max(0, right_boundary - ref_band_width)
        right_ref = protected & (x >= right_ref_start) & (x < right_boundary)
        gen_stats = _masked_region_stats(candidate_image_bgr, grad, right_gen)
        ref_stats = _masked_region_stats(candidate_image_bgr, grad, right_ref)
        if gen_stats is not None and ref_stats is not None:
            g_mean, g_std, g_grad_mean, g_edge_density, g_count = gen_stats
            r_mean, r_std, r_grad_mean, r_edge_density, r_count = ref_stats
            if g_count >= min_pixels_per_side and r_count >= min_pixels_per_side:
                mean_delta_norm = float(np.linalg.norm(g_mean - r_mean) / 255.0)
                std_delta_norm = float(np.linalg.norm(g_std - r_std) / 255.0)
                grad_ratio = float(max(
                    g_grad_mean / (r_grad_mean + 1e-4),
                    r_grad_mean / (g_grad_mean + 1e-4),
                ))
                edge_density_ratio = float(max(
                    g_edge_density / (r_edge_density + 1e-4),
                    r_edge_density / (g_edge_density + 1e-4),
                ))
                if (
                    mean_delta_norm > max_mean_delta_norm
                    or std_delta_norm > max_std_delta_norm
                    or grad_ratio > max_grad_ratio
                    or edge_density_ratio > max_edge_density_ratio
                ):
                    side_failures.append(
                        "right("
                        f"mean={mean_delta_norm:.4f},std={std_delta_norm:.4f},"
                        f"grad={grad_ratio:.4f},edge={edge_density_ratio:.4f})"
                    )

    if side_failures:
        return SafetyCheckResult(
            passed=False,
            reason="generated region unnatural: " + ", ".join(side_failures),
        )

    return SafetyCheckResult(passed=True)
