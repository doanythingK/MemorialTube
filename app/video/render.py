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


def _run_ffmpeg(cmd: list[str], error_message: str) -> None:
    process = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if process.returncode != 0:
        raise RuntimeError(process.stderr.strip() or error_message)


def _normalize_clip(input_path: str, output_path: str) -> None:
    """Normalize clip codec/size/fps before concat to avoid stream mismatch issues."""
    vf = (
        f"scale={settings.target_width}:{settings.target_height}:force_original_aspect_ratio=decrease,"
        f"pad={settings.target_width}:{settings.target_height}:(ow-iw)/2:(oh-ih)/2:black,"
        f"fps={settings.target_fps},setsar=1,format={settings.output_pixel_format}"
    )
    cmd = [
        settings.ffmpeg_path,
        "-y",
        "-i",
        str(Path(input_path).resolve()),
        "-vf",
        vf,
        "-an",
        "-r",
        str(settings.target_fps),
        "-pix_fmt",
        settings.output_pixel_format,
        "-c:v",
        settings.output_video_codec,
        str(Path(output_path).resolve()),
    ]
    _run_ffmpeg(cmd, "ffmpeg normalize clip failed")


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
        normalized_paths: list[Path] = []
        for idx, clip in enumerate(clip_paths):
            normalized = Path(tmp_dir) / f"norm_{idx:04d}.mp4"
            _normalize_clip(clip, str(normalized))
            normalized_paths.append(normalized)

        list_file = Path(tmp_dir) / "clips.txt"
        with list_file.open("w", encoding="utf-8") as fp:
            for clip in normalized_paths:
                fp.write(f"file '{clip.resolve().as_posix()}'\n")

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

        _run_ffmpeg(cmd, "ffmpeg final render failed")

    return str(out)
