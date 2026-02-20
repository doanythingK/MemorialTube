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
        *,
        num_inference_steps: int | None = None,
        fast_mode: bool = False,
    ) -> np.ndarray:
        """Return outpainted image.

        `generation_mask` is uint8 with 255 on generation-allowed pixels.
        """


class MirrorOutpaintAdapter:
    """Non-generative placeholder for early integration tests.

    This mirrors edge pixels into generation regions so the pipeline can be
    executed end-to-end before wiring a real model.
    """

    def outpaint(
        self,
        base_image_bgr: np.ndarray,
        generation_mask: np.ndarray,
        *,
        num_inference_steps: int | None = None,
        fast_mode: bool = False,
    ) -> np.ndarray:
        _ = num_inference_steps
        _ = fast_mode
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

    def outpaint(
        self,
        base_image_bgr: np.ndarray,
        generation_mask: np.ndarray,
        *,
        num_inference_steps: int | None = None,
        fast_mode: bool = False,
    ) -> np.ndarray:
        if generation_mask.shape != base_image_bgr.shape[:2]:
            raise ValueError("generation_mask shape mismatch")

        src_h, src_w = base_image_bgr.shape[:2]
        proc_bgr = base_image_bgr
        proc_mask = generation_mask
        proc_w = src_w
        proc_h = src_h

        if fast_mode:
            max_side = max(64, int(settings.outpaint_fast_max_side))
            longest = max(src_w, src_h)
            if longest > max_side:
                scale = max_side / float(longest)
                proc_w = max(8, int(round(src_w * scale)))
                proc_h = max(8, int(round(src_h * scale)))
                proc_w = max(8, (proc_w // 8) * 8)
                proc_h = max(8, (proc_h // 8) * 8)
                proc_bgr = np.array(
                    Image.fromarray(base_image_bgr[:, :, ::-1], mode="RGB").resize(
                        (proc_w, proc_h),
                        Image.Resampling.LANCZOS,
                    ),
                    dtype=np.uint8,
                )[:, :, ::-1]
                proc_mask = np.array(
                    Image.fromarray(generation_mask, mode="L").resize(
                        (proc_w, proc_h),
                        Image.Resampling.NEAREST,
                    ),
                    dtype=np.uint8,
                )

        gen_w = ((proc_w + 7) // 8) * 8
        gen_h = ((proc_h + 7) // 8) * 8

        if gen_w != proc_w or gen_h != proc_h:
            pad_right = gen_w - proc_w
            pad_bottom = gen_h - proc_h
            padded_image_bgr = np.pad(
                proc_bgr,
                ((0, pad_bottom), (0, pad_right), (0, 0)),
                mode="edge",
            )
            padded_mask = np.pad(
                proc_mask,
                ((0, pad_bottom), (0, pad_right)),
                mode="constant",
                constant_values=0,
            )
        else:
            padded_image_bgr = proc_bgr
            padded_mask = proc_mask

        image = Image.fromarray(padded_image_bgr[:, :, ::-1], mode="RGB")
        mask = Image.fromarray(padded_mask, mode="L")

        kwargs: dict[str, object] = {
            "prompt": settings.outpaint_prompt,
            "negative_prompt": settings.outpaint_negative_prompt,
            "image": image,
            "mask_image": mask,
            "guidance_scale": settings.outpaint_guidance_scale,
            "num_inference_steps": (
                int(num_inference_steps)
                if num_inference_steps is not None
                else settings.outpaint_num_inference_steps
            ),
            "width": gen_w,
            "height": gen_h,
        }
        if settings.outpaint_seed is not None:
            kwargs["generator"] = self._torch.Generator(self._device).manual_seed(
                settings.outpaint_seed
            )

        result = self._pipe(**kwargs).images[0]
        out_rgb = np.array(result, dtype=np.uint8)
        if out_rgb.shape[:2] != (gen_h, gen_w):
            out_rgb = np.array(
                Image.fromarray(out_rgb, mode="RGB").resize(
                    (gen_w, gen_h),
                    Image.Resampling.LANCZOS,
                ),
                dtype=np.uint8,
            )
        out_bgr = out_rgb[:, :, ::-1]  # RGB -> BGR
        out_bgr = out_bgr[:proc_h, :proc_w]
        if proc_w != src_w or proc_h != src_h:
            out_bgr = np.array(
                Image.fromarray(out_bgr[:, :, ::-1], mode="RGB").resize(
                    (src_w, src_h),
                    Image.Resampling.LANCZOS,
                ),
                dtype=np.uint8,
            )[:, :, ::-1]
        return out_bgr


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
