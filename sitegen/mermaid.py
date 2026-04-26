from markdown.extensions import Extension
from markdown.preprocessors import Preprocessor
import re

class MermaidPreprocessor(Preprocessor):
    def run(self, lines):
        new_lines = []
        in_mermaid = False
        mermaid_content = []
        
        for line in lines:
            if line.strip().startswith("```mermaid"):
                in_mermaid = True
                mermaid_content = []
                continue
            
            if in_mermaid:
                if line.strip() == "```":
                    in_mermaid = False
                    # Use a placeholder or just raw HTML
                    # To prevent markdown from wrapping this in <p>, we can use the 'html' block logic
                    # or just return it as is if it's outside of other blocks.
                    content = "\n".join(mermaid_content)
                    new_lines.append('<pre class="mermaid">')
                    new_lines.append(content)
                    new_lines.append('</pre>')
                    continue
                mermaid_content.append(line)
                continue
            
            new_lines.append(line)
        return new_lines

class MermaidExtension(Extension):
    def extendMarkdown(self, md):
        md.preprocessors.register(MermaidPreprocessor(md), "mermaid", 100)

def makeExtension(**kwargs):
    return MermaidExtension(**kwargs)
