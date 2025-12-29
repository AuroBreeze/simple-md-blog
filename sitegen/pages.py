from __future__ import annotations

import datetime as dt
import math
import html
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import markdown

from .content import extract_title, normalize_list_spacing, parse_front_matter, slugify
from .render import fix_relative_img_src, render_template, strip_tags, write_text
from .utils import iso_date, join_url, parse_bool, rfc822_date


def build_category_list(category_map: dict, root: str) -> str:
    items = []
    for name, posts in sorted(category_map.items(), key=lambda x: (-len(x[1]), x[0].lower())):
        slug = slugify(name)
        items.append(
            f'<li><a href="{root}/categories/{slug}.html">{html.escape(name)}</a>'
            f'<span class="count">{len(posts)}</span></li>'
        )
    return "\n".join(items) if items else "<li>No categories yet.</li>"


def build_sidebar(
    category_map: dict, root: str, about_html: str, toc_html: str = "", widget_html: str = ""
) -> str:
    categories_html = build_category_list(category_map, root)
    panels = [
        '<div class="panel">'
        "<h3>About</h3>"
        f"{about_html}"
        "</div>"
    ]
    if widget_html:
        panels.append(
            '<div class="panel panel-widget">'
            "<h3>Stats</h3>"
            f"{widget_html}"
            "</div>"
        )
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


def build_archive_sidebar(post: dict, archive_map: dict, root: str) -> tuple[str, bool]:
    labels = post.get("archives") or []
    if not labels:
        return "", False
    sections = []
    for label in labels:
        related = [item for item in archive_map.get(label, []) if item["slug"] != post["slug"]]
        if not related:
            continue
        rows = []
        for item in related:
            url = f"{root}/posts/{item['slug']}.html"
            rows.append(
                f'<li><a href="{url}">{html.escape(item["title"])}</a>'
                f'<span class="archive-date">{item["date"]}</span></li>'
            )
        sections.append(
            f'<div class="sidebar-archive-group"><h4>{html.escape(label)}</h4>'
            f'<ul class="sidebar-archive-list">{"".join(rows)}</ul></div>'
        )
    if not sections:
        return '<p class="sidebar-empty">No other posts in this archive yet.</p>', True
    return "".join(sections), True


def build_tabbed_panel(sections: list[tuple[str, str, str]]) -> str:
    if not sections:
        return ""
    active_id = sections[0][0]
    buttons = []
    panels = []
    for tab_id, label, body in sections:
        active_class = " is-active" if tab_id == active_id else ""
        buttons.append(
            f'<button class="sidebar-tab{active_class}" type="button" data-tab="{tab_id}">{label}</button>'
        )
        panels.append(
            f'<section class="sidebar-tabpanel{active_class}" data-tab="{tab_id}">{body}</section>'
        )
    return (
        '<div class="panel sidebar-tabs" data-tabs>'
        f'<div class="sidebar-tablist">{"".join(buttons)}</div>'
        f'<div class="sidebar-tabcontent">{"".join(panels)}</div>'
        "</div>"
    )


def build_post_sidebar(
    category_map: dict,
    root: str,
    about_html: str,
    toc_html: str,
    post: dict,
    archive_map: dict,
    widget_html: str,
) -> str:
    categories_html = build_category_list(category_map, root)
    panels = [
        '<div class="panel">'
        "<h3>About</h3>"
        f"{about_html}"
        "</div>"
    ]
    if widget_html:
        panels.append(
            '<div class="panel panel-widget">'
            "<h3>Stats</h3>"
            f"{widget_html}"
            "</div>"
        )
    sections = []
    if toc_html and "<li" in toc_html:
        sections.append(("contents", "Contents", toc_html))
    archive_html, has_archive = build_archive_sidebar(post, archive_map, root)
    if has_archive:
        sections.append(("archive", "Archive", archive_html))
    sections.append(("categories", "Categories", f'<ul class="category-list">{categories_html}</ul>'))
    if len(sections) == 1:
        tab_id, label, body = sections[0]
        panels.append(
            '<div class="panel">'
            f"<h3>{label}</h3>"
            f"{body}"
            "</div>"
        )
    else:
        panels.append(build_tabbed_panel(sections))
    return "".join(panels)


def build_post_cards(posts: list[dict], root: str) -> str:
    cards = []
    for idx, post in enumerate(posts):
        delay = min(idx * 0.05, 0.3)
        title = html.escape(post["title"])
        summary = html.escape(post["summary"])
        url = f"{root}/posts/{post['slug']}.html"
        word_count = post.get("words", 0)
        category_links = " ".join(
            f'<a class="chip" href="{root}/categories/{slugify(cat)}.html">{html.escape(cat)}</a>'
            for cat in post["categories"]
        )
        cards.append(
            f'<article class="post-card" style="animation-delay: {delay:.2f}s">'
            '<div class="post-meta"><div class="post-meta-left">'
            f'<span class="post-date">{post["date"]}</span>'
            f'<span class="post-words">{word_count} words</span>'
            "</div>"
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
    args: object,
    analytics_html: str,
    about_html: str,
    widget_html: str,
    theme_toggle: str,
    theme_default: str,
) -> int:
    def page_url(page: int) -> str:
        if page == 1:
            return "index.html"
        return f"page-{page}.html"

    def build_pagination(page: int, total_pages: int) -> str:
        if total_pages <= 1:
            return ""
        items = []
        prev_url = page_url(page - 1) if page > 1 else ""
        next_url = page_url(page + 1) if page < total_pages else ""
        if prev_url:
            items.append(f'<a class="page-link" href="./{prev_url}">Previous</a>')
        else:
            items.append('<span class="page-link is-disabled">Previous</span>')
        numbers = []
        for num in range(1, total_pages + 1):
            if num == page:
                numbers.append(f'<span class="page-number is-active">{num}</span>')
            else:
                numbers.append(f'<a class="page-number" href="./{page_url(num)}">{num}</a>')
        items.append(f'<div class="page-numbers">{"".join(numbers)}</div>')
        if next_url:
            items.append(f'<a class="page-link" href="./{next_url}">Next</a>')
        else:
            items.append('<span class="page-link is-disabled">Next</span>')
        return f'<nav class="pagination">{"".join(items)}</nav>'

    root = "."
    sidebar = build_sidebar(category_map, root, about_html, widget_html=widget_html)
    site_name = html.escape(args.site_name)
    site_description = html.escape(args.site_description)
    per_page = max(1, int(getattr(args, "posts_per_page", 8)))
    total_pages = max(1, math.ceil(len(posts) / per_page))

    for page in range(1, total_pages + 1):
        start = (page - 1) * per_page
        page_posts = posts[start : start + per_page]
        content = (
            '<div class="section-head">'
            "<h2>Latest posts</h2>"
            "<p>Fresh notes generated from your Markdown folder.</p>"
            "</div>"
            f'<div class="post-grid">{build_post_cards(page_posts, root)}</div>'
            f"{build_pagination(page, total_pages)}"
        )
        page_title = f"{args.site_name} | Home"
        if page > 1:
            page_title = f"{args.site_name} | Page {page}"
        html_doc = render_template(
            base_template,
            title=html.escape(page_title),
            root=root,
            content=content,
            sidebar=sidebar,
            site_name=site_name,
            site_description=site_description,
            year=str(dt.datetime.now().year),
            extra_head="",
            theme_toggle=theme_toggle,
            theme_default=theme_default,
            analytics=analytics_html,
        )
        filename = "index.html" if page == 1 else page_url(page)
        write_text(output_dir / filename, html_doc)

    return total_pages


def build_posts(
    base_template: str,
    output_dir: Path,
    posts: list[dict],
    category_map: dict,
    args: object,
    analytics_html: str,
    about_html: str,
    widget_html: str,
    theme_toggle: str,
    theme_default: str,
    only_slugs=None,
    workers: int = 1,
) -> None:
    root = ".."
    site_name = html.escape(args.site_name)
    site_description = html.escape(args.site_description)
    archive_map: dict[str, list[dict]] = {}
    for post in posts:
        for label in post.get("archives", []):
            archive_map.setdefault(label, []).append(post)
    if only_slugs is None:
        posts_to_render = posts
    else:
        posts_to_render = [post for post in posts if post["slug"] in only_slugs]

    def render_post(post: dict) -> None:
        sidebar = build_post_sidebar(
            category_map,
            root,
            about_html,
            post.get("toc", ""),
            post,
            archive_map,
            widget_html,
        )
        title = html.escape(post["title"])
        word_count = post.get("words", 0)
        updated_value = post.get("updated", "")
        show_updated = parse_bool(getattr(args, "show_updated", True))
        updated_html = (
            f'<span class="post-updated">Updated {updated_value}</span>' if show_updated and updated_value else ""
        )
        stale_notice = (getattr(args, "stale_notice", "") or "").strip()
        stale_days = max(0, int(getattr(args, "stale_days", 0) or 0))
        stale_html = ""
        if stale_notice and stale_days > 0:
            updated_dt = post.get("updated_dt")
            if updated_dt and dt.datetime.now() - updated_dt > dt.timedelta(days=stale_days):
                stale_html = f'<div class="stale-warning">{html.escape(stale_notice)}</div>'
        category_links = " ".join(
            f'<a class="chip" href="{root}/categories/{slugify(cat)}.html">{html.escape(cat)}</a>'
            for cat in post["categories"]
        )
        content = (
            '<article class="post">'
            '<div class="post-meta"><div class="post-meta-left">'
            f'<span class="post-date">{post["date"]}</span>'
            f"{updated_html}"
            f'<span class="post-words">{word_count} words</span>'
            "</div>"
            f'<div class="post-tags">{category_links}</div></div>'
            f'<h1 class="post-title">{title}</h1>'
            f"{stale_html}"
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
            extra_head=f'<script src="{root}/js/sidebar-tabs.js" defer></script>',
            theme_toggle=theme_toggle,
            theme_default=theme_default,
            analytics=analytics_html,
        )
        write_text(output_dir / "posts" / f"{post['slug']}.html", html_doc)

    workers = max(1, int(workers or 1))
    if workers <= 1 or len(posts_to_render) <= 1:
        for post in posts_to_render:
            render_post(post)
    else:
        max_workers = min(workers, len(posts_to_render))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            list(executor.map(render_post, posts_to_render))


def build_categories(
    base_template: str,
    output_dir: Path,
    category_map: dict,
    args: object,
    analytics_html: str,
    about_html: str,
    widget_html: str,
    theme_toggle: str,
    theme_default: str,
) -> None:
    root = ".."
    sidebar = build_sidebar(category_map, root, about_html, widget_html=widget_html)
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
            theme_toggle=theme_toggle,
            theme_default=theme_default,
            analytics=analytics_html,
        )
        write_text(output_dir / "categories" / f"{slugify(category)}.html", html_doc)


def build_search(
    base_template: str,
    output_dir: Path,
    posts: list[dict],
    category_map: dict,
    args: object,
    analytics_html: str,
    about_html: str,
    widget_html: str,
    theme_toggle: str,
    theme_default: str,
) -> None:
    root = "."
    sidebar = build_sidebar(category_map, root, about_html, widget_html=widget_html)
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
        theme_toggle=theme_toggle,
        theme_default=theme_default,
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
    args: object,
    analytics_html: str,
    about_html: str,
    widget_html: str,
    theme_toggle: str,
    theme_default: str,
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
    sidebar = build_sidebar(category_map, ".", about_html, toc_html, widget_html)
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
        theme_toggle=theme_toggle,
        theme_default=theme_default,
        analytics=analytics_html,
    )
    write_text(output_dir / "about.html", html_doc)


def build_archive(
    base_template: str,
    output_dir: Path,
    posts: list[dict],
    category_map: dict,
    args: object,
    analytics_html: str,
    about_html: str,
    widget_html: str,
    theme_toggle: str,
    theme_default: str,
) -> None:
    root = "."
    sidebar = build_sidebar(category_map, root, about_html, widget_html=widget_html)
    archive_groups: dict[str, list[dict]] = {}
    date_groups: dict[str, list[dict]] = {}
    year_counts: dict[int, int] = {}
    for post in posts:
        year_counts[post["date_dt"].year] = year_counts.get(post["date_dt"].year, 0) + 1
        labels = post.get("archives") or []
        for label in labels:
            archive_groups.setdefault(label, []).append(post)
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

    archive_sections: list[str] = []
    for label, items in sorted(
        archive_groups.items(),
        key=lambda x: max((p["date_dt"] for p in x[1]), default=dt.datetime.min),
        reverse=True,
    ):
        items.sort(key=lambda p: p["date_dt"], reverse=True)
        archive_sections.append(render_group(label, items))

    if not archive_sections:
        archive_sections.append('<p class="archive-empty">No archive groups yet.</p>')

    time_sections: list[str] = []
    for key, items in sorted(date_groups.items(), key=lambda x: x[0], reverse=True):
        items.sort(key=lambda p: p["date_dt"], reverse=True)
        time_sections.append(render_group(key, items))

    year_rows = []
    for year, count in sorted(year_counts.items(), key=lambda x: x[0], reverse=True):
        year_rows.append(
            f'<li><span class="archive-year">{year}</span>'
            f'<span class="archive-count">{count}</span></li>'
        )
    total_words = sum(post.get("words", 0) for post in posts)
    stats_html = (
        '<div class="archive-stats">'
        f'<div class="archive-total">Total {len(posts)} posts</div>'
        f'<div class="archive-total">Total {total_words} words</div>'
        f'<ul class="archive-year-list">{"".join(year_rows)}</ul>'
        "</div>"
        if posts
        else ""
    )

    controls = (
        '<div class="archive-controls">'
        '<button class="archive-toggle is-active" type="button" data-view="archive">'
        "By archive</button>"
        '<button class="archive-toggle" type="button" data-view="time">By date</button>'
        "</div>"
    )
    views = (
        '<div class="archive-views">'
        f'<section class="archive-view archive-view--archive is-active" data-view="archive">'
        f'{"".join(archive_sections)}'
        "</section>"
        f'<section class="archive-view archive-view--time" data-view="time">'
        f'{"".join(time_sections)}'
        "</section>"
        "</div>"
    )
    content = (
        '<div class="section-head">'
        "<h2>Archive</h2>"
        "<p>All posts by date.</p>"
        "</div>"
        f"{stats_html}"
        f"{controls}"
        f"{views}"
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
        extra_head=f'<script src="{root}/js/archive.js" defer></script>',
        theme_toggle=theme_toggle,
        theme_default=theme_default,
        analytics=analytics_html,
    )
    write_text(output_dir / "archive.html", html_doc)


def build_rss(
    output_dir: Path, posts: list[dict], site_url: str, args: object, feed_limit: int
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
    output_dir: Path, posts: list[dict], site_url: str, args: object, feed_limit: int
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


def build_sitemap(
    output_dir: Path, posts: list[dict], category_map: dict, site_url: str, total_pages: int
) -> None:
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
    if total_pages > 1:
        for page in range(2, total_pages + 1):
            urls.append((join_url(site_url, f"page-{page}.html"), None))
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
    args: object,
    analytics_html: str,
    about_html: str,
    widget_html: str,
    theme_toggle: str,
    theme_default: str,
) -> None:
    root = "."
    sidebar = build_sidebar(category_map, root, about_html, widget_html=widget_html)
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
        theme_toggle=theme_toggle,
        theme_default=theme_default,
        analytics=analytics_html,
    )
    write_text(output_dir / "404.html", html_doc)
