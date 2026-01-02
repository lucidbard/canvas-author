"""
Pandoc Integration

Provides markdown <-> HTML conversion using pandoc with optional inline CSS styling.
Canvas LMS strips <style> tags, so styles are inlined directly on elements.
"""

import subprocess
import logging
import shutil
from typing import Optional, Dict

logger = logging.getLogger("canvas_author.pandoc")


def _check_pandoc() -> bool:
    """Check if pandoc is available."""
    return shutil.which("pandoc") is not None


def markdown_to_html(
    markdown: str,
    standalone: bool = False,
    apply_styles: bool = False,
    style_preset: str = "default",
    custom_css: Optional[str] = None
) -> str:
    """
    Convert markdown to HTML using pandoc with optional inline CSS styling.

    Canvas LMS strips <style> tags and external stylesheets, so when apply_styles
    is True, CSS is inlined directly on HTML elements (similar to email HTML).

    Args:
        markdown: Markdown content to convert
        standalone: If True, generate a complete HTML document
        apply_styles: If True, apply inline CSS styles for Canvas compatibility
        style_preset: Style preset to use ('default', 'minimal', 'academic', 'colorful', 'dark')
        custom_css: Custom CSS string to merge with preset

    Returns:
        HTML content with optional inline styles

    Raises:
        RuntimeError: If pandoc is not installed or conversion fails

    Examples:
        >>> html = markdown_to_html("# Hello", apply_styles=True)
        >>> 'style=' in html
        True

        >>> custom = 'h1 { color: red; } .note { background: yellow; }'
        >>> html = markdown_to_html("# Hello", apply_styles=True, custom_css=custom)
    """
    if not _check_pandoc():
        raise RuntimeError("pandoc is not installed. Install it with: apt install pandoc (Linux) or brew install pandoc (macOS)")

    cmd = ["pandoc", "-f", "markdown", "-t", "html"]
    if standalone:
        cmd.append("-s")

    try:
        result = subprocess.run(
            cmd,
            input=markdown,
            capture_output=True,
            text=True,
            check=True,
        )
        html = result.stdout

        # Apply inline styles if requested
        if apply_styles:
            from .styling import inline_styles
            html = inline_styles(html, css=custom_css, preset=style_preset)

        return html
    except subprocess.CalledProcessError as e:
        logger.error(f"Pandoc conversion failed: {e.stderr}")
        raise RuntimeError(f"Pandoc conversion failed: {e.stderr}")


def html_to_markdown(html: str, wrap: Optional[int] = None) -> str:
    """
    Convert HTML to markdown using pandoc.

    Args:
        html: HTML content to convert
        wrap: Line wrap width (None for no wrapping)

    Returns:
        Markdown content

    Raises:
        RuntimeError: If pandoc is not installed or conversion fails
    """
    if not _check_pandoc():
        raise RuntimeError("pandoc is not installed. Install it with: apt install pandoc (Linux) or brew install pandoc (macOS)")

    cmd = ["pandoc", "-f", "html", "-t", "markdown"]
    if wrap is not None:
        cmd.extend(["--wrap=auto", f"--columns={wrap}"])
    else:
        cmd.append("--wrap=none")

    try:
        result = subprocess.run(
            cmd,
            input=html,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout
    except subprocess.CalledProcessError as e:
        logger.error(f"Pandoc conversion failed: {e.stderr}")
        raise RuntimeError(f"Pandoc conversion failed: {e.stderr}")


def is_pandoc_available() -> bool:
    """Check if pandoc is available on the system."""
    return _check_pandoc()
