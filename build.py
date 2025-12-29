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
FEED_LIMIT = 20
IMG_SRC_RE = re.compile(r'<img([^>]*?)src="([^"]+)"', re.IGNORECASE)
TAG_RE = re.compile(r"<[^>]+>")
LIST_MARKER_RE = re.compile(r"^(?P<indent>[ \t]*)(?:[-+*]|\d+[.)])\s+")
FENCE_RE = re.compile(r"^(?P<indent>[ \t]*)(`{3,}|~{3,})")
DOUBLE_QUOTE_RE = re.compile(r"^(?P<indent>[ \t]*)>>(?!>)(?P<rest>.*)$")


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
    write_text(output_dir / ".nojekyll", "")


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


def resolve_analytics(args: argparse.Namespace) -> str:
    html_snippet = (args.analytics_html or "").strip()
    if html_snippet:
        return html_snippet
    file_value = (args.analytics_file or "").strip()
    if not file_value:
        return ""
    path = Path(file_value)
    if not path.is_absolute():
        config_path = Path(args.config).resolve()
        path = config_path.parent / path
    if not path.exists():
        print(f"Analytics file not found: {path}", file=sys.stderr)
        return ""
    return path.read_text(encoding="utf-8")


def resolve_about_html(args: argparse.Namespace) -> str:
    html_snippet = (args.about_html or "").strip()
    if html_snippet:
        return html_snippet

    file_value = (args.about_file or "").strip()
    if file_value:
        path = Path(file_value)
        if not path.is_absolute():
            config_path = Path(args.config).resolve()
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

    text_value = (args.about_text or "").strip()
    if text_value:
        escaped = html.escape(text_value).replace("\n", "<br>")
        return f"<p>{escaped}</p>"

    return f"<p>{html.escape(args.site_description)}</p>"


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


def build_sidebar(category_map: dict, root: str, about_html: str, toc_html: str = "") -> str:
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
        f"{about_html}"
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
    base_template: str,
    output_dir: Path,
    posts: list[dict],
    category_map: dict,
    args: argparse.Namespace,
    analytics_html: str,
    about_html: str,
) -> None:
    root = "."
    sidebar = build_sidebar(category_map, root, about_html)
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
        analytics=analytics_html,
    )
    write_text(output_dir / "index.html", html_doc)


def build_posts(
    base_template: str,
    output_dir: Path,
    posts: list[dict],
    category_map: dict,
    args: argparse.Namespace,
    analytics_html: str,
    about_html: str,
) -> None:
    root = ".."
    site_name = html.escape(args.site_name)
    site_description = html.escape(args.site_description)
    for post in posts:
        sidebar = build_sidebar(category_map, root, about_html, post.get("toc", ""))
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
            analytics=analytics_html,
        )
        write_text(output_dir / "posts" / f"{post['slug']}.html", html_doc)


def build_categories(
    base_template: str,
    output_dir: Path,
    category_map: dict,
    args: argparse.Namespace,
    analytics_html: str,
    about_html: str,
) -> None:
    root = ".."
    sidebar = build_sidebar(category_map, root, about_html)
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
            analytics=analytics_html,
        )
        write_text(output_dir / "categories" / f"{slugify(category)}.html", html_doc)


def build_search(
    base_template: str,
    output_dir: Path,
    posts: list[dict],
    category_map: dict,
    args: argparse.Namespace,
    analytics_html: str,
    about_html: str,
) -> None:
    root = "."
    sidebar = build_sidebar(category_map, root, about_html)
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
        analytics=analytics_html,
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


def build_about(
    base_template: str,
    output_dir: Path,
    category_map: dict,
    args: argparse.Namespace,
    analytics_html: str,
    about_html: str,
) -> None:
    about_path = Path("pages") / "about.md"
    if not about_path.exists():
        return
    raw_text = about_path.read_text(encoding="utf-8")
    meta, body = parse_front_matter(raw_text)
    title, body = extract_title(meta, body)
    body = normalize_list_spacing(body)
    md = markdown.Markdown(
        extensions=["fenced_code", "tables", "toc"],
        extension_configs={"toc": {"toc_depth": args.toc_depth}},
    )
    html_content = md.convert(body)
    toc_html = md.toc
    md.reset()
    html_content = fix_relative_img_src(html_content, ".")
    sidebar = build_sidebar(category_map, ".", about_html, toc_html)
    content = (
        '<article class="post">'
        f'<h1 class="post-title">{html.escape(title)}</h1>'
        f'<div class="post-body">{html_content}</div>'
        "</article>"
    )
    html_doc = render_template(
        base_template,
        title=html.escape(f"{title} | {args.site_name}"),
        root=".",
        content=content,
        sidebar=sidebar,
        site_name=html.escape(args.site_name),
        site_description=html.escape(args.site_description),
        year=str(dt.datetime.now().year),
        extra_head="",
        analytics=analytics_html,
    )
    write_text(output_dir / "about.html", html_doc)


def build_archive(
    base_template: str,
    output_dir: Path,
    posts: list[dict],
    category_map: dict,
    args: argparse.Namespace,
    analytics_html: str,
    about_html: str,
) -> None:
    root = "."
    sidebar = build_sidebar(category_map, root, about_html)
    archive_groups: dict[str, list[dict]] = {}
    date_groups: dict[str, list[dict]] = {}
    year_counts: dict[int, int] = {}
    for post in posts:
        year_counts[post["date_dt"].year] = year_counts.get(post["date_dt"].year, 0) + 1
        label = post.get("archive") or ""
        if label:
            archive_groups.setdefault(label, []).append(post)
        else:
            key = post["date_dt"].strftime("%Y-%m")
            date_groups.setdefault(key, []).append(post)

    def render_group(title: str, items: list[dict]) -> str:
        rows = []
        for item in items:
            item_title = html.escape(item["title"])
            url = f'{root}/posts/{item["slug"]}.html'
            rows.append(
                f'<li><span class="archive-date">{item["date"]}</span>'
                f'<a href="{url}">{item_title}</a></li>'
            )
        return (
            f'<section class="archive-group"><h3>{html.escape(title)}</h3>'
            f'<ul class="archive-list">{"".join(rows)}</ul></section>'
        )

    group_sections: list[str] = []
    for label, items in sorted(
        archive_groups.items(),
        key=lambda x: max((p["date_dt"] for p in x[1]), default=dt.datetime.min),
        reverse=True,
    ):
        items.sort(key=lambda p: p["date_dt"], reverse=True)
        group_sections.append(render_group(label, items))
    for key, items in sorted(date_groups.items(), key=lambda x: x[0], reverse=True):
        items.sort(key=lambda p: p["date_dt"], reverse=True)
        group_sections.append(render_group(key, items))

    year_rows = []
    for year, count in sorted(year_counts.items(), key=lambda x: x[0], reverse=True):
        year_rows.append(
            f'<li><span class="archive-year">{year}</span>'
            f'<span class="archive-count">{count}</span></li>'
        )
    stats_html = (
        '<div class="archive-stats">'
        f'<div class="archive-total">Total {len(posts)} posts</div>'
        f'<ul class="archive-year-list">{"".join(year_rows)}</ul>'
        "</div>"
        if posts
        else ""
    )

    content = (
        '<div class="section-head">'
        "<h2>Archive</h2>"
        "<p>All posts by date.</p>"
        "</div>"
        f"{stats_html}"
        f'{"".join(group_sections)}'
    )
    html_doc = render_template(
        base_template,
        title=html.escape(f"Archive | {args.site_name}"),
        root=root,
        content=content,
        sidebar=sidebar,
        site_name=html.escape(args.site_name),
        site_description=html.escape(args.site_description),
        year=str(dt.datetime.now().year),
        extra_head="",
        analytics=analytics_html,
    )
    write_text(output_dir / "archive.html", html_doc)


def build_rss(
    output_dir: Path, posts: list[dict], site_url: str, args: argparse.Namespace, feed_limit: int
) -> None:
    if not site_url:
        return
    site_url = site_url.rstrip("/")
    items = []
    for post in posts[:feed_limit]:
        link = join_url(site_url, f"posts/{post['slug']}.html")
        items.append(
            "\n".join(
                [
                    "<item>",
                    f"<title>{html.escape(post['title'])}</title>",
                    f"<link>{link}</link>",
                    f"<guid>{link}</guid>",
                    f"<pubDate>{rfc822_date(post['date_dt'])}</pubDate>",
                    f"<description>{html.escape(post['summary'])}</description>",
                    "</item>",
                ]
            )
        )
    last_build = rfc822_date(posts[0]["date_dt"]) if posts else rfc822_date(dt.datetime.utcnow())
    rss = "\n".join(
        [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<rss version="2.0">',
            "<channel>",
            f"<title>{html.escape(args.site_name)}</title>",
            f"<link>{site_url}/</link>",
            f"<description>{html.escape(args.site_description)}</description>",
            f"<lastBuildDate>{last_build}</lastBuildDate>",
            "\n".join(items),
            "</channel>",
            "</rss>",
        ]
    )
    write_text(output_dir / "rss.xml", rss)


def build_atom(
    output_dir: Path, posts: list[dict], site_url: str, args: argparse.Namespace, feed_limit: int
) -> None:
    if not site_url:
        return
    site_url = site_url.rstrip("/")
    updated = iso_date(posts[0]["date_dt"]) if posts else iso_date(dt.datetime.utcnow())
    entries = []
    for post in posts[:feed_limit]:
        link = join_url(site_url, f"posts/{post['slug']}.html")
        entries.append(
            "\n".join(
                [
                    "<entry>",
                    f"<title>{html.escape(post['title'])}</title>",
                    f"<link href=\"{link}\" />",
                    f"<id>{link}</id>",
                    f"<updated>{iso_date(post['date_dt'])}</updated>",
                    f"<summary>{html.escape(post['summary'])}</summary>",
                    "</entry>",
                ]
            )
        )
    atom = "\n".join(
        [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<feed xmlns="http://www.w3.org/2005/Atom">',
            f"<title>{html.escape(args.site_name)}</title>",
            f"<id>{site_url}/</id>",
            f"<updated>{updated}</updated>",
            f'<link href="{site_url}/atom.xml" rel="self" />',
            f'<link href="{site_url}/" />',
            "\n".join(entries),
            "</feed>",
        ]
    )
    write_text(output_dir / "atom.xml", atom)


def build_sitemap(output_dir: Path, posts: list[dict], category_map: dict, site_url: str) -> None:
    if not site_url:
        return
    site_url = site_url.rstrip("/")
    urls = [
        (site_url + "/", None),
        (join_url(site_url, "about.html"), None),
        (join_url(site_url, "archive.html"), None),
        (join_url(site_url, "search.html"), None),
        (join_url(site_url, "rss.xml"), None),
        (join_url(site_url, "atom.xml"), None),
        (join_url(site_url, "404.html"), None),
    ]
    for post in posts:
        urls.append((join_url(site_url, f"posts/{post['slug']}.html"), post["date_dt"]))
    for category in category_map.keys():
        urls.append((join_url(site_url, f"categories/{slugify(category)}.html"), None))
    items = []
    for url, lastmod in urls:
        if lastmod:
            items.append(
                "\n".join(
                    [
                        "<url>",
                        f"<loc>{url}</loc>",
                        f"<lastmod>{lastmod.date().isoformat()}</lastmod>",
                        "</url>",
                    ]
                )
            )
        else:
            items.append(
                "\n".join(
                    [
                        "<url>",
                        f"<loc>{url}</loc>",
                        "</url>",
                    ]
                )
            )
    sitemap = "\n".join(
        [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
            "\n".join(items),
            "</urlset>",
        ]
    )
    write_text(output_dir / "sitemap.xml", sitemap)


def build_404(
    base_template: str,
    output_dir: Path,
    category_map: dict,
    args: argparse.Namespace,
    analytics_html: str,
    about_html: str,
) -> None:
    root = "."
    sidebar = build_sidebar(category_map, root, about_html)
    content = (
        '<div class="section-head">'
        "<h2>404</h2>"
        "<p>Page not found. Try heading back to the homepage.</p>"
        "</div>"
        '<div class="post-card">'
        '<p class="post-summary">The page you requested does not exist.</p>'
        f'<a class="post-more" href="{root}/index.html">Back to home</a>'
        "</div>"
    )
    html_doc = render_template(
        base_template,
        title=html.escape(f"404 | {args.site_name}"),
        root=root,
        content=content,
        sidebar=sidebar,
        site_name=html.escape(args.site_name),
        site_description=html.escape(args.site_description),
        year=str(dt.datetime.now().year),
        extra_head="",
        analytics=analytics_html,
    )
    write_text(output_dir / "404.html", html_doc)


def build_site(args: argparse.Namespace) -> None:
    posts_dir = Path(args.posts)
    static_dir = Path(args.static)
    output_dir = Path(args.output)
    templates_dir = Path("templates")
    project_root = Path.cwd()

    if not posts_dir.exists():
        print(f"Posts directory not found: {posts_dir}", file=sys.stderr)
        sys.exit(1)
    if not templates_dir.exists():
        print(f"Templates directory not found: {templates_dir}", file=sys.stderr)
        sys.exit(1)

    if args.clean:
        clean_output_dir(output_dir, project_root)

    base_template = read_template(templates_dir / "base.html")

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "posts").mkdir(parents=True, exist_ok=True)
    (output_dir / "categories").mkdir(parents=True, exist_ok=True)

    if static_dir.exists():
        copy_static(static_dir, output_dir)

    custom_domain = (args.custom_domain or "").strip()
    if custom_domain:
        write_text(output_dir / "CNAME", f"{custom_domain}\n")
    if args.write_nojekyll:
        write_nojekyll(output_dir)

    analytics_html = resolve_analytics(args)
    about_html = resolve_about_html(args)
    site_url = (args.site_url or "").strip()
    if not site_url and custom_domain:
        site_url = f"https://{custom_domain}"

    posts = []
    md = markdown.Markdown(
        extensions=["fenced_code", "tables", "toc"],
        extension_configs={"toc": {"toc_depth": args.toc_depth}},
    )
    for md_file in sorted(posts_dir.glob("*.md")):
        raw_text = md_file.read_text(encoding="utf-8")
        meta, body = parse_front_matter(raw_text)
        if parse_bool(meta.get("draft")):
            continue
        title, body = extract_title(meta, body)
        body = normalize_list_spacing(body)
        date_dt, time_used = parse_date(meta, md_file)
        date_fmt = DATETIME_FMT if time_used else DATE_FMT
        date_str = date_dt.strftime(date_fmt)
        categories = get_categories(meta)
        slug = slugify(meta.get("slug", "")) if meta.get("slug") else slugify(md_file.stem)
        archive_label = (meta.get("archive") or "").strip()
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
                "archive": archive_label,
            }
        )

    posts.sort(key=lambda p: p["date_dt"], reverse=True)

    category_map = {}
    for post in posts:
        for category in post["categories"]:
            category_map.setdefault(category, []).append(post)

    build_index(base_template, output_dir, posts, category_map, args, analytics_html, about_html)
    build_posts(base_template, output_dir, posts, category_map, args, analytics_html, about_html)
    build_categories(base_template, output_dir, category_map, args, analytics_html, about_html)
    build_search(base_template, output_dir, posts, category_map, args, analytics_html, about_html)
    build_search_index(output_dir, posts)
    build_about(base_template, output_dir, category_map, args, analytics_html, about_html)
    build_archive(base_template, output_dir, posts, category_map, args, analytics_html, about_html)
    if args.enable_rss:
        build_rss(output_dir, posts, site_url, args, args.feed_limit)
    if args.enable_atom:
        build_atom(output_dir, posts, site_url, args, args.feed_limit)
    if args.enable_sitemap:
        build_sitemap(output_dir, posts, category_map, site_url)
    if args.enable_404:
        build_404(base_template, output_dir, category_map, args, analytics_html, about_html)


def main() -> None:
    pre_parser = argparse.ArgumentParser(add_help=False)
    pre_parser.add_argument("--config", default="site.json", help="Path to site config JSON.")
    pre_args, _ = pre_parser.parse_known_args()
    config = load_config(Path(pre_args.config))

    def cfg_value(key: str, default: object) -> object:
        value = config.get(key)
        return default if value is None else value

    def cfg_str(key: str, default: str) -> str:
        value = cfg_value(key, default)
        return default if value is None else str(value)

    def cfg_bool(key: str, default: bool) -> bool:
        value = cfg_value(key, default)
        return parse_bool(value) if value is not None else default

    def cfg_int(key: str, default: int) -> int:
        value = cfg_value(key, default)
        return parse_int(value, default)

    parser = argparse.ArgumentParser(description="Simple Markdown blog generator.")
    parser.add_argument("--config", default=pre_args.config, help="Path to site config JSON.")
    parser.add_argument("--posts", default=cfg_str("posts", "posts"), help="Directory containing Markdown posts.")
    parser.add_argument("--static", default=cfg_str("static", "static"), help="Directory containing static assets.")
    parser.add_argument("--output", default=cfg_str("output", "dist"), help="Output directory for the site.")
    parser.add_argument("--site-name", default=cfg_str("site_name", "Simple MD Blog"), help="Site title.")
    parser.add_argument(
        "--site-description",
        default=cfg_str("site_description", "A tiny, fast Markdown blog for GitHub Pages."),
        help="Site description.",
    )
    parser.add_argument(
        "--custom-domain",
        default=cfg_str("custom_domain", ""),
        help="Custom domain to write into CNAME.",
    )
    parser.add_argument(
        "--site-url",
        default=cfg_str("site_url", ""),
        help="Public site URL used for RSS and sitemap.",
    )
    parser.add_argument(
        "--clean",
        action=argparse.BooleanOptionalAction,
        default=cfg_bool("clean", True),
        help="Clean output directory before build.",
    )
    parser.add_argument(
        "--feed-limit",
        default=cfg_int("feed_limit", FEED_LIMIT),
        type=int,
        help="Maximum number of posts in RSS/Atom feeds.",
    )
    parser.add_argument(
        "--toc-depth",
        default=cfg_str("toc_depth", "2-4"),
        help="Heading depth range for TOC (e.g. 2-4).",
    )
    parser.add_argument(
        "--enable-rss",
        action=argparse.BooleanOptionalAction,
        default=cfg_bool("enable_rss", True),
        help="Generate rss.xml.",
    )
    parser.add_argument(
        "--enable-atom",
        action=argparse.BooleanOptionalAction,
        default=cfg_bool("enable_atom", True),
        help="Generate atom.xml.",
    )
    parser.add_argument(
        "--enable-sitemap",
        action=argparse.BooleanOptionalAction,
        default=cfg_bool("enable_sitemap", True),
        help="Generate sitemap.xml.",
    )
    parser.add_argument(
        "--enable-404",
        action=argparse.BooleanOptionalAction,
        default=cfg_bool("enable_404", True),
        help="Generate 404.html.",
    )
    parser.add_argument(
        "--write-nojekyll",
        action=argparse.BooleanOptionalAction,
        default=cfg_bool("write_nojekyll", True),
        help="Write .nojekyll in the output directory.",
    )
    parser.add_argument(
        "--analytics-file",
        default=cfg_str("analytics_file", ""),
        help="Path to analytics HTML snippet file.",
    )
    parser.add_argument(
        "--analytics-html",
        default=cfg_str("analytics_html", ""),
        help="Inline analytics HTML snippet.",
    )
    parser.add_argument(
        "--about-text",
        default=cfg_str("about_text", ""),
        help="Text content for the sidebar About panel.",
    )
    parser.add_argument(
        "--about-html",
        default=cfg_str("about_html", ""),
        help="HTML content for the sidebar About panel.",
    )
    parser.add_argument(
        "--about-file",
        default=cfg_str("about_file", ""),
        help="Path to file used for the sidebar About panel.",
    )
    args = parser.parse_args()
    build_site(args)
    print(f"Site generated in: {args.output}")


if __name__ == "__main__":
    main()
