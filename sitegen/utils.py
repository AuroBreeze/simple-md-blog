from __future__ import annotations

import datetime as dt
import shutil
import sys
from pathlib import Path


def parse_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return False


def parse_int(value: object, default: int) -> int:
    if value is None:
        return default
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    try:
        return int(str(value).strip())
    except ValueError:
        return default


def join_url(base: str, path: str) -> str:
    base = base.rstrip("/")
    path = path.lstrip("/")
    if not path:
        return base
    return f"{base}/{path}"


def rfc822_date(value: dt.datetime) -> str:
    value = value.replace(tzinfo=dt.timezone.utc)
    return value.strftime("%a, %d %b %Y %H:%M:%S %z")


def iso_date(value: dt.datetime) -> str:
    value = value.replace(tzinfo=dt.timezone.utc)
    return value.strftime("%Y-%m-%dT%H:%M:%SZ")


def write_nojekyll(output_dir: Path) -> None:
    output_dir.joinpath(".nojekyll").write_text("", encoding="utf-8")


def clean_output_dir(output_dir: Path, project_root: Path) -> None:
    if not output_dir.exists():
        return
    output_resolved = output_dir.resolve()
    root_resolved = project_root.resolve()
    if output_resolved == root_resolved:
        print("Refusing to clean project root.", file=sys.stderr)
        sys.exit(1)
    if not output_resolved.is_relative_to(root_resolved):
        print("Refusing to clean output directory outside project root.", file=sys.stderr)
        sys.exit(1)
    shutil.rmtree(output_dir)
