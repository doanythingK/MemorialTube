from __future__ import annotations

from pathlib import Path

from app.config import settings


def _allowed_roots() -> list[Path]:
    roots = [Path("data").resolve(), Path(settings.storage_root).resolve()]
    unique: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        key = str(root)
        if key in seen:
            continue
        seen.add(key)
        unique.append(root)
    return unique


def _is_under_any_root(path: Path, roots: list[Path]) -> bool:
    for root in roots:
        try:
            path.relative_to(root)
            return True
        except ValueError:
            continue
    return False


def ensure_safe_input_path(path_str: str) -> str:
    p = Path(path_str).resolve()
    roots = _allowed_roots()
    if not _is_under_any_root(p, roots):
        raise ValueError(f"path outside allowed roots: {path_str}")
    if not p.exists():
        raise FileNotFoundError(f"path not found: {path_str}")
    return str(p)


def ensure_safe_output_path(path_str: str) -> str:
    p = Path(path_str).resolve()
    roots = _allowed_roots()
    if not _is_under_any_root(p, roots):
        raise ValueError(f"output path outside allowed roots: {path_str}")
    parent = p.parent
    parent.mkdir(parents=True, exist_ok=True)
    return str(p)
