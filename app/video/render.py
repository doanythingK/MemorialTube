from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from app.config import settings


def _validate_inputs(clip_paths: list[str]) -> None:
    if not clip_paths:
        raise ValueError("clip_paths must not be empty")
    for clip in clip_paths:
        p = Path(clip)
        if not p.exists():
            raise FileNotFoundError(f"clip not found: {clip}")


def build_final_render(
    clip_paths: list[str],
    output_path: str,
    *,
    bgm_path: str | None = None,
    bgm_volume: float = 0.15,
) -> str:
    _validate_inputs(clip_paths)
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="render_concat_") as tmp_dir:
        list_file = Path(tmp_dir) / "clips.txt"
        with list_file.open("w", encoding="utf-8") as fp:
            for clip in clip_paths:
                fp.write(f"file '{Path(clip).resolve().as_posix()}'\n")

        if bgm_path:
            bgm = Path(bgm_path)
            if not bgm.exists():
                raise FileNotFoundError(f"bgm not found: {bgm_path}")
            cmd = [
                settings.ffmpeg_path,
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(list_file),
                "-stream_loop",
                "-1",
                "-i",
                str(bgm.resolve()),
                "-map",
                "0:v:0",
                "-map",
                "1:a:0",
                "-filter:a",
                f"volume={bgm_volume}",
                "-shortest",
                "-r",
                str(settings.target_fps),
                "-pix_fmt",
                settings.output_pixel_format,
                "-c:v",
                settings.output_video_codec,
                "-c:a",
                "aac",
                str(out),
            ]
        else:
            cmd = [
                settings.ffmpeg_path,
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(list_file),
                "-map",
                "0:v:0",
                "-an",
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
            raise RuntimeError(process.stderr.strip() or "ffmpeg final render failed")

    return str(out)
