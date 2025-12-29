from __future__ import annotations

import argparse
import datetime as dt
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import markdown

from .cache import hash_file, hash_paths, hash_text, list_files, load_lock, write_lock
from .config import load_config, resolve_about_html, resolve_analytics, resolve_widget_html
from .content import (
    count_words,
    extract_title,
    get_categories,
    normalize_list_spacing,
    parse_list,
    parse_date,
    parse_updated,
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
LOCK_VERSION = 1


def build_site(args: argparse.Namespace) -> bool:
    posts_dir = Path(args.posts)
    static_dir = Path(args.static)
    output_dir = Path(args.output)
    templates_dir = Path("templates")
    project_root = Path.cwd()
    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = (project_root / config_path).resolve()

    lock_path = Path(args.lock_file)
    if not lock_path.is_absolute():
        lock_path = config_path.parent / lock_path

    incremental = parse_bool(getattr(args, "incremental", True))
    stale_days = max(0, int(getattr(args, "stale_days", 0) or 0))
    build_workers = int(getattr(args, "build_workers", 0) or 0)
    if build_workers <= 0:
        build_workers = os.cpu_count() or 1
    build_workers = max(1, min(build_workers, 32))

    if not posts_dir.exists():
        print(f"Posts directory not found: {posts_dir}", file=sys.stderr)
        sys.exit(1)
    if not templates_dir.exists():
        print(f"Templates directory not found: {templates_dir}", file=sys.stderr)
        sys.exit(1)

    analytics_html = resolve_analytics(args)
    about_html = resolve_about_html(args)
    widget_html = resolve_widget_html(args)

    generator_paths = []
    build_script = project_root / "build.py"
    if build_script.exists():
        generator_paths.append(build_script)
    generator_paths.extend(list_files(project_root / "sitegen"))
    generator_hash = hash_paths(generator_paths, project_root) if generator_paths else ""
    templates_hash = hash_paths(list_files(templates_dir), project_root)
    config_hash = hash_file(config_path) if config_path.exists() else ""
    snippets_hash = hash_text("\n".join([analytics_html, widget_html, about_html]))
    static_hash = hash_paths(list_files(static_dir), project_root) if static_dir.exists() else ""

    about_page = Path("pages") / "about.md"
    about_page_hash = hash_file(about_page) if about_page.exists() else ""

    def rel_key(path: Path) -> str:
        try:
            return path.relative_to(project_root).as_posix()
        except ValueError:
            return path.resolve().as_posix()

    post_files = sorted(posts_dir.rglob("*.md"), key=lambda p: p.as_posix())
    current_posts = {}
    for md_file in post_files:
        current_posts[rel_key(md_file)] = {"hash": hash_file(md_file)}

    previous_state = load_lock(lock_path) if incremental else {}
    previous_posts = previous_state.get("posts", {}) if isinstance(previous_state, dict) else {}
    previous_hashes = {key: value.get("hash", "") for key, value in previous_posts.items()}
    current_hashes = {key: value.get("hash", "") for key, value in current_posts.items()}

    added_posts = {key for key in current_hashes if key not in previous_hashes}
    removed_posts = {key for key in previous_hashes if key not in current_hashes}
    modified_posts = {key for key in current_hashes if key in previous_hashes and current_hashes[key] != previous_hashes[key]}
    posts_changed = bool(added_posts or removed_posts or modified_posts)

    def stale_status_changed(state: dict) -> bool:
        if stale_days <= 0:
            return False
        if not state:
            return True
        built_at = state.get("built_at")
        if not built_at:
            return True
        try:
            built_at_dt = dt.datetime.fromisoformat(built_at)
        except ValueError:
            return True
        now = dt.datetime.now()
        threshold = dt.timedelta(days=stale_days)
        for info in state.get("posts", {}).values():
            if parse_bool(info.get("draft")):
                continue
            updated_value = info.get("updated")
            if not updated_value:
                continue
            try:
                updated_dt = dt.datetime.fromisoformat(updated_value)
            except ValueError:
                continue
            was_stale = (built_at_dt - updated_dt) > threshold
            is_stale = (now - updated_dt) > threshold
            if is_stale and not was_stale:
                return True
        return False

    stale_changed = stale_status_changed(previous_state) if incremental else False

    output_exists = output_dir.exists()
    lock_ok = previous_state.get("version") == LOCK_VERSION if previous_state else False
    no_changes = (
        incremental
        and output_exists
        and lock_ok
        and generator_hash == previous_state.get("generator_hash")
        and templates_hash == previous_state.get("templates_hash")
        and config_hash == previous_state.get("config_hash")
        and snippets_hash == previous_state.get("snippets_hash")
        and static_hash == previous_state.get("static_hash")
        and about_page_hash == previous_state.get("about_page_hash")
        and not posts_changed
        and not stale_changed
    )
    if no_changes:
        print("No changes detected. Build skipped.")
        return False

    full_rebuild = (
        not incremental
        or not output_exists
        or not lock_ok
        or generator_hash != previous_state.get("generator_hash")
        or templates_hash != previous_state.get("templates_hash")
        or config_hash != previous_state.get("config_hash")
        or snippets_hash != previous_state.get("snippets_hash")
        or args.clean
    )
    static_changed = full_rebuild or static_hash != previous_state.get("static_hash")
    aggregate_needed = full_rebuild or posts_changed or stale_changed
    about_changed = full_rebuild or posts_changed or about_page_hash != previous_state.get("about_page_hash")

    if full_rebuild and args.clean:
        clean_output_dir(output_dir, project_root)

    base_template = read_template(templates_dir / "base.html")

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "posts").mkdir(parents=True, exist_ok=True)
    (output_dir / "categories").mkdir(parents=True, exist_ok=True)

    if static_dir.exists() and static_changed:
        copy_static(static_dir, output_dir)

    custom_domain = (args.custom_domain or "").strip()
    if custom_domain:
        write_text(output_dir / "CNAME", f"{custom_domain}\n")
    if args.write_nojekyll:
        write_nojekyll(output_dir)

    site_url = (args.site_url or "").strip()
    if not site_url and custom_domain:
        site_url = f"https://{custom_domain}"

    posts = []
    current_post_state = {}
    changed_slugs = set()
    category_hash = previous_state.get("category_hash", "")
    archive_hash = previous_state.get("archive_hash", "")
    if aggregate_needed or about_changed:
        def parse_post_data(md_file: Path) -> dict:
            rel = rel_key(md_file)
            raw_text = md_file.read_text(encoding="utf-8")
            meta, body = parse_front_matter(raw_text)
            is_draft = parse_bool(meta.get("draft"))
            title, body = extract_title(meta, body)
            body = normalize_list_spacing(body)
            date_dt, time_used = parse_date(meta, md_file)
            date_fmt = DATETIME_FMT if time_used else DATE_FMT
            date_str = date_dt.strftime(date_fmt)
            updated_dt, updated_time_used = parse_updated(meta, md_file)
            updated_fmt = DATETIME_FMT if updated_time_used else DATE_FMT
            updated_str = updated_dt.strftime(updated_fmt)
            categories = get_categories(meta)
            archive_value = meta.get("archive") or []
            if isinstance(archive_value, list):
                archive_labels = [str(item).strip() for item in archive_value if str(item).strip()]
            else:
                archive_labels = parse_list(str(archive_value))
            explicit_slug = (meta.get("slug") or "").strip()
            candidate_slug = slugify(explicit_slug) if explicit_slug else slugify(md_file.stem)
            result = {
                "rel": rel,
                "draft": is_draft,
                "title": title,
                "date": date_str,
                "date_dt": date_dt,
                "updated": updated_str,
                "updated_dt": updated_dt,
                "categories": categories,
                "archives": archive_labels,
                "explicit_slug": explicit_slug,
                "candidate_slug": candidate_slug,
            }
            if is_draft:
                return result
            md = markdown.Markdown(
                extensions=["fenced_code", "tables", "toc"],
                extension_configs={"toc": {"toc_depth": args.toc_depth}},
            )
            html_content = md.convert(body)
            toc_html = md.toc
            md.reset()
            html_content = fix_relative_img_src(html_content, "..")
            summary = meta.get("summary") or meta.get("description")
            if not summary:
                summary = strip_tags(html_content).strip().replace("\n", " ")
                summary = summary[:200] + ("..." if len(summary) > 200 else "")
            word_count = count_words(strip_tags(html_content))
            result.update(
                {
                    "summary": summary,
                    "content": html_content,
                    "toc": toc_html,
                    "words": word_count,
                }
            )
            return result

        parse_workers = min(build_workers, len(post_files)) if post_files else 1
        if parse_workers > 1:
            with ThreadPoolExecutor(max_workers=parse_workers) as executor:
                parsed_posts = list(executor.map(parse_post_data, post_files))
        else:
            parsed_posts = [parse_post_data(path) for path in post_files]

        used_slugs = set()
        for info in parsed_posts:
            rel = info["rel"]
            explicit_slug = info["explicit_slug"]
            candidate_slug = info["candidate_slug"]
            previous_slug = ""
            if not explicit_slug:
                previous_slug = previous_posts.get(rel, {}).get("slug", "")
            if previous_slug and previous_slug not in used_slugs:
                slug = previous_slug
            elif candidate_slug not in used_slugs:
                slug = candidate_slug
            else:
                base_hash = hash_text(rel)[:8]
                slug = f"{candidate_slug}-{base_hash}"
                if slug in used_slugs:
                    for length in (10, 12, 16):
                        slug = f"{candidate_slug}-{hash_text(rel)[:length]}"
                        if slug not in used_slugs:
                            break
                if slug in used_slugs:
                    counter = 2
                    while True:
                        slug = f"{candidate_slug}-{counter}"
                        if slug not in used_slugs:
                            break
                        counter += 1
            used_slugs.add(slug)
            current_posts[rel]["slug"] = slug
            current_posts[rel]["draft"] = info["draft"]
            current_posts[rel]["updated"] = info["updated_dt"].replace(microsecond=0).isoformat()
            if info["draft"]:
                continue
            posts.append(
                {
                    "title": info["title"],
                    "date": info["date"],
                    "date_dt": info["date_dt"],
                    "updated": info["updated"],
                    "updated_dt": info["updated_dt"],
                    "categories": info["categories"],
                    "slug": slug,
                    "summary": info["summary"],
                    "content": info["content"],
                    "toc": info["toc"],
                    "archives": info["archives"],
                    "words": info["words"],
                    "source": rel,
                }
            )
        changed_paths = added_posts | modified_posts
        changed_slugs = {post["slug"] for post in posts if post["source"] in changed_paths}
        current_post_state = {
            key: {
                "hash": current_posts[key]["hash"],
                "slug": current_posts[key].get("slug", ""),
                "draft": current_posts[key].get("draft", False),
                "updated": current_posts[key].get("updated", ""),
            }
            for key in current_posts
        }
    else:
        current_post_state = previous_posts

    posts.sort(key=lambda p: p["date_dt"], reverse=True)

    category_map = {}
    for post in posts:
        for category in post["categories"]:
            category_map.setdefault(category, []).append(post)

    if aggregate_needed or about_changed:
        category_parts = [
            f"{name}:{len(items)}" for name, items in sorted(category_map.items(), key=lambda x: x[0].lower())
        ]
        category_hash = hash_text("|".join(category_parts))
        archive_groups = {}
        for post in posts:
            for label in post.get("archives", []):
                archive_groups.setdefault(label, []).append(post["slug"])
        archive_parts = []
        for label in sorted(archive_groups):
            archive_parts.append(f"{label}:{','.join(sorted(archive_groups[label]))}")
        archive_hash = hash_text("|".join(archive_parts))

    if aggregate_needed:
        total_pages = build_index(
            base_template, output_dir, posts, category_map, args, analytics_html, about_html, widget_html
        )
        rebuild_all_posts = (
            full_rebuild
            or stale_changed
            or category_hash != previous_state.get("category_hash")
            or archive_hash != previous_state.get("archive_hash")
        )
        if rebuild_all_posts:
            build_posts(
                base_template,
                output_dir,
                posts,
                category_map,
                args,
                analytics_html,
                about_html,
                widget_html,
                workers=build_workers,
            )
        elif changed_slugs:
            build_posts(
                base_template,
                output_dir,
                posts,
                category_map,
                args,
                analytics_html,
                about_html,
                widget_html,
                only_slugs=changed_slugs,
                workers=build_workers,
            )
        build_categories(base_template, output_dir, category_map, args, analytics_html, about_html, widget_html)
        build_search(base_template, output_dir, posts, category_map, args, analytics_html, about_html, widget_html)
        build_search_index(output_dir, posts)
        build_archive(base_template, output_dir, posts, category_map, args, analytics_html, about_html, widget_html)
        if args.enable_rss:
            build_rss(output_dir, posts, site_url, args, args.feed_limit)
        if args.enable_atom:
            build_atom(output_dir, posts, site_url, args, args.feed_limit)
        if args.enable_sitemap:
            build_sitemap(output_dir, posts, category_map, site_url, total_pages)
        if args.enable_404:
            build_404(base_template, output_dir, category_map, args, analytics_html, about_html, widget_html)
    if about_changed:
        build_about(base_template, output_dir, category_map, args, analytics_html, about_html, widget_html)

    if output_exists and aggregate_needed:
        removed_slugs = set()
        for rel in removed_posts:
            slug = previous_posts.get(rel, {}).get("slug")
            if slug:
                removed_slugs.add(slug)
        for rel, data in current_post_state.items():
            prev = previous_posts.get(rel, {})
            prev_slug = prev.get("slug")
            prev_draft = parse_bool(prev.get("draft"))
            if prev_slug and prev_draft is False and data.get("draft") is True:
                removed_slugs.add(prev_slug)
            if prev_slug and data.get("slug") and prev_slug != data.get("slug"):
                removed_slugs.add(prev_slug)
        for slug in removed_slugs:
            path = output_dir / "posts" / f"{slug}.html"
            try:
                path.unlink()
            except FileNotFoundError:
                pass

    build_state = {
        "version": LOCK_VERSION,
        "built_at": dt.datetime.now().replace(microsecond=0).isoformat(),
        "generator_hash": generator_hash,
        "templates_hash": templates_hash,
        "config_hash": config_hash,
        "snippets_hash": snippets_hash,
        "static_hash": static_hash,
        "about_page_hash": about_page_hash,
        "category_hash": category_hash,
        "archive_hash": archive_hash,
        "posts": current_post_state,
    }
    write_lock(lock_path, build_state)
    return True


def main() -> None:
    pre_parser = argparse.ArgumentParser(add_help=False)
    pre_parser.add_argument(
        "--config",
        default="site.toml",
        help="Path to site config file (TOML/YAML/JSON).",
    )
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
    parser.add_argument("--config", default=pre_args.config, help="Path to site config file (TOML/YAML/JSON).")
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
        "--posts-per-page",
        default=cfg_int("posts_per_page", 8),
        type=int,
        help="Number of posts on the home page before pagination.",
    )
    parser.add_argument(
        "--build-workers",
        default=cfg_int("build_workers", 0),
        type=int,
        help="Number of worker threads for parsing/rendering (0 = auto).",
    )
    parser.add_argument(
        "--toc-depth",
        default=cfg_str("toc_depth", "2-4"),
        help="Heading depth range for TOC (e.g. 2-4).",
    )
    parser.add_argument(
        "--show-updated",
        action=argparse.BooleanOptionalAction,
        default=cfg_bool("show_updated", True),
        help="Show updated date on post pages.",
    )
    parser.add_argument(
        "--stale-days",
        default=cfg_int("stale_days", 365),
        type=int,
        help="Days before a post is marked as stale (0 to disable).",
    )
    parser.add_argument(
        "--stale-notice",
        default=cfg_str("stale_notice", "This post may be outdated."),
        help="Notice text for stale posts.",
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
        "--incremental",
        action=argparse.BooleanOptionalAction,
        default=cfg_bool("incremental", True),
        help="Enable incremental build using the lock file.",
    )
    parser.add_argument(
        "--lock-file",
        default=cfg_str("lock_file", "build.lock.json"),
        help="Path to build lock JSON.",
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
        "--widget-file",
        default=cfg_str("widget_file", ""),
        help="Path to data widget HTML snippet file.",
    )
    parser.add_argument(
        "--widget-html",
        default=cfg_str("widget_html", ""),
        help="Inline data widget HTML snippet.",
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
    start = time.perf_counter()
    built = build_site(args)
    elapsed = time.perf_counter() - start
    print(f"Build completed in {elapsed:.2f}s.")
    if built:
        print(f"Site generated in: {args.output}")
