from __future__ import annotations

import html
import json
import sys
from pathlib import Path

import markdown

try:
    import tomllib as toml
except ImportError:
    try:
        import tomli as toml
    except ImportError:  # pragma: no cover - optional dependency
        toml = None

try:
    import yaml
except ImportError:  # pragma: no cover - optional dependency
    yaml = None


def load_config(path: Path) -> dict:
    if not path.exists():
        return {}
    suffix = path.suffix.lower()
    text = path.read_text(encoding="utf-8")
    if suffix == ".toml":
        if toml is None:
            print("TOML config requires tomllib (Python 3.11+) or tomli.", file=sys.stderr)
            sys.exit(1)
        try:
            data = toml.loads(text)
        except Exception as exc:  # pragma: no cover - depends on parser
            print(f"Invalid TOML in config file {path}: {exc}", file=sys.stderr)
            sys.exit(1)
        if not isinstance(data, dict):
            print(f"TOML config must be a mapping: {path}", file=sys.stderr)
            sys.exit(1)
        return data
    if suffix in {".yml", ".yaml"}:
        if yaml is None:
            print("YAML config requires PyYAML.", file=sys.stderr)
            sys.exit(1)
        try:
            data = yaml.safe_load(text)
        except Exception as exc:  # pragma: no cover - depends on parser
            print(f"Invalid YAML in config file {path}: {exc}", file=sys.stderr)
            sys.exit(1)
        if data is None:
            return {}
        if not isinstance(data, dict):
            print(f"YAML config must be a mapping: {path}", file=sys.stderr)
            sys.exit(1)
        return data
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        print(f"Invalid JSON in config file {path}: {exc}", file=sys.stderr)
        sys.exit(1)


def resolve_analytics(args: object) -> str:
    html_snippet = (getattr(args, "analytics_html", "") or "").strip()
    if html_snippet:
        return html_snippet
    file_value = (getattr(args, "analytics_file", "") or "").strip()
    if not file_value:
        return ""
    path = Path(file_value)
    if not path.is_absolute():
        config_path = Path(getattr(args, "config", "site.json")).resolve()
        path = config_path.parent / path
    if not path.exists():
        print(f"Analytics file not found: {path}", file=sys.stderr)
        return ""
    return path.read_text(encoding="utf-8")


def resolve_about_html(args: object) -> str:
    html_snippet = (getattr(args, "about_html", "") or "").strip()
    if html_snippet:
        return html_snippet

    file_value = (getattr(args, "about_file", "") or "").strip()
    if file_value:
        path = Path(file_value)
        if not path.is_absolute():
            config_path = Path(getattr(args, "config", "site.json")).resolve()
            path = config_path.parent / path
        if not path.exists():
            print(f"About file not found: {path}", file=sys.stderr)
        else:
            text = path.read_text(encoding="utf-8")
            suffix = path.suffix.lower()
            if suffix in {".html", ".htm"}:
                return text
            if suffix == ".md":
                md = markdown.Markdown(extensions=["fenced_code", "tables"])
                return md.convert(text)
            escaped = html.escape(text).replace("\n", "<br>")
            return f"<p>{escaped}</p>"

    text_value = (getattr(args, "about_text", "") or "").strip()
    if text_value:
        escaped = html.escape(text_value).replace("\n", "<br>")
        return f"<p>{escaped}</p>"

    site_description = getattr(args, "site_description", "")
    return f"<p>{html.escape(site_description)}</p>"


def resolve_widget_html(args: object) -> str:
    html_snippet = (getattr(args, "widget_html", "") or "").strip()
    if html_snippet:
        return html_snippet
    file_value = (getattr(args, "widget_file", "") or "").strip()
    if not file_value:
        return ""
    path = Path(file_value)
    if not path.is_absolute():
        config_path = Path(getattr(args, "config", "site.json")).resolve()
        path = config_path.parent / path
    if not path.exists():
        print(f"Widget file not found: {path}", file=sys.stderr)
        return ""
    return path.read_text(encoding="utf-8")
