from __future__ import annotations

import datetime as dt
import html as html_lib
import re
from pathlib import Path

LIST_MARKER_RE = re.compile(r"^(?P<indent>[ \t]*)(?:[-+*]|\d+[.)])\s+")
FENCE_RE = re.compile(r"^(?P<indent>[ \t]*)(`{3,}|~{3,})")
DOUBLE_QUOTE_RE = re.compile(r"^(?P<indent>[ \t]*)>>(?!>)(?P<rest>.*)$")
CJK_RE = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uac00-\ud7af]")
WORD_RE = re.compile(r"[A-Za-z0-9]+(?:'[A-Za-z0-9]+)?")


def slugify(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^\w]+", "-", text, flags=re.UNICODE)
    text = text.strip("-_").replace("_", "-")
    return text or "post"


def parse_list(value: str) -> list[str]:
    value = value.strip()
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1]
        items = [item.strip().strip("'\"") for item in inner.split(",")]
    else:
        items = [item.strip() for item in value.split(",")]
    return [item for item in items if item]


def parse_front_matter(text: str) -> tuple[dict, str]:
    clean_text = text.lstrip("\ufeff")
    lines = clean_text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, clean_text

    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        return {}, clean_text

    meta = {}
    for line in lines[1:end]:
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip().lower()
        value = value.strip()
        if key in {"categories", "tags", "archive"}:
            meta[key] = parse_list(value)
        else:
            meta[key] = value
    body = "\n".join(lines[end + 1 :])
    return meta, body


def extract_title(meta: dict, body: str) -> tuple[str, str]:
    if meta.get("title"):
        return meta["title"], body
    lines = body.splitlines()
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("# "):
            title = stripped[2:].strip() or "Untitled"
            new_body = "\n".join(lines[i + 1 :]).lstrip()
            return title, new_body
        if stripped:
            break
    return "Untitled", body


def parse_date(meta: dict, file_path: Path) -> tuple[dt.datetime, bool]:
    now = dt.datetime.now()
    date_value = (meta.get("date") or "").strip()
    time_value = (meta.get("time") or "").strip()
    if date_value:
        if "T" in date_value or " " in date_value:
            try:
                return dt.datetime.fromisoformat(date_value), True
            except ValueError:
                pass
        if time_value:
            try:
                date_part = dt.date.fromisoformat(date_value)
                time_part = dt.time.fromisoformat(time_value)
                return dt.datetime.combine(date_part, time_part), True
            except ValueError:
                pass
        try:
            date_part = dt.date.fromisoformat(date_value)
            return dt.datetime.combine(date_part, now.time()), True
        except ValueError:
            pass
    if time_value:
        try:
            time_part = dt.time.fromisoformat(time_value)
            return dt.datetime.combine(now.date(), time_part), True
        except ValueError:
            pass
    if not time_value:
        return now, True
    return dt.datetime.fromtimestamp(file_path.stat().st_mtime), False


def get_categories(meta: dict) -> list[str]:
    if meta.get("category"):
        return [meta["category"]]
    if meta.get("categories"):
        return meta["categories"]
    if meta.get("tags"):
        return meta["tags"]
    return ["General"]


def normalize_list_spacing(text: str) -> str:
    lines = text.splitlines()
    out: list[str] = []
    in_fence = False
    fence_marker = ""
    for line in lines:
        fence_match = FENCE_RE.match(line)
        if fence_match:
            marker = fence_match.group(2)
            if not in_fence:
                in_fence = True
                fence_marker = marker
            elif marker == fence_marker:
                in_fence = False
                fence_marker = ""
            out.append(line)
            continue
        if in_fence:
            out.append(line)
            continue
        quote_match = DOUBLE_QUOTE_RE.match(line)
        if quote_match:
            rest = quote_match.group("rest").lstrip()
            if rest:
                line = f'{quote_match.group("indent")}> {rest}'
            else:
                line = f'{quote_match.group("indent")}>'
        list_match = LIST_MARKER_RE.match(line)
        if list_match:
            if not list_match.group("indent"):
                if out and out[-1].strip() and not LIST_MARKER_RE.match(out[-1]):
                    out.append("")
        out.append(line)
    return "\n".join(out)


def count_words(text: str) -> int:
    text = html_lib.unescape(text)
    cjk_count = len(CJK_RE.findall(text))
    text = CJK_RE.sub(" ", text)
    word_count = len(WORD_RE.findall(text))
    return cjk_count + word_count
