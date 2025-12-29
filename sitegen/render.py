from __future__ import annotations

import re
import shutil
from pathlib import Path

IMG_SRC_RE = re.compile(r'<img([^>]*?)src="([^"]+)"', re.IGNORECASE)
TAG_RE = re.compile(r"<[^>]+>")


def fix_relative_img_src(html_text: str, root: str) -> str:
    def repl(match: re.Match) -> str:
        attrs = match.group(1)
        src = match.group(2)
        if src.startswith(("http://", "https://", "data:", "#", "/", "./", "../")):
            return match.group(0)
        src = src.lstrip("/")
        return f'<img{attrs}src="{root}/{src}"'

    return IMG_SRC_RE.sub(repl, html_text)


def strip_tags(html_text: str) -> str:
    return TAG_RE.sub("", html_text)


def render_template(template: str, **context: str) -> str:
    output = template
    late_keys = {"content", "sidebar"}
    for key, value in context.items():
        if key in late_keys:
            continue
        output = output.replace(f"{{{{{key}}}}}", value)
    for key in late_keys:
        if key in context:
            output = output.replace(f"{{{{{key}}}}}", context[key])
    return output


def read_template(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def copy_static(static_dir: Path, output_dir: Path) -> None:
    for item in static_dir.iterdir():
        dest = output_dir / item.name
        if item.is_dir():
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(item, dest)
        else:
            shutil.copy2(item, dest)
