from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Optional


def list_files(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return [path for path in root.rglob("*") if path.is_file()]


def hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def hash_text(text: str) -> str:
    return hash_bytes(text.encode("utf-8"))


def hash_file(path: Path) -> str:
    return hash_bytes(path.read_bytes())


def hash_paths(paths: list[Path], base: Optional[Path] = None) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths, key=lambda p: p.as_posix()):
        rel = path
        if base is not None:
            try:
                rel = path.relative_to(base)
            except ValueError:
                rel = path
        digest.update(rel.as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def load_lock(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def write_lock(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=True), encoding="utf-8")
