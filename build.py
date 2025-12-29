#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import re
import shutil
import sys
from pathlib import Path

try:
    import markdown
except ImportError:
    print("Missing dependency: markdown. Install with pip install -r requirements.txt", file=sys.stderr)
    sys.exit(1)

DATE_FMT = "%Y-%m-%d"
DATETIME_FMT = "%Y-%m-%d %H:%M"
IMG_SRC_RE = re.compile(r'<img([^>]*?)src="([^"]+)"', re.IGNORECASE)
TAG_RE = re.compile(r"<[^>]+>")
TIME_IN_DATE_RE = re.compile(r"[T ]\d{1,2}:\d{2}")


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
        if key in {"categories", "tags"}:
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


def parse_date(meta: dict, file_path: Path) -> dt.datetime:
    date_value = (meta.get("date") or "").strip()
    time_value = (meta.get("time") or "").strip()
    if date_value:
        if time_value:
            try:
                date_part = dt.date.fromisoformat(date_value)
                time_part = dt.time.fromisoformat(time_value)
                return dt.datetime.combine(date_part, time_part)
            except ValueError:
                pass
        try:
            return dt.datetime.fromisoformat(date_value)
        except ValueError:
            pass
    return dt.datetime.fromtimestamp(file_path.stat().st_mtime)


def has_explicit_time(meta: dict) -> bool:
    if meta.get("time"):
        return True
    date_value = meta.get("date") or ""
    return bool(TIME_IN_DATE_RE.search(date_value))


def get_categories(meta: dict) -> list[str]:
    if meta.get("category"):
        return [meta["category"]]
    if meta.get("categories"):
        return meta["categories"]
    if meta.get("tags"):
        return meta["tags"]
    return ["General"]


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


def load_config(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"Invalid JSON in config file {path}: {exc}", file=sys.stderr)
        sys.exit(1)


def build_sidebar(category_map: dict, root: str, site_description: str, toc_html: str = "") -> str:
    items = []
    for name, posts in sorted(category_map.items(), key=lambda x: (-len(x[1]), x[0].lower())):
        slug = slugify(name)
        items.append(
            f'<li><a href="{root}/categories/{slug}.html">{html.escape(name)}</a>'
            f'<span class="count">{len(posts)}</span></li>'
        )
    categories_html = "\n".join(items) if items else "<li>No categories yet.</li>"
    panels = [
        '<div class="panel">'
        "<h3>About</h3>"
        f"<p>{html.escape(site_description)}</p>"
        "</div>"
    ]
    if toc_html and "<li" in toc_html:
        panels.append(
            '<div class="panel">'
            "<h3>Contents</h3>"
            f"{toc_html}"
            "</div>"
        )
    panels.append(
        '<div class="panel">'
        "<h3>Categories</h3>"
        f'<ul class="category-list">{categories_html}</ul>'
        "</div>"
    )
    return "".join(panels)


def build_post_cards(posts: list[dict], root: str) -> str:
    cards = []
    for idx, post in enumerate(posts):
        delay = min(idx * 0.05, 0.3)
        title = html.escape(post["title"])
        summary = html.escape(post["summary"])
        url = f"{root}/posts/{post['slug']}.html"
        category_links = " ".join(
            f'<a class="chip" href="{root}/categories/{slugify(cat)}.html">{html.escape(cat)}</a>'
            for cat in post["categories"]
        )
        cards.append(
            f'<article class="post-card" style="animation-delay: {delay:.2f}s">'
            f'<div class="post-meta"><span class="post-date">{post["date"]}</span>'
            f'<div class="post-tags">{category_links}</div></div>'
            f'<h2 class="post-title"><a href="{url}">{title}</a></h2>'
            f'<p class="post-summary">{summary}</p>'
            f'<a class="post-more" href="{url}">Read more</a>'
            "</article>"
        )
    return "\n".join(cards)


def build_index(
    base_template: str, output_dir: Path, posts: list[dict], category_map: dict, args: argparse.Namespace
) -> None:
    root = "."
    sidebar = build_sidebar(category_map, root, args.site_description)
    site_name = html.escape(args.site_name)
    site_description = html.escape(args.site_description)
    content = (
        '<div class="section-head">'
        "<h2>Latest posts</h2>"
        "<p>Fresh notes generated from your Markdown folder.</p>"
        "</div>"
        f'<div class="post-grid">{build_post_cards(posts, root)}</div>'
    )
    html_doc = render_template(
        base_template,
        title=html.escape(f"{args.site_name} | Home"),
        root=root,
        content=content,
        sidebar=sidebar,
        site_name=site_name,
        site_description=site_description,
        year=str(dt.datetime.now().year),
        extra_head="",
    )
    write_text(output_dir / "index.html", html_doc)


def build_posts(
    base_template: str, output_dir: Path, posts: list[dict], category_map: dict, args: argparse.Namespace
) -> None:
    root = ".."
    site_name = html.escape(args.site_name)
    site_description = html.escape(args.site_description)
    for post in posts:
        sidebar = build_sidebar(category_map, root, args.site_description, post.get("toc", ""))
        title = html.escape(post["title"])
        category_links = " ".join(
            f'<a class="chip" href="{root}/categories/{slugify(cat)}.html">{html.escape(cat)}</a>'
            for cat in post["categories"]
        )
        content = (
            '<article class="post">'
            f'<div class="post-meta"><span class="post-date">{post["date"]}</span>'
            f'<div class="post-tags">{category_links}</div></div>'
            f'<h1 class="post-title">{title}</h1>'
            f'<div class="post-body">{post["content"]}</div>'
            f'<div class="post-footer"><a href="{root}/index.html">Back to home</a></div>'
            "</article>"
        )
        html_doc = render_template(
            base_template,
            title=html.escape(f"{post['title']} | {args.site_name}"),
            root=root,
            content=content,
            sidebar=sidebar,
            site_name=site_name,
            site_description=site_description,
            year=str(dt.datetime.now().year),
            extra_head="",
        )
        write_text(output_dir / "posts" / f"{post['slug']}.html", html_doc)


def build_categories(
    base_template: str, output_dir: Path, category_map: dict, args: argparse.Namespace
) -> None:
    root = ".."
    sidebar = build_sidebar(category_map, root, args.site_description)
    site_name = html.escape(args.site_name)
    site_description = html.escape(args.site_description)
    for category, posts in sorted(category_map.items(), key=lambda x: x[0].lower()):
        content = (
            '<div class="section-head">'
            f"<h2>{html.escape(category)}</h2>"
            "<p>Posts grouped in this category.</p>"
            "</div>"
            f'<div class="post-grid">{build_post_cards(posts, root)}</div>'
        )
        html_doc = render_template(
            base_template,
            title=html.escape(f"{category} | {args.site_name}"),
            root=root,
            content=content,
            sidebar=sidebar,
            site_name=site_name,
            site_description=site_description,
            year=str(dt.datetime.now().year),
            extra_head="",
        )
        write_text(output_dir / "categories" / f"{slugify(category)}.html", html_doc)


def build_search(
    base_template: str, output_dir: Path, posts: list[dict], category_map: dict, args: argparse.Namespace
) -> None:
    root = "."
    sidebar = build_sidebar(category_map, root, args.site_description)
    site_name = html.escape(args.site_name)
    site_description = html.escape(args.site_description)
    content = (
        '<div class="section-head">'
        "<h2>Search</h2>"
        "<p>Filter posts by title, summary, date, or category.</p>"
        "</div>"
        '<div class="search-bar">'
        '<input id="search-input" class="search-input" type="search" placeholder="Type to search..." />'
        '<div id="search-status" class="search-status">Type to filter posts.</div>'
        "</div>"
        '<div id="search-results" class="post-grid"></div>'
    )
    extra_head = f'<script src="{root}/js/search.js" defer></script>'
    html_doc = render_template(
        base_template,
        title=html.escape(f"{args.site_name} | Search"),
        root=root,
        content=content,
        sidebar=sidebar,
        site_name=site_name,
        site_description=site_description,
        year=str(dt.datetime.now().year),
        extra_head=extra_head,
    )
    write_text(output_dir / "search.html", html_doc)


def build_search_index(output_dir: Path, posts: list[dict]) -> None:
    index = []
    for post in posts:
        index.append(
            {
                "title": post["title"],
                "url": f"posts/{post['slug']}.html",
                "summary": post["summary"],
                "date": post["date"],
                "categories": [{"name": cat, "slug": slugify(cat)} for cat in post["categories"]],
            }
        )
    write_text(output_dir / "search-index.json", json.dumps(index, indent=2, ensure_ascii=True))


def build_site(args: argparse.Namespace) -> None:
    posts_dir = Path(args.posts)
    static_dir = Path(args.static)
    output_dir = Path(args.output)
    templates_dir = Path("templates")

    if not posts_dir.exists():
        print(f"Posts directory not found: {posts_dir}", file=sys.stderr)
        sys.exit(1)
    if not templates_dir.exists():
        print(f"Templates directory not found: {templates_dir}", file=sys.stderr)
        sys.exit(1)

    base_template = read_template(templates_dir / "base.html")

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "posts").mkdir(parents=True, exist_ok=True)
    (output_dir / "categories").mkdir(parents=True, exist_ok=True)

    if static_dir.exists():
        copy_static(static_dir, output_dir)

    custom_domain = (args.custom_domain or "").strip()
    if custom_domain:
        write_text(output_dir / "CNAME", f"{custom_domain}\n")

    posts = []
    md = markdown.Markdown(
        extensions=["fenced_code", "tables", "toc"],
        extension_configs={"toc": {"toc_depth": "2-4"}},
    )
    for md_file in sorted(posts_dir.glob("*.md")):
        raw_text = md_file.read_text(encoding="utf-8")
        meta, body = parse_front_matter(raw_text)
        title, body = extract_title(meta, body)
        date_dt = parse_date(meta, md_file)
        date_fmt = DATETIME_FMT if has_explicit_time(meta) else DATE_FMT
        date_str = date_dt.strftime(date_fmt)
        categories = get_categories(meta)
        slug = slugify(meta.get("slug", "")) if meta.get("slug") else slugify(md_file.stem)
        html_content = md.convert(body)
        toc_html = md.toc
        md.reset()
        html_content = fix_relative_img_src(html_content, "..")
        summary = meta.get("summary") or meta.get("description")
        if not summary:
            summary = strip_tags(html_content).strip().replace("\n", " ")
            summary = summary[:200] + ("..." if len(summary) > 200 else "")
        posts.append(
            {
                "title": title,
                "date": date_str,
                "date_dt": date_dt,
                "categories": categories,
                "slug": slug,
                "summary": summary,
                "content": html_content,
                "toc": toc_html,
            }
        )

    posts.sort(key=lambda p: p["date_dt"], reverse=True)

    category_map = {}
    for post in posts:
        for category in post["categories"]:
            category_map.setdefault(category, []).append(post)

    build_index(base_template, output_dir, posts, category_map, args)
    build_posts(base_template, output_dir, posts, category_map, args)
    build_categories(base_template, output_dir, category_map, args)
    build_search(base_template, output_dir, posts, category_map, args)
    build_search_index(output_dir, posts)


def main() -> None:
    pre_parser = argparse.ArgumentParser(add_help=False)
    pre_parser.add_argument("--config", default="site.json", help="Path to site config JSON.")
    pre_args, _ = pre_parser.parse_known_args()
    config = load_config(Path(pre_args.config))

    def cfg(key: str, default: str) -> str:
        value = config.get(key)
        return default if value is None else value

    parser = argparse.ArgumentParser(description="Simple Markdown blog generator.")
    parser.add_argument("--config", default=pre_args.config, help="Path to site config JSON.")
    parser.add_argument("--posts", default=cfg("posts", "posts"), help="Directory containing Markdown posts.")
    parser.add_argument("--static", default=cfg("static", "static"), help="Directory containing static assets.")
    parser.add_argument("--output", default=cfg("output", "dist"), help="Output directory for the site.")
    parser.add_argument("--site-name", default=cfg("site_name", "Simple MD Blog"), help="Site title.")
    parser.add_argument(
        "--site-description",
        default=cfg("site_description", "A tiny, fast Markdown blog for GitHub Pages."),
        help="Site description.",
    )
    parser.add_argument(
        "--custom-domain",
        default=cfg("custom_domain", ""),
        help="Custom domain to write into CNAME.",
    )
    args = parser.parse_args()
    build_site(args)
    print(f"Site generated in: {args.output}")


if __name__ == "__main__":
    main()
