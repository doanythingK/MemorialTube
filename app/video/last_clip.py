from __future__ import annotations

import subprocess
from pathlib import Path

from app.config import settings


def _motion_filter_expr(motion_style: str) -> str:
    if motion_style == "zoom_out":
        return (
            "zoompan="
            "z='if(lte(on,1),1.08,max(1.0,zoom-0.0008))':"
            "x='iw/2-(iw/zoom/2)':"
            "y='ih/2-(ih/zoom/2)':"
            f"d=1:s={settings.target_width}x{settings.target_height}:fps={settings.target_fps}"
        )
    if motion_style == "none":
        return f"fps={settings.target_fps}"
    return (
        "zoompan="
        "z='min(zoom+0.0008,1.08)':"
        "x='iw/2-(iw/zoom/2)':"
        "y='ih/2-(ih/zoom/2)':"
        f"d=1:s={settings.target_width}x{settings.target_height}:fps={settings.target_fps}"
    )


def build_last_clip(
    image_path: str,
    output_path: str,
    *,
    duration_seconds: int,
    motion_style: str = "zoom_in",
) -> str:
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    base_norm = (
        f"scale={settings.target_width}:{settings.target_height}:force_original_aspect_ratio=decrease,"
        f"pad={settings.target_width}:{settings.target_height}:(ow-iw)/2:(oh-ih)/2"
    )
    motion = _motion_filter_expr(motion_style)
    vf = f"{base_norm},{motion},format={settings.output_pixel_format}"

    cmd = [
        settings.ffmpeg_path,
        "-y",
        "-loop",
        "1",
        "-t",
        str(duration_seconds),
        "-i",
        image_path,
        "-vf",
        vf,
        "-t",
        str(duration_seconds),
        "-r",
        str(settings.target_fps),
        "-pix_fmt",
        settings.output_pixel_format,
        "-c:v",
        settings.output_video_codec,
        str(out),
    ]
    process = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if process.returncode != 0:
        raise RuntimeError(process.stderr.strip() or "ffmpeg last-clip build failed")
    return str(out)
