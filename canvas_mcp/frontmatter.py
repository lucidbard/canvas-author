"""
Frontmatter Module

Shared utilities for parsing and generating YAML frontmatter in markdown files.
Uses PyYAML for robust parsing.
"""

import re
import logging
from typing import Dict, Any, Tuple, Optional
from datetime import datetime

try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False

logger = logging.getLogger("canvas_mcp.frontmatter")

# Frontmatter delimiter
FRONTMATTER_DELIMITER = "---"

# Regex to match frontmatter block
FRONTMATTER_PATTERN = re.compile(
    r'^---\s*\n(.*?)\n---\s*\n',
    re.DOTALL
)


class FrontmatterError(Exception):
    """Raised when frontmatter parsing fails."""
    pass


def parse_frontmatter(content: str) -> Tuple[Dict[str, Any], str]:
    """
    Parse YAML frontmatter from markdown content.

    Args:
        content: Markdown content with optional frontmatter

    Returns:
        Tuple of (metadata dict, body content)

    Raises:
        FrontmatterError: If frontmatter exists but is malformed

    Examples:
        >>> content = '''---
        ... title: My Page
        ... published: true
        ... ---
        ...
        ... # Body content
        ... '''
        >>> meta, body = parse_frontmatter(content)
        >>> meta['title']
        'My Page'
        >>> meta['published']
        True
    """
    if not content:
        return {}, ""

    # Check if content starts with frontmatter delimiter
    if not content.startswith(FRONTMATTER_DELIMITER):
        return {}, content

    # Use regex to extract frontmatter block
    match = FRONTMATTER_PATTERN.match(content)
    if not match:
        # Has opening delimiter but no valid frontmatter block
        # Could be malformed or just content starting with ---
        logger.debug("Content starts with --- but no valid frontmatter found")
        return {}, content

    frontmatter_text = match.group(1)
    body = content[match.end():]

    # Parse YAML
    if YAML_AVAILABLE:
        try:
            metadata = yaml.safe_load(frontmatter_text)
            if metadata is None:
                metadata = {}
            elif not isinstance(metadata, dict):
                raise FrontmatterError(
                    f"Frontmatter must be a YAML mapping, got {type(metadata).__name__}"
                )
        except yaml.YAMLError as e:
            raise FrontmatterError(f"Invalid YAML in frontmatter: {e}")
    else:
        # Fallback to simple parsing if PyYAML not available
        metadata = _parse_simple_yaml(frontmatter_text)

    return metadata, body


def _parse_simple_yaml(text: str) -> Dict[str, Any]:
    """
    Simple YAML parser fallback when PyYAML is not available.

    Only handles simple key: value pairs, not nested structures.
    """
    metadata = {}
    for line in text.strip().split('\n'):
        line = line.strip()
        if not line or line.startswith('#'):
            continue

        # Find the first colon (handles values with colons)
        colon_idx = line.find(':')
        if colon_idx == -1:
            continue

        key = line[:colon_idx].strip()
        value = line[colon_idx + 1:].strip()

        # Remove quotes if present
        if (value.startswith('"') and value.endswith('"')) or \
           (value.startswith("'") and value.endswith("'")):
            value = value[1:-1]

        # Type conversion
        value = _convert_yaml_value(value)
        metadata[key] = value

    return metadata


def _convert_yaml_value(value: str) -> Any:
    """Convert a string value to appropriate Python type."""
    if not value:
        return None

    # Boolean
    if value.lower() in ('true', 'yes', 'on'):
        return True
    if value.lower() in ('false', 'no', 'off'):
        return False

    # Null
    if value.lower() in ('null', 'none', '~'):
        return None

    # Integer
    try:
        return int(value)
    except ValueError:
        pass

    # Float
    try:
        return float(value)
    except ValueError:
        pass

    return value


def generate_frontmatter(metadata: Dict[str, Any]) -> str:
    """
    Generate YAML frontmatter from a metadata dict.

    Args:
        metadata: Dictionary of metadata key-value pairs

    Returns:
        Formatted frontmatter string including delimiters

    Examples:
        >>> meta = {'title': 'My Page', 'published': True}
        >>> print(generate_frontmatter(meta))
        ---
        title: My Page
        published: true
        ---
    """
    lines = [FRONTMATTER_DELIMITER]

    for key, value in metadata.items():
        if value is None:
            continue
        formatted_value = _format_yaml_value(value)
        lines.append(f"{key}: {formatted_value}")

    lines.append(FRONTMATTER_DELIMITER)
    lines.append("")  # Blank line after frontmatter

    return "\n".join(lines)


def _format_yaml_value(value: Any) -> str:
    """Format a Python value for YAML output."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if value is None:
        return "null"

    # String value - quote if contains special characters
    str_value = str(value)
    if ':' in str_value or '\n' in str_value or str_value.startswith('"'):
        # Quote the value
        escaped = str_value.replace('"', '\\"')
        return f'"{escaped}"'

    return str_value


def create_page_frontmatter(
    title: str,
    url: str,
    course_id: str,
    published: bool = True,
    front_page: bool = False,
    updated_at: Optional[str] = None,
) -> str:
    """
    Create frontmatter for a Canvas wiki page.

    Args:
        title: Page title
        url: Page URL slug
        course_id: Canvas course ID
        published: Whether the page is published
        front_page: Whether this is the front page
        updated_at: Last update timestamp

    Returns:
        Formatted frontmatter string
    """
    metadata = {
        "title": title,
        "url": url,
        "course_id": course_id,
        "published": published,
        "front_page": front_page,
        "updated_at": updated_at or datetime.now().isoformat(),
    }
    return generate_frontmatter(metadata)


def update_frontmatter(content: str, updates: Dict[str, Any]) -> str:
    """
    Update frontmatter values in existing content.

    Args:
        content: Markdown content with frontmatter
        updates: Dictionary of values to update

    Returns:
        Content with updated frontmatter

    Raises:
        FrontmatterError: If content has no valid frontmatter
    """
    metadata, body = parse_frontmatter(content)

    if not metadata:
        raise FrontmatterError("Content has no frontmatter to update")

    metadata.update(updates)
    return generate_frontmatter(metadata) + body


def has_frontmatter(content: str) -> bool:
    """Check if content has valid frontmatter."""
    if not content or not content.startswith(FRONTMATTER_DELIMITER):
        return False
    return bool(FRONTMATTER_PATTERN.match(content))
