from __future__ import annotations

from functools import lru_cache
from typing import Protocol

import numpy as np
from PIL import Image

from app.config import settings


class OutpaintAdapter(Protocol):
    def outpaint(
        self,
        base_image_bgr: np.ndarray,
        generation_mask: np.ndarray,
    ) -> np.ndarray:
        """Return outpainted image.

        `generation_mask` is uint8 with 255 on generation-allowed pixels.
        """


class MirrorOutpaintAdapter:
    """Non-generative placeholder for early integration tests.

    This mirrors edge pixels into generation regions so the pipeline can be
    executed end-to-end before wiring a real model.
    """

    def outpaint(self, base_image_bgr: np.ndarray, generation_mask: np.ndarray) -> np.ndarray:
        out = base_image_bgr.copy()
        h, w = out.shape[:2]

        mask = generation_mask > 0
        if not mask.any():
            return out

        # Fill left generation zone from nearest non-generated column.
        for y in range(h):
            row_mask = mask[y]
            if not row_mask.any():
                continue
            valid_cols = np.where(~row_mask)[0]
            if valid_cols.size == 0:
                continue

            first_valid = int(valid_cols[0])
            last_valid = int(valid_cols[-1])

            left_cols = np.where(row_mask & (np.arange(w) < first_valid))[0]
            right_cols = np.where(row_mask & (np.arange(w) > last_valid))[0]

            if left_cols.size > 0:
                src = out[y, first_valid : first_valid + 1, :]
                out[y, left_cols, :] = src

            if right_cols.size > 0:
                src = out[y, last_valid : last_valid + 1, :]
                out[y, right_cols, :] = src

        return out


class DiffusersOutpaintAdapter:
    """Diffusers-based outpainting adapter.

    Notes:
    - Requires `diffusers`, `torch`, `transformers`, `accelerate`.
    - Model weights are downloaded at first load.
    """

    def __init__(self) -> None:
        import torch  # noqa: PLC0415 - optional dependency

        self._torch = torch
        device = settings.outpaint_device.lower().strip()
        if device == "auto":
            device = "cuda" if torch.cuda.is_available() else "cpu"
        self._device = device

        dtype = torch.float16 if device == "cuda" else torch.float32
        # Use Stable Diffusion inpaint pipeline directly.
        # AutoPipeline can import optional pipeline modules and fail due to
        # unrelated dependency issues (for example MT5Tokenizer import path).
        try:
            from diffusers import StableDiffusionInpaintPipeline  # noqa: PLC0415

            pipeline = StableDiffusionInpaintPipeline.from_pretrained(
                settings.outpaint_model_id,
                torch_dtype=dtype,
            )
        except Exception as exc:  # noqa: BLE001 - optional dependency/model load failure
            raise RuntimeError(f"StableDiffusionInpaintPipeline failed: {exc}") from exc

        self._pipe = pipeline
        self._pipe.to(device)
        if hasattr(self._pipe, "set_progress_bar_config"):
            self._pipe.set_progress_bar_config(disable=True)
        if device == "cuda" and hasattr(self._pipe, "enable_attention_slicing"):
            self._pipe.enable_attention_slicing()

    def outpaint(self, base_image_bgr: np.ndarray, generation_mask: np.ndarray) -> np.ndarray:
        if generation_mask.shape != base_image_bgr.shape[:2]:
            raise ValueError("generation_mask shape mismatch")

        image = Image.fromarray(base_image_bgr[:, :, ::-1], mode="RGB")
        mask = Image.fromarray(generation_mask, mode="L")

        kwargs: dict[str, object] = {
            "prompt": settings.outpaint_prompt,
            "negative_prompt": settings.outpaint_negative_prompt,
            "image": image,
            "mask_image": mask,
            "guidance_scale": settings.outpaint_guidance_scale,
            "num_inference_steps": settings.outpaint_num_inference_steps,
        }
        if settings.outpaint_seed is not None:
            kwargs["generator"] = self._torch.Generator(self._device).manual_seed(
                settings.outpaint_seed
            )

        result = self._pipe(**kwargs).images[0]
        out_rgb = np.array(result, dtype=np.uint8)
        return out_rgb[:, :, ::-1]  # RGB -> BGR


@lru_cache(maxsize=1)
def _create_cached_diffusers_adapter() -> DiffusersOutpaintAdapter:
    return DiffusersOutpaintAdapter()


def create_default_outpaint_adapter() -> OutpaintAdapter:
    provider = settings.outpaint_provider.lower().strip()

    if provider in {"mirror", "none"}:
        return MirrorOutpaintAdapter()

    if provider in {"diffusers", "auto"}:
        try:
            return _create_cached_diffusers_adapter()
        except Exception:  # noqa: BLE001 - optional dependency/model load failure
            if provider == "diffusers":
                raise

    return MirrorOutpaintAdapter()
