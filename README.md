# Simple MD Blog

一个轻量的 Markdown 静态博客生成器，适合部署到 GitHub Pages。支持分类、搜索、目录、归档、RSS/Atom、站点地图、自定义域名、统计脚本与数据挂件。

## 特性

- Markdown -> HTML（代码块、表格、图片）
- 分类页 + 全站搜索
- 文章目录（TOC）自动生成
- 归档页（按归档字段/时间切换）
- 首页分页 + 文章字数统计
- 最后更新与过期提示
- RSS/Atom + sitemap + 404 + .nojekyll
- 侧栏 About/目录/分类/归档可切换
- 增量构建 + 多线程加速

## 目录结构

```
posts/        Markdown 文章（支持子目录）
pages/        独立页面（如 about.md）
static/       CSS、JS、图片（构建时复制到输出根目录）
templates/    HTML 模板
site.toml     配置文件（带详细注释）
dist/         生成站点输出
```

## 快速开始

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python build.py
```

打开 `dist/index.html` 查看效果。

## 写作格式

每篇文章是 `posts/` 下的 `.md` 文件（可放子目录，仅用于整理，不会展示文件夹名）。推荐使用 front matter：

```text
---
title: 你好，Markdown
date: 2025-01-05
time: 09:30
updated: 2025-01-06
categories: 随笔
archive: 课程笔记
summary: 这是一段摘要。
draft: false
slug: hello-markdown
---
```

说明：
- `time` 为可选，格式 `HH:MM` 或 `HH:MM:SS`
- `updated` 可选，不填则使用文件最后修改时间
- `draft: true` 会跳过生成
- `archive` 可用于归档分组，相同字段会归到一起
- `archive` 支持多个值：`archive: 课程笔记, OS` 或 `archive: [课程笔记, OS]`
- 若无 `title`，会使用正文第一行 H1
- `slug` 可选，用于固定 URL

## 图片

图片放到 `static/images/`，在 Markdown 中引用：

```text
![Alt](images/your-image.png)
```

## 配置文件

默认读取 `site.toml`（也支持 `.yml/.yaml/.json`），CLI 参数会覆盖配置文件。建议直接编辑 `site.toml`，文件内已包含详细注释。

```toml
site_name = "AuroBreeze Blog"
site_description = "A tiny, fast Markdown blog for GitHub Pages."
custom_domain = "blog.aurobreeze.top"
site_url = "https://blog.aurobreeze.top"

clean = false
incremental = true
lock_file = "build.lock.json"
build_workers = 4

posts_per_page = 8
toc_depth = "2-4"
feed_limit = 20

enable_rss = true
enable_atom = true
enable_sitemap = true
enable_404 = true
write_nojekyll = true

analytics_file = "templates/analytics.html"
widget_file = "templates/widget.html"

show_updated = true
stale_days = 365
stale_notice = "This post may be outdated."
```

## 常用命令

```powershell
python build.py --site-name "My Blog" --site-description "Notes from the keyboard."
python build.py --output docs
python build.py --no-clean
```

## 增量构建 / 全量重建

默认开启增量构建（`incremental = true`），只重建变更的文章与相关页面。

强制全量重建的方式：

```powershell
# 1) 禁用增量构建
python build.py --no-incremental

# 2) 清理输出目录后重建
python build.py --clean

# 3) 删除构建缓存文件后重建
Remove-Item build.lock.json
python build.py
```

## 侧栏 About 配置

优先级：`about_html` > `about_file` > `about_text`。

- `about_text`: 纯文本（自动转义并包一层 `<p>`）
- `about_html`: 直接插入 HTML
- `about_file`: 指向一个文件（支持 `.html`/`.md`/纯文本）

## 统计脚本与数据挂件

将脚本分别放到：
- `templates/analytics.html`
- `templates/widget.html`

并在 `site.toml` 配置：

```toml
analytics_file = "templates/analytics.html"
widget_file = "templates/widget.html"
```

也可以用 `analytics_html` / `widget_html` 直接写内联脚本内容。

## GitHub Pages + Actions

项目已内置 `.github/workflows/pages.yml`，推送后自动构建并发布。

1. 分支名为 `main` 或 `master`
2. 仓库 Settings -> Pages -> Source 选择 `GitHub Actions`
3. 等待 Actions 结束即可访问

## 自定义域名

1. DNS 配置 CNAME：`blog` -> `aurobreeze.github.io`
2. 仓库 Settings -> Pages -> Custom domain 填 `blog.aurobreeze.top`
3. 勾选 `Enforce HTTPS`

构建会自动生成 `CNAME`。
