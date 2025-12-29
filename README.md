# 简易 MD 博客

一个将 Markdown 生成 HTML 的极简静态博客生成器，适合用于 GitHub Pages。

## 目录结构

- posts/        Markdown 文章
- static/       CSS、JS、图片（会复制到输出根目录）
- templates/    HTML 模板
- dist/         生成站点输出

## 快速开始

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python build.py
```

用浏览器打开 `dist/index.html`。

## 自定义

你可以通过命令行覆盖站点标题和描述：

```powershell
python build.py --site-name "My Blog" --site-description "Notes from the keyboard."
```

## 写作

每篇文章是 `posts/` 下的一个 `.md` 文件。可选的 front matter 示例：

```text
---
title: 你好，Markdown
date: 2025-01-05
category: 随笔
summary: 布局与功能的快速预览。
---
```

如果省略 `title`，会自动取第一行 H1 作为标题，并从正文中移除。

## 图片

`static/` 下的内容会被复制到输出根目录。图片引用示例：

```text
![Alt](images/your-image.png)
```

## GitHub Actions 自动部署

仓库每次推送后自动构建并发布到 GitHub Pages：

1. 确保分支名是 `main` 或 `master`（如不同，请修改 `.github/workflows/pages.yml`）。
2. 在 GitHub Pages 设置中将 Source 选择为 `GitHub Actions`。
3. 推送后等待 Actions 运行完成即可访问。

## 站点配置文件

默认会读取 `site.json`，用于统一配置站点信息和自定义域名。CLI 参数会覆盖配置文件。

```json
{
  "site_name": "Simple MD Blog",
  "site_description": "A tiny, fast Markdown blog for GitHub Pages.",
  "custom_domain": "blog.aurobreeze.top",
  "site_url": "https://blog.aurobreeze.top",
  "clean": true,
  "feed_limit": 20,
  "toc_depth": "2-4",
  "enable_rss": true,
  "enable_atom": true,
  "enable_sitemap": true,
  "enable_404": true,
  "write_nojekyll": true,
  "analytics_file": "analytics.html"
}
```

构建时会在输出目录自动生成 `CNAME`，用于 GitHub Pages 自定义域名。

## GitHub Pages

如果你想用 `docs/` 作为 Pages 的发布目录：

```powershell
python build.py --output docs
```

然后在 GitHub Pages 设置中选择 `docs/`。

## 进阶功能

- 自动清理输出：默认在构建前清空输出目录，避免旧页面残留。可用 `--no-clean` 关闭。
- 草稿：在 front matter 中加入 `draft: true`，该文章不会生成。
- RSS/Atom：生成 `rss.xml` 和 `atom.xml`，需要在 `site.json` 填写 `site_url`，可用 `enable_rss`/`enable_atom` 控制。
- Sitemap：生成 `sitemap.xml`，同样依赖 `site_url`，可用 `enable_sitemap` 控制。
- 404 页面：自动生成 `404.html`，可用 `enable_404` 控制。
- `.nojekyll`：输出根目录会写入 `.nojekyll`，可用 `write_nojekyll` 控制。
- 统计脚本：配置 `analytics_file` 或 `analytics_html`，会注入到页面底部。
