from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

import markdown

from .config import load_config, resolve_about_html, resolve_analytics
from .content import (
    extract_title,
    get_categories,
    normalize_list_spacing,
    parse_date,
    parse_front_matter,
    slugify,
)
from .pages import (
    build_404,
    build_about,
    build_archive,
    build_atom,
    build_categories,
    build_index,
    build_posts,
    build_rss,
    build_search,
    build_search_index,
    build_sitemap,
)
from .render import copy_static, fix_relative_img_src, read_template, strip_tags, write_text
from .utils import clean_output_dir, parse_bool, parse_int, write_nojekyll

DATE_FMT = "%Y-%m-%d"
DATETIME_FMT = "%Y-%m-%d %H:%M"
FEED_LIMIT = 20


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
