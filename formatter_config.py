"""Per-target formatter pipeline configurations.

Each target gets a pipeline tuned for its display medium. Pipelines are
built lazily and cached. To customize, edit the build functions below —
or override at runtime via `get_pipeline("web").add(MyFormatter())`.
"""

from __future__ import annotations

from threading import Lock

from formatter import FormatterPipeline, get_formatter

_LOCK = Lock()
_CACHE: dict[str, FormatterPipeline] = {}


def _build_cli() -> FormatterPipeline:
    """CLI / TTY: ANSI-colored markdown, no HTML."""
    return (
        FormatterPipeline()
        .add(get_formatter("normalize"))
        .add(get_formatter("ansi_markdown", width=80, color=True))
        .add(get_formatter("emoticon"))  # run AFTER markdown so it doesn't touch URLs like https://
    )


def _build_cli_plain() -> FormatterPipeline:
    """CLI plain (no color support, e.g. piped output)."""
    return (
        FormatterPipeline()
        .add(get_formatter("normalize"))
        .add(get_formatter("ansi_markdown", color=False))
    )


def _build_web() -> FormatterPipeline:
    """Web GUI: full HTML with code highlighting + sanitization."""
    return (
        FormatterPipeline()
        .add(get_formatter("normalize"))
        .add(get_formatter("markdown_html", highlight=True, style="monokai"))
        .add(get_formatter("linkify"))
        .add(get_formatter("sanitize_html"))
    )


def _build_hud() -> FormatterPipeline:
    """HUD overlay: same as web but with a tighter sanitization."""
    return (
        FormatterPipeline()
        .add(get_formatter("normalize"))
        .add(get_formatter("markdown_html", highlight=True, style="monokai"))
        .add(get_formatter("sanitize_html"))
    )


def _build_desktop() -> FormatterPipeline:
    """Legacy desktop GUI (customtkinter): plain text — CTk can't render HTML."""
    return (
        FormatterPipeline()
        .add(get_formatter("normalize"))
        .add(get_formatter("tts_clean", replace_code="\n[code block]\n"))
    )


def _build_tts() -> FormatterPipeline:
    """TTS: strip ALL markdown, expand abbreviations, readable speech."""
    return (
        FormatterPipeline()
        .add(get_formatter("normalize"))
        .add(get_formatter("tts_clean"))
        .add(get_formatter("truncate", max_chars=2000))
    )


_BUILDERS = {
    "cli": _build_cli,
    "cli_plain": _build_cli_plain,
    "web": _build_web,
    "hud": _build_hud,
    "desktop": _build_desktop,
    "tts": _build_tts,
}


def get_pipeline(target: str) -> FormatterPipeline:
    """Get a pipeline for the given target. Cached after first build."""
    with _LOCK:
        if target not in _CACHE:
            if target not in _BUILDERS:
                raise KeyError(f"No pipeline for target '{target}'. Available: {list(_BUILDERS)}")
            _CACHE[target] = _BUILDERS[target]()
        return _CACHE[target]


def format_for(text: str, target: str, **ctx) -> str:
    """Convenience: format text for the given target."""
    ctx.setdefault("target", target)
    return get_pipeline(target).run(text, **ctx)


def reset_cache() -> None:
    """Clear the pipeline cache (useful in tests / hot-reload)."""
    with _LOCK:
        _CACHE.clear()
