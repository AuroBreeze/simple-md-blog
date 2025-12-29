# Simple MD Blog

一个轻量的 Markdown 静态博客生成器，适合部署到 GitHub Pages。支持分类、搜索、目录、RSS/Atom、站点地图、自定义域名与统计脚本。

## 特性

- Markdown -> HTML（代码块、表格、图片）
- 分类页 + 全站搜索
- 文章目录（TOC）自动生成
- 归档页（按月归档）
- RSS/Atom + sitemap + 404 + .nojekyll
- front matter 支持时间与草稿
- 侧栏 About 内容可配置

## 目录结构

```
posts/        Markdown 文章
pages/        独立页面（如 about.md）
static/       CSS、JS、图片（构建时复制到输出根目录）
templates/    HTML 模板
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

每篇文章是 `posts/` 下的 `.md` 文件。推荐使用 front matter：

```text
---
title: 你好，Markdown
date: 2025-01-05
time: 09:30
category: 随笔
archive: 课程笔记
summary: 这是一段摘要。
draft: false
---
```

说明：
- `time` 为可选，格式 `HH:MM` 或 `HH:MM:SS`
- 未填写 `time` 会使用当前时间
- `draft: true` 会跳过生成
- `archive` 可用于归档分组，相同字段会归到一起
- `archive` 支持多个值：`archive: 课程笔记, OS` 或 `archive: [课程笔记, OS]`
- 若无 `title`，会使用正文第一行 H1

## 图片

图片放到 `static/images/`，在 Markdown 中引用：

```text
![Alt](images/your-image.png)
```

## 配置文件

默认读取 `site.json`，CLI 参数会覆盖配置文件。

```json
{
  "site_name": "AuroBreeze Blog",
  "site_description": "A tiny, fast Markdown blog for GitHub Pages.",
  "custom_domain": "blog.aurobreeze.top",
  "site_url": "https://blog.aurobreeze.top",
  "clean": true,
  "feed_limit": 20,
  "posts_per_page": 8,
  "toc_depth": "2-4",
  "enable_rss": true,
  "enable_atom": true,
  "enable_sitemap": true,
  "enable_404": true,
  "write_nojekyll": true,
  "analytics_file": "analytics.html",
  "about_text": "A tiny, fast Markdown blog for GitHub Pages."
}
```

常用命令：

```powershell
python build.py --site-name "My Blog" --site-description "Notes from the keyboard."
python build.py --output docs
python build.py --no-clean
```

## 侧栏 About 配置

优先级：`about_html` > `about_file` > `about_text`。

- `about_text`: 纯文本（自动转义并包一层 `<p>`）
- `about_html`: 直接插入 HTML
- `about_file`: 指向一个文件（支持 `.html`/`.md`/纯文本）

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

## 统计脚本

将脚本放到 `analytics.html`，并在 `site.json` 配置：

```json
{
  "analytics_file": "analytics.html"
}
```

也可以用 `analytics_html` 直接写内联脚本内容。
