"""
CSS Styling Module

Provides inline CSS styling for Canvas wiki pages using premailer.
Canvas LMS strips <style> tags and external CSS, so styles must be
inlined directly on HTML elements (like email HTML).

This module supports:
- Converting CSS stylesheets to inline styles via premailer
- Pre-defined style presets for common Canvas page layouts
- Custom CSS strings or files
- Callout boxes and styled containers
"""

import logging
from typing import Dict, Optional, List

from premailer import Premailer

logger = logging.getLogger("canvas_mcp.styling")


# Pre-defined CSS style presets for Canvas pages
STYLE_PRESETS: Dict[str, str] = {
    "default": """
        h1 { color: #2d3b45; font-size: 2em; margin-bottom: 0.5em; border-bottom: 2px solid #c7cdd1; padding-bottom: 0.3em; }
        h2 { color: #2d3b45; font-size: 1.5em; margin-top: 1em; margin-bottom: 0.5em; }
        h3 { color: #2d3b45; font-size: 1.25em; margin-top: 1em; margin-bottom: 0.5em; }
        p { line-height: 1.6; margin-bottom: 1em; }
        ul, ol { margin-left: 1.5em; margin-bottom: 1em; }
        li { margin-bottom: 0.5em; }
        a { color: #0374b5; text-decoration: none; }
        code { background-color: #f5f5f5; padding: 0.2em 0.4em; border-radius: 3px; font-family: monospace; }
        pre { background-color: #f5f5f5; padding: 1em; border-radius: 5px; overflow-x: auto; margin-bottom: 1em; }
        pre code { background-color: transparent; padding: 0; }
        blockquote { border-left: 4px solid #c7cdd1; padding-left: 1em; margin-left: 0; color: #666; font-style: italic; }
        table { border-collapse: collapse; width: 100%; margin-bottom: 1em; }
        th { background-color: #f5f5f5; border: 1px solid #c7cdd1; padding: 0.5em; text-align: left; }
        td { border: 1px solid #c7cdd1; padding: 0.5em; }
        hr { border: none; border-top: 1px solid #c7cdd1; margin: 2em 0; }
        img { max-width: 100%; height: auto; }
    """,

    "minimal": """
        h1 { font-size: 2em; margin-bottom: 0.5em; }
        h2 { font-size: 1.5em; margin-top: 1em; }
        h3 { font-size: 1.25em; margin-top: 1em; }
        p { line-height: 1.5; }
        code { font-family: monospace; }
        pre { font-family: monospace; padding: 1em; background: #f5f5f5; }
    """,

    "academic": """
        h1 { color: #1a1a1a; font-size: 1.8em; font-weight: bold; margin-bottom: 0.5em; border-bottom: 1px solid #333; }
        h2 { color: #1a1a1a; font-size: 1.4em; font-weight: bold; margin-top: 1.5em; margin-bottom: 0.5em; }
        h3 { color: #1a1a1a; font-size: 1.2em; font-weight: bold; margin-top: 1em; }
        p { line-height: 1.8; text-align: justify; margin-bottom: 1em; }
        ul, ol { margin-left: 2em; margin-bottom: 1em; }
        li { margin-bottom: 0.3em; }
        a { color: #0066cc; }
        blockquote { margin-left: 2em; font-style: italic; color: #444; }
        table { border-collapse: collapse; width: 100%; margin: 1em 0; }
        th { border: 1px solid #000; padding: 0.5em; background-color: #e8e8e8; font-weight: bold; }
        td { border: 1px solid #000; padding: 0.5em; }
    """,

    "colorful": """
        h1 { color: #1e3a5f; font-size: 2em; background-color: #e8f4f8; padding: 0.5em; border-radius: 5px; }
        h2 { color: #2e5a7e; font-size: 1.5em; border-left: 4px solid #4a90d9; padding-left: 0.5em; }
        h3 { color: #3e6a8e; font-size: 1.25em; }
        p { line-height: 1.6; }
        a { color: #4a90d9; text-decoration: underline; }
        code { background-color: #fff3cd; padding: 0.2em 0.4em; border-radius: 3px; color: #856404; }
        pre { background-color: #1e3a5f; color: #f8f9fa; padding: 1em; border-radius: 5px; }
        pre code { background-color: transparent; color: inherit; }
        blockquote { background-color: #e8f4f8; border-left: 4px solid #4a90d9; padding: 1em; margin: 1em 0; }
        table { border-collapse: collapse; width: 100%; }
        th { background-color: #4a90d9; color: white; padding: 0.75em; border: 1px solid #2e5a7e; }
        td { border: 1px solid #c7cdd1; padding: 0.5em; }
    """,

    "dark": """
        body { background-color: #1e1e1e; color: #d4d4d4; }
        h1 { color: #569cd6; font-size: 2em; border-bottom: 2px solid #569cd6; padding-bottom: 0.3em; }
        h2 { color: #4ec9b0; font-size: 1.5em; margin-top: 1em; }
        h3 { color: #9cdcfe; font-size: 1.25em; }
        p { line-height: 1.6; color: #d4d4d4; }
        a { color: #569cd6; }
        code { background-color: #2d2d2d; padding: 0.2em 0.4em; border-radius: 3px; color: #ce9178; }
        pre { background-color: #2d2d2d; padding: 1em; border-radius: 5px; }
        pre code { color: #d4d4d4; }
        blockquote { border-left: 4px solid #569cd6; padding-left: 1em; color: #9cdcfe; }
        table { border-collapse: collapse; width: 100%; }
        th { background-color: #2d2d2d; border: 1px solid #404040; padding: 0.5em; color: #569cd6; }
        td { border: 1px solid #404040; padding: 0.5em; }
    """,
}


def inline_styles(
    html: str,
    css: Optional[str] = None,
    preset: Optional[str] = "default",
    base_url: Optional[str] = None,
    preserve_style_tags: bool = False,
    strip_important: bool = True,
) -> str:
    """
    Apply inline CSS styles to HTML content using premailer.

    Canvas LMS strips <style> tags and external stylesheets, so all styles
    must be applied inline on individual elements (similar to email HTML).

    Args:
        html: HTML content to style
        css: Custom CSS string to apply. Can include full stylesheet rules.
        preset: Style preset name ('default', 'minimal', 'academic', 'colorful', 'dark').
                Set to None to skip preset styles.
        base_url: Base URL for resolving relative URLs in the HTML
        preserve_style_tags: If True, keep <style> tags (for debugging)
        strip_important: If True, remove !important declarations

    Returns:
        HTML with inline styles applied

    Examples:
        >>> html = '<h1>Title</h1><p>Content</p>'
        >>> styled = inline_styles(html)
        >>> 'style=' in styled
        True

        >>> custom_css = 'h1 { color: red; } .highlight { background: yellow; }'
        >>> styled = inline_styles(html, css=custom_css, preset=None)
    """
    if not html:
        return html

    # Build combined CSS
    combined_css = ""

    # Add preset styles
    if preset and preset in STYLE_PRESETS:
        combined_css += STYLE_PRESETS[preset]

    # Add custom CSS
    if css:
        combined_css += "\n" + css

    if not combined_css.strip():
        return html

    # Wrap HTML with style tag for premailer
    styled_html = f"<style>{combined_css}</style>\n{html}"

    try:
        premailer = Premailer(
            styled_html,
            base_url=base_url,
            preserve_internal_links=True,
            include_star_selectors=True,
            keep_style_tags=preserve_style_tags,
            strip_important=strip_important,
            cssutils_logging_level=logging.CRITICAL,  # Suppress cssutils warnings
        )
        result = premailer.transform()

        logger.debug(f"Applied inline styles using preset '{preset}'")
        return result

    except Exception as e:
        logger.warning(f"Error inlining styles with premailer: {e}. Returning original HTML.")
        return html


def inline_styles_from_file(
    html: str,
    css_file_path: str,
    preset: Optional[str] = None,
) -> str:
    """
    Apply inline CSS styles from a CSS file.

    Args:
        html: HTML content to style
        css_file_path: Path to CSS file
        preset: Optional preset to combine with file styles

    Returns:
        HTML with inline styles applied
    """
    try:
        with open(css_file_path, 'r', encoding='utf-8') as f:
            css = f.read()
        return inline_styles(html, css=css, preset=preset)
    except IOError as e:
        logger.error(f"Error reading CSS file {css_file_path}: {e}")
        return html


def create_styled_container(
    content: str,
    container_style: str = "max-width: 800px; margin: 0 auto; padding: 20px;",
    wrapper_tag: str = "div"
) -> str:
    """
    Wrap content in a styled container.

    Args:
        content: HTML content to wrap
        container_style: CSS styles for the container
        wrapper_tag: HTML tag to use for wrapper (default: div)

    Returns:
        Content wrapped in styled container
    """
    return f'<{wrapper_tag} style="{container_style}">{content}</{wrapper_tag}>'


def add_callout_box(
    content: str,
    style: str = "info",
    title: Optional[str] = None
) -> str:
    """
    Create a styled callout/alert box for Canvas pages.

    Args:
        content: Content for the callout
        style: Callout style ('info', 'warning', 'success', 'danger', 'note')
        title: Optional title for the callout

    Returns:
        HTML for styled callout box

    Example:
        >>> callout = add_callout_box("Important information!", style="warning", title="Warning")
    """
    colors = {
        "info": {"bg": "#d1ecf1", "border": "#0c5460", "text": "#0c5460", "icon": "info"},
        "warning": {"bg": "#fff3cd", "border": "#856404", "text": "#856404", "icon": "warning"},
        "success": {"bg": "#d4edda", "border": "#155724", "text": "#155724", "icon": "check"},
        "danger": {"bg": "#f8d7da", "border": "#721c24", "text": "#721c24", "icon": "error"},
        "note": {"bg": "#e7e9eb", "border": "#6c757d", "text": "#495057", "icon": "note"},
    }

    c = colors.get(style, colors["info"])

    box_style = (
        f"background-color: {c['bg']}; "
        f"border: 1px solid {c['border']}; "
        f"border-left: 4px solid {c['border']}; "
        f"color: {c['text']}; "
        "padding: 1em; "
        "margin: 1em 0; "
        "border-radius: 4px;"
    )

    title_html = ""
    if title:
        title_style = f"font-weight: bold; margin-bottom: 0.5em; color: {c['border']};"
        title_html = f'<div style="{title_style}">{title}</div>'

    return f'<div style="{box_style}">{title_html}<div>{content}</div></div>'


def add_styled_table(
    headers: List[str],
    rows: List[List[str]],
    style: str = "default"
) -> str:
    """
    Create a styled HTML table.

    Args:
        headers: List of header cell contents
        rows: List of rows, each row is a list of cell contents
        style: Table style ('default', 'striped', 'bordered')

    Returns:
        HTML table with inline styles
    """
    styles = {
        "default": {
            "table": "border-collapse: collapse; width: 100%; margin: 1em 0;",
            "th": "background-color: #f5f5f5; border: 1px solid #c7cdd1; padding: 0.75em; text-align: left; font-weight: bold;",
            "td": "border: 1px solid #c7cdd1; padding: 0.75em;",
            "tr_even": "",
        },
        "striped": {
            "table": "border-collapse: collapse; width: 100%; margin: 1em 0;",
            "th": "background-color: #4a90d9; color: white; border: 1px solid #2e5a7e; padding: 0.75em; text-align: left;",
            "td": "border: 1px solid #c7cdd1; padding: 0.75em;",
            "tr_even": "background-color: #f8f9fa;",
        },
        "bordered": {
            "table": "border-collapse: collapse; width: 100%; margin: 1em 0; border: 2px solid #333;",
            "th": "background-color: #333; color: white; border: 1px solid #333; padding: 0.75em; text-align: left;",
            "td": "border: 1px solid #333; padding: 0.75em;",
            "tr_even": "",
        },
    }

    s = styles.get(style, styles["default"])

    html = f'<table style="{s["table"]}">\n<thead>\n<tr>'
    for header in headers:
        html += f'<th style="{s["th"]}">{header}</th>'
    html += '</tr>\n</thead>\n<tbody>\n'

    for i, row in enumerate(rows):
        tr_style = s["tr_even"] if i % 2 == 1 and s["tr_even"] else ""
        html += f'<tr style="{tr_style}">' if tr_style else '<tr>'
        for cell in row:
            html += f'<td style="{s["td"]}">{cell}</td>'
        html += '</tr>\n'

    html += '</tbody>\n</table>'
    return html


def get_preset_names() -> List[str]:
    """Return list of available style preset names."""
    return list(STYLE_PRESETS.keys())


def get_preset_css(name: str) -> str:
    """
    Get the CSS for a style preset.

    Args:
        name: Preset name

    Returns:
        CSS string or empty string if not found
    """
    return STYLE_PRESETS.get(name, "")
