from __future__ import annotations

import re
import uuid
from pathlib import Path

from fastapi import UploadFile
from PIL import Image

from app.config import settings


_SAFE_NAME_PATTERN = re.compile(r"[^a-zA-Z0-9._-]+")


def _safe_name(name: str) -> str:
    cleaned = _SAFE_NAME_PATTERN.sub("_", name).strip("._")
    return cleaned or "upload.jpg"


def save_project_asset_file(project_id: str, upload: UploadFile) -> tuple[str, int, int, str]:
    root = Path(settings.storage_root) / "projects" / project_id / "assets"
    root.mkdir(parents=True, exist_ok=True)

    original_name = upload.filename or "upload.jpg"
    safe_name = _safe_name(original_name)
    ext = Path(safe_name).suffix or ".jpg"
    new_name = f"{uuid.uuid4().hex}{ext.lower()}"
    destination = root / new_name

    data = upload.file.read()
    destination.write_bytes(data)

    with Image.open(destination) as img:
        rgb = img.convert("RGB")
        width, height = rgb.size
        rgb.save(destination)

    return str(destination), width, height, safe_name
