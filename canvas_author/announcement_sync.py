"""
Announcement Sync Module

Two-way sync between Canvas announcements and local markdown files.
Announcements are discussion topics with is_announcement=true.
"""

import re
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime

from .client import get_canvas_client, CanvasClient
from .discussions import create_discussion, update_discussion
from .pandoc import html_to_markdown, markdown_to_html, is_pandoc_available
from .datetime_utils import convert_to_iso8601, convert_from_iso8601

logger = logging.getLogger("canvas_author.announcement_sync")


def sanitize_filename(name: str) -> str:
    """Convert an announcement title to a safe filename with date prefix."""
    # Replace spaces and special chars with hyphens
    safe = re.sub(r'[^\w\s-]', '', name.lower())
    safe = re.sub(r'[-\s]+', '-', safe).strip('-')
    return safe


def create_announcement_frontmatter(announcement: Dict[str, Any]) -> str:
    """Create YAML frontmatter for an announcement file.

    Args:
        announcement: Announcement data

    Returns:
        YAML frontmatter string
    """
    lines = ["---"]

    if announcement.get('id'):
        lines.append(f"announcement_id: {announcement['id']}")

    lines.append(f"title: {announcement.get('title', 'Untitled')}")

    if announcement.get('posted_at'):
        posted_at = convert_from_iso8601(announcement['posted_at'])
        if posted_at:
            lines.append(f"posted_at: \"{posted_at}\"")

    if announcement.get('delayed_post_at'):
        delayed_post_at = convert_from_iso8601(announcement['delayed_post_at'])
        if delayed_post_at:
            lines.append(f"delayed_post_at: \"{delayed_post_at}\"")
        else:
            lines.append("delayed_post_at: null")
    else:
        lines.append("delayed_post_at: null")

    lines.append(f"published: {str(announcement.get('published', True)).lower()}")

    lines.append("---")
    lines.append("")
    return "\n".join(lines)


def parse_announcement_frontmatter(content: str) -> tuple[Dict[str, Any], str]:
    """Parse YAML frontmatter from an announcement file.

    Returns:
        Tuple of (metadata dict, body content)
    """
    if not content.startswith("---"):
        return {}, content

    # Find the closing ---
    end_idx = content.find("\n---", 3)
    if end_idx == -1:
        return {}, content

    frontmatter = content[4:end_idx]  # Skip initial ---\n
    body = content[end_idx + 4:].lstrip("\n")  # Skip closing ---\n

    metadata = {}

    for line in frontmatter.split("\n"):
        line = line.rstrip()
        if not line or ':' not in line:
            continue

        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()

        # Remove quotes
        if value.startswith('"') and value.endswith('"'):
            value = value[1:-1]
        elif value.startswith("'") and value.endswith("'"):
            value = value[1:-1]

        # Handle special values
        if value.lower() == "true":
            value = True
        elif value.lower() == "false":
            value = False
        elif value.lower() == "null" or value == "":
            value = None
        elif value.isdigit():
            value = int(value)

        metadata[key] = value

    return metadata, body


def pull_announcements(
    course_id: str,
    output_dir: str,
    overwrite: bool = False,
    limit: int = 50,
    client: Optional[CanvasClient] = None
) -> Dict[str, Any]:
    """
    Pull announcements from Canvas and save as markdown files with date prefixes.

    Args:
        course_id: Canvas course ID
        output_dir: Directory to save files (announcements subfolder will be created)
        overwrite: Overwrite existing files
        limit: Maximum number of announcements to pull (default: 50)
        client: Optional CanvasClient instance

    Returns:
        Dict with results: pulled, skipped, errors
    """
    # Create announcements subfolder
    output_path = Path(output_dir) / "announcements"
    output_path.mkdir(parents=True, exist_ok=True)

    canvas = client or get_canvas_client()
    course = canvas.get_course(course_id)

    # Get announcements (these are discussion topics with is_announcement=true)
    announcements = course.get_discussion_topics(only_announcements=True)

    results = {"pulled": [], "skipped": [], "errors": []}
    count = 0

    for announcement in announcements:
        if count >= limit:
            break

        try:
            announcement_id = str(announcement.id)
            title = announcement.title
            posted_at = getattr(announcement, 'posted_at', None)

            # Create filename with date prefix for sorting
            if posted_at:
                try:
                    date_obj = datetime.fromisoformat(str(posted_at).replace('Z', '+00:00'))
                    date_prefix = date_obj.strftime("%Y-%m-%d")
                except:
                    date_prefix = "undated"
            else:
                date_prefix = "undated"

            filename = f"{date_prefix}-{sanitize_filename(title)}.announcement.md"
            file_path = output_path / filename

            # Skip if exists and not overwriting
            if file_path.exists() and not overwrite:
                results["skipped"].append({
                    "id": announcement_id,
                    "title": title,
                    "reason": "file exists"
                })
                continue

            # Build announcement data
            announcement_data = {
                'id': announcement_id,
                'title': title,
                'posted_at': str(posted_at) if posted_at else None,
                'delayed_post_at': str(getattr(announcement, 'delayed_post_at', None)) if getattr(announcement, 'delayed_post_at', None) else None,
                'published': getattr(announcement, 'published', True),
            }

            # Convert message to markdown
            message = getattr(announcement, 'message', '') or ''
            if message and is_pandoc_available():
                message_md = html_to_markdown(message)
            else:
                message_md = message

            # Build file content
            content = create_announcement_frontmatter(announcement_data)
            content += message_md

            # Write file
            file_path.write_text(content, encoding="utf-8")
            results["pulled"].append({
                "id": announcement_id,
                "title": title,
                "file": str(file_path)
            })
            logger.info(f"Pulled announcement '{title}' to {file_path}")

            count += 1

        except Exception as e:
            results["errors"].append({
                "id": getattr(announcement, 'id', 'unknown'),
                "title": getattr(announcement, 'title', 'unknown'),
                "error": str(e)
            })
            logger.error(f"Error pulling announcement: {e}")

    logger.info(f"Pull complete: {len(results['pulled'])} pulled, {len(results['skipped'])} skipped, {len(results['errors'])} errors")
    return results


def push_announcements(
    course_id: str,
    input_dir: str,
    create_missing: bool = True,
    update_existing: bool = True,
    client: Optional[CanvasClient] = None
) -> Dict[str, Any]:
    """
    Push local markdown files to Canvas as announcements.

    Can create new announcements or update existing ones based on parameters.

    Args:
        course_id: Canvas course ID
        input_dir: Directory containing announcement markdown files (or parent dir with announcements subfolder)
        create_missing: Create announcements that don't exist on Canvas (default: True)
        update_existing: Update announcements that already exist (default: True)
        client: Optional CanvasClient instance

    Returns:
        Dict with results: created, updated, skipped, errors
    """
    # Check if input_dir has an announcements subfolder
    input_path = Path(input_dir)
    announcements_path = input_path / "announcements"
    if announcements_path.exists():
        input_path = announcements_path

    results = {"created": [], "updated": [], "skipped": [], "errors": []}

    if not input_path.exists():
        return results

    canvas = client or get_canvas_client()

    # Find all .announcement.md files
    md_files = list(input_path.glob("*.announcement.md"))
    if not md_files:
        # Also check for regular .md files
        md_files = list(input_path.glob("*.md"))

    for file_path in md_files:
        try:
            content = file_path.read_text(encoding="utf-8")
            metadata, body = parse_announcement_frontmatter(content)

            title = metadata.get("title", file_path.stem)
            announcement_id = metadata.get("announcement_id")

            # Convert markdown body to HTML
            if body and is_pandoc_available():
                message_html = markdown_to_html(body)
            else:
                message_html = body

            if announcement_id:
                # Announcement exists - update if allowed
                if not update_existing:
                    results["skipped"].append({
                        "file": str(file_path),
                        "reason": "update_existing is false"
                    })
                    continue

                # Update announcement
                update_params = {
                    'title': title if 'title' in metadata else None,
                    'message': message_html,
                    'published': metadata.get('published'),
                }

                # Remove None values
                update_params = {k: v for k, v in update_params.items() if v is not None}

                update_discussion(
                    course_id,
                    announcement_id,
                    client=canvas,
                    **update_params
                )

                results["updated"].append({
                    "id": announcement_id,
                    "title": title,
                    "file": str(file_path)
                })
                logger.info(f"Updated announcement '{title}' from {file_path.name}")

            else:
                # Announcement doesn't exist - create if allowed
                if not create_missing:
                    results["skipped"].append({
                        "file": str(file_path),
                        "reason": "no announcement_id and create_missing is false"
                    })
                    continue

                # Get scheduled post time if provided
                delayed_post_at = None
                if metadata.get('delayed_post_at'):
                    delayed_post_at = convert_to_iso8601(metadata['delayed_post_at'], use_utc=True)

                # Create announcement
                new_announcement = create_discussion(
                    course_id,
                    title=title,
                    message=message_html,
                    published=metadata.get('published', False),
                    is_announcement=True,
                    delayed_post_at=delayed_post_at,
                    client=canvas
                )

                results["created"].append({
                    "id": new_announcement['id'],
                    "title": title,
                    "file": str(file_path),
                    "html_url": new_announcement.get('html_url', '')
                })
                logger.info(f"Created announcement '{title}' from {file_path.name}")

        except Exception as e:
            results["errors"].append({
                "file": str(file_path),
                "error": str(e)
            })
            logger.error(f"Error processing {file_path}: {e}")

    logger.info(f"Push complete: {len(results['created'])} created, {len(results['updated'])} updated, {len(results['skipped'])} skipped, {len(results['errors'])} errors")
    return results


def create_announcement_from_template(
    course_id: str,
    title: str,
    template_file: str,
    variables: Optional[Dict[str, str]] = None,
    delayed_post_at: Optional[str] = None,
    published: bool = False,
    client: Optional[CanvasClient] = None
) -> Dict[str, Any]:
    """
    Create an announcement from a template file with variable substitution.

    Args:
        course_id: Canvas course ID
        title: Announcement title
        template_file: Path to template markdown file
        variables: Dict of variables to substitute in template (e.g., {'week_number': '2'})
        delayed_post_at: Schedule for later posting (ISO 8601 format)
        published: Whether to publish immediately (default: False for scheduled)
        client: Optional CanvasClient instance

    Returns:
        Dict with announcement data

    Example:
        create_announcement_from_template(
            course_id='1503378',
            title='Week 2 - The 2026 Development Landscape',
            template_file='templates/weekly-overview.md',
            variables={'week_number': '2', 'topic': 'Development Landscape'},
            delayed_post_at='2026-01-19T09:00:00Z'
        )
    """
    template_path = Path(template_file)
    if not template_path.exists():
        raise FileNotFoundError(f"Template not found: {template_file}")

    # Read template
    template_content = template_path.read_text(encoding="utf-8")

    # Substitute variables
    if variables:
        for key, value in variables.items():
            placeholder = f"{{{key}}}"
            template_content = template_content.replace(placeholder, value)

    # Parse frontmatter if present
    metadata, body = parse_announcement_frontmatter(template_content)

    # Override title if provided
    if title:
        metadata['title'] = title

    # Convert markdown to HTML
    if body and is_pandoc_available():
        message_html = markdown_to_html(body)
    else:
        message_html = body

    # Create announcement
    canvas = client or get_canvas_client()

    announcement = create_discussion(
        course_id,
        title=metadata.get('title', title),
        message=message_html,
        published=published,
        is_announcement=True,
        delayed_post_at=delayed_post_at,
        client=canvas
    )

    logger.info(f"Created announcement from template: {title}")
    return announcement
