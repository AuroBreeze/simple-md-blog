from __future__ import annotations

import html
import re
from pathlib import Path

import xml.etree.ElementTree as etree
import markdown
from markdown.extensions import Extension
from markdown.inlinepatterns import InlineProcessor

from pygments import highlight
from pygments.lexers import get_lexer_by_name
from pygments.formatters import HtmlFormatter

RE_CODE_LINK = r"\[(?P<text>[^\]]+)\]\(code:(?P<path>[^#]+)#L(?P<line>\d+)\)"

class CodeLinkerProcessor(InlineProcessor):
    def __init__(self, pattern, md, base_path: Path, project_root: Path):
        super().__init__(pattern, md)
        self.base_path = base_path
        self.project_root = project_root

    def handleMatch(self, m, data):
        file_path_str = m.group("path").strip()
        line_num = int(m.group("line"))
        link_text = m.group("text")
        
        if file_path_str.startswith('/'):
            # Root-relative path
            file_path = (self.project_root / file_path_str.lstrip('/')).resolve()
        else:
            # Page-relative path
            file_path = (self.base_path / file_path_str).resolve()

        if not file_path.exists():
            return f'<a href="#" class="code-link-error">File not found: {html.escape(file_path_str)}</a>', m.start(0), m.end(0)

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                code_selection = f.read()
        except Exception as e:
            return f'<a href="#" class="code-link-error">Error reading file: {html.escape(str(e))}</a>', m.start(0), m.end(0)
        
        lang = self.get_lang(file_path)
        
        try:
            lexer = get_lexer_by_name(lang, stripall=True)
            formatter = HtmlFormatter(
                linenos=True,
                cssclass="codehilite",
                hl_lines=[line_num]
            )
            highlighted_code = highlight(code_selection, lexer, formatter)
        except Exception:
            highlighted_code = f'<pre><code>{html.escape(code_selection)}</code></pre>'


        el = etree.Element("a")
        el.set("href", "#")
        el.set("class", "code-link")
        el.set("data-code", highlighted_code)
        el.set("data-lang", lang)
        el.set("data-line", str(line_num))
        # Use the captured link text for the link
        el.text = link_text
        
        return el, m.start(0), m.end(0)

    def get_lang(self, file_path: Path) -> str:
        ext = file_path.suffix.lstrip(".")
        if ext == "py":
            return "python"
        if ext in ("c", "h"):
            return "c"
        if ext in ("cpp", "hpp", "cxx"):
            return "cpp"
        if ext == "js":
            return "javascript"
        if ext == "ts":
            return "typescript"
        if ext == "java":
            return "java"
        if ext == "rs":
            return "rust"
        if ext == "go":
            return "go"
        if ext == "sh":
            return "bash"
        if ext == "md":
            return "markdown"
        return "text"


class CodeLinkerExtension(Extension):
    def __init__(self, base_path: Path, project_root: Path, **kwargs):
        super().__init__(**kwargs)
        self.base_path = base_path
        self.project_root = project_root

    def extendMarkdown(self, md):
        md.inlinePatterns.register(
            CodeLinkerProcessor(RE_CODE_LINK, md, self.base_path, self.project_root), 
            "code_linker", 
            175
        )

