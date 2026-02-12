from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(slots=True)
class CanvasBuildResult:
    image: np.ndarray
    used_outpaint: bool
    fallback_applied: bool
    fallback_reason: str | None
    safety_passed: bool
    safety_message: str
