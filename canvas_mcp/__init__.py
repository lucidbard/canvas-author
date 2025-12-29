"""
Canvas MCP - Canvas LMS MCP server for managing wiki pages, assignments, discussions, and rubrics.

Uses pandoc for markdown <-> HTML conversion and supports two-way sync with local files.
"""

__version__ = "0.1.0"

from .client import get_canvas_client, CanvasClient
from .pandoc import markdown_to_html, html_to_markdown
from .server import mcp, main
from .exceptions import (
    CanvasMCPError,
    ConfigurationError,
    AuthenticationError,
    ResourceNotFoundError,
    APIError,
    RateLimitError,
    ValidationError,
    PandocError,
    SyncError,
    FileOperationError,
)
from .styling import (
    inline_styles,
    inline_styles_from_file,
    add_callout_box,
    add_styled_table,
    get_preset_names,
    get_preset_css,
)

__all__ = [
    # Client
    "get_canvas_client",
    "CanvasClient",
    # Pandoc
    "markdown_to_html",
    "html_to_markdown",
    # Styling
    "inline_styles",
    "inline_styles_from_file",
    "add_callout_box",
    "add_styled_table",
    "get_preset_names",
    "get_preset_css",
    # Server
    "mcp",
    "main",
    # Exceptions
    "CanvasMCPError",
    "ConfigurationError",
    "AuthenticationError",
    "ResourceNotFoundError",
    "APIError",
    "RateLimitError",
    "ValidationError",
    "PandocError",
    "SyncError",
    "FileOperationError",
]
