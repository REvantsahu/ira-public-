"""IRA Response Formatter — Clean, extensible, pluggable pipeline.

Architecture:
    Formatter (base class)
        └── any subclass with format(text, ctx) -> text

    FormatterPipeline
        └── runs formatters in order, passing shared ctx dict
        └── a failing formatter never breaks the chain

Adding a new formatter:
    1. Subclass Formatter
    2. Set `name` and implement `format(text, ctx)`
    3. Register with @register_formatter("my_formatter")
    4. Add to a pipeline in formatter_config.py

Each formatter receives a `ctx` dict with at least:
    - `target`: "cli" | "web" | "hud" | "desktop" | "tts"
    - `speaking`: bool — whether this output will be TTS-spoken
    - any custom keys formatters want to share downstream
"""

from __future__ import annotations

import re
import html
import threading
from typing import Callable


# ─────────────────────────────────────────────────────────────────
# Registry — auto-register formatters with @register_formatter("name")
# ─────────────────────────────────────────────────────────────────

_REGISTRY: dict[str, type["Formatter"]] = {}


def register_formatter(name: str):
    """Decorator to register a Formatter subclass in the global registry."""
    def wrap(cls: type["Formatter"]) -> type["Formatter"]:
        if name in _REGISTRY:
            raise ValueError(f"Formatter '{name}' already registered")
        cls.name = name
        _REGISTRY[name] = cls
        return cls
    return wrap


def get_formatter(name: str, **opts) -> "Formatter":
    """Instantiate a registered formatter by name with options."""
    if name not in _REGISTRY:
        raise KeyError(f"Formatter '{name}' not registered. Available: {list(_REGISTRY)}")
    return _REGISTRY[name](**opts)


def list_formatters() -> list[str]:
    """List all registered formatter names."""
    return sorted(_REGISTRY)


# ─────────────────────────────────────────────────────────────────
# Base classes
# ─────────────────────────────────────────────────────────────────


class Formatter:
    """Base class for all formatters. Override `format()`."""

    name: str = "base"

    def format(self, text: str, ctx: dict) -> str:
        """Transform text. Return the (possibly modified) text."""
        return text


class FormatterPipeline:
    """Runs text through a chain of formatters in order.

    - `ctx` dict is passed to every formatter (mutable, formatters can communicate)
    - A failing formatter logs the error and is skipped (never breaks the chain)
    - `run(text, **ctx_overrides)` is the main entry point
    """

    def __init__(self, formatters: list[Formatter] | None = None):
        self._formatters: list[Formatter] = list(formatters or [])

    def add(self, formatter: Formatter, position: int | None = None) -> "FormatterPipeline":
        """Append a formatter, or insert at position. Returns self for chaining."""
        if position is None:
            self._formatters.append(formatter)
        else:
            self._formatters.insert(position, formatter)
        return self

    def remove(self, name: str) -> "FormatterPipeline":
        """Remove a formatter by name. Returns self for chaining."""
        self._formatters = [f for f in self._formatters if f.name != name]
        return self

    def clear(self) -> "FormatterPipeline":
        self._formatters.clear()
        return self

    def __len__(self) -> int:
        return len(self._formatters)

    def __iter__(self):
        return iter(self._formatters)

    def run(self, text: str, **ctx_overrides) -> str:
        """Run text through the pipeline. ctx_overrides seed the shared ctx dict."""
        ctx = {"target": "unknown", "speaking": False}
        ctx.update(ctx_overrides)
        for f in self._formatters:
            try:
                text = f.format(text, ctx)
            except Exception as e:
                # Never break the chain — log and continue
                if ctx.get("debug"):
                    print(f"  [FORMATTER] {f.name} failed: {e}")
        return text


# ─────────────────────────────────────────────────────────────────
# Built-in formatters
# ─────────────────────────────────────────────────────────────────


@register_formatter("normalize")
class NormalizeFormatter(Formatter):
    """Normalize whitespace, strip BOM, fix common LLM quirks."""

    def format(self, text: str, ctx: dict) -> str:
        text = text.lstrip("\ufeff")  # BOM
        text = text.replace("\r\n", "\n")
        # Collapse 3+ blank lines to max 2
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()


@register_formatter("emoticon")
class EmoticonFormatter(Formatter):
    """Convert ASCII emoticons to emoji. Optional, off by default in some pipelines.

    Skips matches that are part of URLs (e.g. `https://`, `http://`)
    or other alphanumeric contexts.
    """

    MAP = {
        ":-)": "🙂", ":)": "🙂",
        ":-D": "😄", ":D": "😄",
        ";-(": "😢", ":(": "😞",
        "<3": "❤️",
        "</3": "💔",
        ":P": "😛", ":-P": "😛",
        ";-)": "😉", ";)": "😉",
        ":/": "😕",
        "B-)": "😎",
    }

    def format(self, text: str, ctx: dict) -> str:
        # Don't touch code blocks
        if ctx.get("in_code_block"):
            return text
        # Find URL spans first, protect them from emoticon substitution
        url_re = re.compile(r"https?://\S+")
        protected_spans: list[tuple[int, int]] = [(m.start(), m.end()) for m in url_re.finditer(text)]

        def in_url(pos: int) -> bool:
            for s, e in protected_spans:
                if s <= pos < e:
                    return True
            return False

        # Apply emoticons in reverse so positions don't shift
        for k, v in self.MAP.items():
            new_parts: list[str] = []
            i = 0
            while i <= len(text) - len(k):
                if text[i:i + len(k)] == k and not in_url(i):
                    new_parts.append(text[:i])
                    new_parts.append(v)
                    text = text[i + len(k):]
                    i = 0
                else:
                    i += 1
            if new_parts:
                new_parts.append(text)
                text = "".join(new_parts)
        return text


@register_formatter("markdown_html")
class MarkdownHTMLFormatter(Formatter):
    """Convert markdown to HTML with syntax-highlighted code blocks.

    Uses markdown-it-py (safe by default — no raw HTML).
    """

    def __init__(self, highlight: bool = True, style: str = "monokai"):
        from markdown_it import MarkdownIt
        from pygments.formatters import HtmlFormatter

        self._highlight = highlight
        opts = {}
        if highlight:
            opts["highlight"] = self._pygmentize
        self._md = MarkdownIt("default", opts)
        self._style = style
        self._pyg_css = HtmlFormatter(style=style).get_style_defs(".highlight") if highlight else ""

    def _pygmentize(self, code: str, lang: str, attrs: str = "") -> str:
        from pygments import highlight as pg_highlight
        from pygments.lexers import get_lexer_by_name, guess_lexer, PythonLexer
        from pygments.formatters import HtmlFormatter

        try:
            lexer = get_lexer_by_name(lang, stripall=True)
        except Exception:
            try:
                lexer = guess_lexer(code)
            except Exception:
                lexer = PythonLexer()
        formatter = HtmlFormatter(style=self._style, noclasses=True)
        return pg_highlight(code, lexer, formatter)

    @property
    def pygments_css(self) -> str:
        """CSS to inject for syntax highlighting. Returns '' if highlighting is off."""
        return self._pyg_css

    def format(self, text: str, ctx: dict) -> str:
        return self._md.render(text)


@register_formatter("ansi_markdown")
class ANSIMarkdownFormatter(Formatter):
    """Render markdown as ANSI-colored terminal text. For CLI/TTY.

    Supports: bold, italic, headings, inline code, code blocks, links, lists.
    """

    BOLD = "\033[1m"
    DIM = "\033[2m"
    ITALIC = "\033[3m"
    UNDERLINE = "\033[4m"
    CYAN = "\033[36m"
    MAGENTA = "\033[35m"
    YELLOW = "\033[33m"
    GREEN = "\033[32m"
    BLUE = "\033[34m"
    GRAY = "\033[90m"
    RESET = "\033[0m"

    def __init__(self, width: int = 80, color: bool = True):
        self._width = width
        self._c = color

    def _wrap(self, text: str) -> str:
        return text if self._c else ""

    def format(self, text: str, ctx: dict) -> str:
        if not self._c:
            # Strip markdown syntax, return plain
            return self._strip_markdown(text)

        out = []
        in_code = False
        code_buf: list[str] = []
        code_lang = ""

        def flush_code():
            if not code_buf:
                return ""
            inner = "\n".join(code_buf)
            return f"\n{self.GRAY}┌{'─' * (self._width - 2)}┐{self.RESET}\n"
            + "\n".join(f"{self.GRAY}│{self.RESET} {self.CYAN}{line}{self.RESET}" for line in code_buf)
            + f"\n{self.GRAY}└{'─' * (self._width - 2)}┘{self.RESET}\n"

        for line in text.split("\n"):
            if line.startswith("```"):
                if in_code:
                    out.append(flush_code())
                    code_buf.clear()
                    in_code = False
                else:
                    in_code = True
                    code_lang = line[3:].strip()
                continue
            if in_code:
                code_buf.append(line)
                continue

            # Headings
            if line.startswith("### "):
                out.append(f"{self.MAGENTA}{self.BOLD}  {line[4:]}{self.RESET}")
            elif line.startswith("## "):
                out.append(f"{self.MAGENTA}{self.BOLD}  {line[3:]}{self.RESET}")
            elif line.startswith("# "):
                out.append(f"{self.CYAN}{self.BOLD}  {line[2:]}{self.RESET}")
            # Bullets
            elif re.match(r"^\s*[-*]\s+", line):
                out.append(f"{self.GREEN}  •{self.RESET} {self._inline(line.lstrip()[2:])}")
            # Numbered lists
            elif re.match(r"^\s*\d+\.\s+", line):
                out.append(f"{self.GREEN}  {line.lstrip()}{self.RESET}")
                # recolor the number
                out[-1] = re.sub(r"^(\s*)(\d+)\.", rf"\1{self.BOLD}{self.CYAN}\2{self.RESET}.", out[-1])
            # Blockquote
            elif line.startswith("> "):
                out.append(f"{self.GRAY}  │{self.RESET} {self.DIM}{line[2:]}{self.RESET}")
            else:
                out.append(f"  {self._inline(line)}")

        if in_code and code_buf:
            out.append(flush_code())

        return "\n".join(out)

    def _inline(self, line: str) -> str:
        # Inline code
        line = re.sub(
            r"`([^`]+)`",
            lambda m: f"{self.YELLOW}{m.group(1)}{self.RESET}",
            line,
        )
        # Bold
        line = re.sub(
            r"\*\*([^*]+)\*\*",
            lambda m: f"{self.BOLD}{m.group(1)}{self.RESET}",
            line,
        )
        # Italic
        line = re.sub(
            r"(?<!\*)\*([^*]+)\*(?!\*)",
            lambda m: f"{self.ITALIC}{m.group(1)}{self.RESET}",
            line,
        )
        # Links [text](url)
        line = re.sub(
            r"\[([^\]]+)\]\(([^)]+)\)",
            lambda m: f"{self.UNDERLINE}{self.BLUE}{m.group(1)}{self.RESET}{self.GRAY} ({m.group(2)}){self.RESET}",
            line,
        )
        return line

    def _strip_markdown(self, text: str) -> str:
        text = re.sub(r"^#{1,6}\s+", "", text, flags=re.M)
        text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
        text = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"\1", text)
        text = re.sub(r"`([^`]+)`", r"\1", text)
        text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1 (\2)", text)
        text = re.sub(r"^```.*$", "", text, flags=re.M)
        return text


@register_formatter("linkify")
class LinkifyFormatter(Formatter):
    """Auto-link bare URLs in plain text. Safe — does not touch <a> tags."""

    URL_RE = re.compile(r"(?<![\"'>=])(https?://[^\s<>\"')]+)")

    def format(self, text: str, ctx: dict) -> str:
        target = ctx.get("target")
        if target in ("web", "hud"):
            return self.URL_RE.sub(r'<a href="\1" target="_blank" rel="noopener">\1</a>', text)
        if target == "cli":
            return self.URL_RE.sub(r"\033[4;34m\1\033[0m", text)
        return text


@register_formatter("sanitize_html")
class SanitizeHTMLFormatter(Formatter):
    """Strip dangerous HTML tags. Defensive layer for any user-supplied HTML.

    markdown-it is already safe by default, so this is belt-and-suspenders.
    """

    DANGEROUS = re.compile(
        r"<\s*(script|iframe|object|embed|style|link|meta|form)\b[^>]*>.*?<\s*/\s*\1\s*>",
        re.IGNORECASE | re.DOTALL,
    )
    ON_ATTR = re.compile(r'\s+on\w+\s*=\s*("[^"]*"|\'[^\']*\'|[^\s>]+)', re.IGNORECASE)
    JS_URL = re.compile(r'(href|src|action)\s*=\s*["\']?\s*javascript:', re.IGNORECASE)

    def format(self, text: str, ctx: dict) -> str:
        text = self.DANGEROUS.sub("", text)
        text = self.ON_ATTR.sub("", text)
        text = self.JS_URL.sub(r"\1=", text)
        return text


@register_formatter("tts_clean")
class TTSCleanFormatter(Formatter):
    """Strip markdown/formatting for clean text-to-speech output.

    - Removes code blocks entirely (or replaces with placeholder)
    - Strips markdown syntax
    - Expands common abbreviations
    """

    ABBREV = {
        "e.g.": "for example",
        "i.e.": "that is",
        "etc.": "etcetera",
        "vs.": "versus",
        "Dr.": "Doctor",
        "Mr.": "Mister",
        "Mrs.": "Misses",
        "Ms.": "Miss",
        "AI": "A.I.",
        "API": "A.P.I.",
    }

    def __init__(self, replace_code: str = " (code block omitted) "):
        self._replace_code = replace_code

    def format(self, text: str, ctx: dict) -> str:
        # Remove fenced code blocks
        text = re.sub(r"```[^\n]*\n.*?```", self._replace_code, text, flags=re.DOTALL)
        text = re.sub(r"```[^\n]*```", self._replace_code, text)
        # Inline code → read literally
        text = re.sub(r"`([^`]+)`", r"\1", text)
        # Strip markdown syntax
        text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
        text = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"\1", text)
        text = re.sub(r"_([^_]+)_", r"\1", text)
        text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
        text = re.sub(r"^#{1,6}\s+", "", text, flags=re.M)
        text = re.sub(r"^>\s+", "", text, flags=re.M)
        # Expand abbreviations
        for k, v in self.ABBREV.items():
            text = text.replace(k, v)
        # Collapse whitespace
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()


@register_formatter("truncate")
class TruncateFormatter(Formatter):
    """Cap output length. Useful for status badges, TTS, etc."""

    def __init__(self, max_chars: int = 500, suffix: str = "..."):
        self._max = max_chars
        self._suffix = suffix

    def format(self, text: str, ctx: dict) -> str:
        if len(text) <= self._max:
            return text
        return text[: self._max - len(self._suffix)].rstrip() + self._suffix


@register_formatter("signature")
class SignatureFormatter(Formatter):
    """Append an optional signature line. Off by default — set in pipeline config."""

    def __init__(self, signature: str = "\n\n— IRA"):
        self._sig = signature

    def format(self, text: str, ctx: dict) -> str:
        return text + self._sig
