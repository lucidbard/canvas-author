"""
Discussion Sync Module

Two-way sync between Canvas discussion topics and local YAML files.
"""

import re
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional

from .client import get_canvas_client, CanvasClient
from .discussions import list_discussions, create_discussion, update_discussion
from .pandoc import html_to_markdown, markdown_to_html, is_pandoc_available
from .datetime_utils import convert_to_iso8601, convert_from_iso8601

logger = logging.getLogger("canvas_author.discussion_sync")


def sanitize_filename(name: str) -> str:
    """Convert a discussion title to a safe filename."""
    # Replace spaces and special chars with hyphens
    safe = re.sub(r'[^\w\s-]', '', name.lower())
    safe = re.sub(r'[-\s]+', '-', safe).strip('-')
    return safe


def create_discussion_frontmatter(
    discussion: Dict[str, Any],
    assignment: Optional[Dict[str, Any]] = None
) -> str:
    """Create YAML frontmatter for a discussion file.

    Args:
        discussion: Discussion topic data
        assignment: Optional assignment data (for graded discussions)

    Returns:
        YAML frontmatter string
    """
    lines = ["---"]
    lines.append(f"title: {discussion.get('title', 'Untitled')}")

    if discussion.get('id'):
        lines.append(f"discussion_id: {discussion['id']}")

    if discussion.get('assignment_id'):
        lines.append(f"assignment_id: {discussion['assignment_id']}")

    lines.append(f"discussion_type: {discussion.get('discussion_type', 'threaded')}")
    lines.append(f"published: {str(discussion.get('published', False)).lower()}")

    # Discussion-specific fields
    if discussion.get('require_initial_post'):
        lines.append(f"require_initial_post: {str(discussion['require_initial_post']).lower()}")

    if discussion.get('reply_to_entry_required_count'):
        lines.append(f"reply_to_entry_required_count: {discussion['reply_to_entry_required_count']}")

    if discussion.get('pinned'):
        lines.append(f"pinned: {str(discussion['pinned']).lower()}")

    if discussion.get('locked'):
        lines.append(f"locked: {str(discussion['locked']).lower()}")

    if discussion.get('is_checkpointed'):
        lines.append(f"is_checkpointed: {str(discussion['is_checkpointed']).lower()}")

    # Assignment fields (for graded discussions)
    if assignment:
        lines.append(f"points_possible: {assignment.get('points_possible', 0)}")

        if assignment.get('assignment_group_id'):
            lines.append(f"assignment_group_id: {assignment['assignment_group_id']}")

        if assignment.get('grading_type'):
            lines.append(f"grading_type: {assignment.get('grading_type', 'points')}")

        # Checkpoints
        if assignment.get('checkpoints'):
            lines.append("checkpoints:")
            for checkpoint in assignment['checkpoints']:
                lines.append(f"  - tag: {checkpoint['tag']}")
                lines.append(f"    points_possible: {checkpoint['points_possible']}")
                if checkpoint.get('only_visible_to_overrides'):
                    lines.append(f"    only_visible_to_overrides: {str(checkpoint['only_visible_to_overrides']).lower()}")
                if checkpoint.get('due_at'):
                    due_at = convert_from_iso8601(checkpoint['due_at'])
                    if due_at:
                        lines.append(f"    due_at: \"{due_at}\"")
                if checkpoint.get('unlock_at'):
                    unlock_at = convert_from_iso8601(checkpoint['unlock_at'])
                    if unlock_at:
                        lines.append(f"    unlock_at: \"{unlock_at}\"")
                if checkpoint.get('lock_at'):
                    lock_at = convert_from_iso8601(checkpoint['lock_at'])
                    if lock_at:
                        lines.append(f"    lock_at: \"{lock_at}\"")

                # Checkpoint overrides for differentiated deadlines
                overrides = checkpoint.get('overrides', [])
                if overrides:
                    lines.append("    overrides:")
                    for override in overrides:
                        lines.append(f"      - id: {override.get('id', '')}")

                        # Student IDs
                        if override.get('student_ids'):
                            student_ids_str = ", ".join(str(sid) for sid in override['student_ids'])
                            lines.append(f"        student_ids: [{student_ids_str}]")

                        # Title (optional)
                        if override.get('title'):
                            lines.append(f"        title: \"{override['title']}\"")

                        # Dates
                        if override.get('due_at'):
                            override_due_at = convert_from_iso8601(override['due_at'])
                            if override_due_at:
                                lines.append(f"        due_at: \"{override_due_at}\"")
                        if override.get('unlock_at'):
                            override_unlock_at = convert_from_iso8601(override['unlock_at'])
                            if override_unlock_at:
                                lines.append(f"        unlock_at: \"{override_unlock_at}\"")
                        if override.get('lock_at'):
                            override_lock_at = convert_from_iso8601(override['lock_at'])
                            if override_lock_at:
                                lines.append(f"        lock_at: \"{override_lock_at}\"")

        # Due dates (for non-checkpointed discussions)
        elif assignment.get('due_at'):
            due_at = convert_from_iso8601(assignment['due_at'])
            if due_at:
                lines.append(f"due_at: \"{due_at}\"")

        if assignment.get('unlock_at') and not assignment.get('checkpoints'):
            unlock_at = convert_from_iso8601(assignment['unlock_at'])
            if unlock_at:
                lines.append(f"unlock_at: \"{unlock_at}\"")

        if assignment.get('lock_at') and not assignment.get('checkpoints'):
            lock_at = convert_from_iso8601(assignment['lock_at'])
            if lock_at:
                lines.append(f"lock_at: \"{lock_at}\"")

    lines.append("---")
    lines.append("")
    return "\n".join(lines)


def parse_discussion_frontmatter(content: str) -> tuple[Dict[str, Any], str]:
    """Parse YAML frontmatter from a discussion file.

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
    current_key = None
    current_list = None
    current_dict = None

    for line in frontmatter.split("\n"):
        line_stripped = line.rstrip()
        if not line_stripped:
            continue

        # Check for list item with sub-dict (checkpoints)
        if line.startswith("  - ") and current_key == "checkpoints":
            # New checkpoint item
            if current_dict:
                current_list.append(current_dict)
            current_dict = {}
            # Parse the field after -
            if ":" in line[4:]:
                key, _, value = line[4:].partition(":")
                key = key.strip()
                value = value.strip()
                if value.startswith('"') and value.endswith('"'):
                    value = value[1:-1]
                elif value.lower() == "true":
                    value = True
                elif value.lower() == "false":
                    value = False
                elif value and value.replace('.', '').replace('-', '').isdigit():
                    value = float(value) if '.' in value else int(value)
                current_dict[key] = value
            continue

        # Check for nested list (overrides within checkpoints)
        if line.startswith("      - ") and current_dict is not None and 'overrides' in current_dict:
            # New override item within a checkpoint
            override_list = current_dict.get('overrides', [])
            if not isinstance(override_list, list):
                override_list = []
                current_dict['overrides'] = override_list

            # Start new override dict
            override_dict = {}
            # Parse the field after -
            if ":" in line[8:]:
                key, _, value = line[8:].partition(":")
                key = key.strip()
                value = value.strip()
                if value.startswith('"') and value.endswith('"'):
                    value = value[1:-1]
                elif value and value.replace('.', '').replace('-', '').isdigit():
                    value = float(value) if '.' in value else int(value)
                override_dict[key] = value
            override_list.append(override_dict)
            continue

        # Check for override field (within checkpoint overrides)
        if line.startswith("        ") and current_dict is not None and 'overrides' in current_dict:
            if ":" in line:
                override_list = current_dict.get('overrides', [])
                if override_list and isinstance(override_list, list):
                    last_override = override_list[-1]

                    key, _, value = line[8:].partition(":")
                    key = key.strip()
                    value = value.strip()

                    # Handle arrays like student_ids: [1, 2, 3]
                    if value.startswith('[') and value.endswith(']'):
                        array_content = value[1:-1].strip()
                        if array_content:
                            items = [item.strip() for item in array_content.split(',')]
                            try:
                                value = [int(item) for item in items]
                            except:
                                value = items
                        else:
                            value = []
                    elif value.startswith('"') and value.endswith('"'):
                        value = value[1:-1]
                    elif value.lower() == "true":
                        value = True
                    elif value.lower() == "false":
                        value = False
                    elif value.lower() == "null":
                        value = None
                    elif value and value.replace('.', '').replace('-', '').isdigit():
                        value = float(value) if '.' in value else int(value)

                    last_override[key] = value
            continue

        # Check for sub-dict field (checkpoint fields)
        if line.startswith("    ") and current_dict is not None:
            if ":" in line:
                key, _, value = line[4:].partition(":")
                key = key.strip()
                value = value.strip()

                # Empty value means upcoming list (like overrides:)
                if value == "":
                    current_dict[key] = []
                elif value.startswith('"') and value.endswith('"'):
                    value = value[1:-1]
                    current_dict[key] = value
                elif value.lower() == "true":
                    current_dict[key] = True
                elif value.lower() == "false":
                    current_dict[key] = False
                elif value and value.replace('.', '').replace('-', '').isdigit():
                    value = float(value) if '.' in value else int(value)
                    current_dict[key] = value
                else:
                    current_dict[key] = value
            continue

        # Check for key: value
        if ":" in line:
            # Finish any current dict
            if current_dict and current_list is not None:
                current_list.append(current_dict)
                current_dict = None

            key, _, value = line.partition(":")
            key = key.strip()
            value = value.strip()

            # Remove quotes
            if value.startswith('"') and value.endswith('"'):
                value = value[1:-1]
            elif value.startswith("'") and value.endswith("'"):
                value = value[1:-1]

            # Handle boolean
            if value.lower() == "true":
                value = True
            elif value.lower() == "false":
                value = False
            # Handle numbers
            elif value and value.replace('.', '').replace('-', '').isdigit():
                value = float(value) if '.' in value else int(value)

            # Empty value means upcoming list
            if value == "":
                current_key = key
                current_list = []
                metadata[key] = current_list
            else:
                metadata[key] = value
                current_key = key
                current_list = None

    # Finish any remaining dict
    if current_dict and current_list is not None:
        current_list.append(current_dict)

    return metadata, body


def pull_discussions(
    course_id: str,
    output_dir: str,
    overwrite: bool = False,
    only_announcements: bool = False,
    client: Optional[CanvasClient] = None
) -> Dict[str, Any]:
    """
    Pull all discussion topics from Canvas and save as YAML markdown files.

    Args:
        course_id: Canvas course ID
        output_dir: Directory to save files (discussions subfolder will be created)
        overwrite: Overwrite existing files
        only_announcements: Only pull announcements (not regular discussions)
        client: Optional CanvasClient instance

    Returns:
        Dict with results: pulled, skipped, errors
    """
    # Create discussions subfolder
    subfolder_name = "announcements" if only_announcements else "discussions"
    output_path = Path(output_dir) / subfolder_name
    output_path.mkdir(parents=True, exist_ok=True)

    canvas = client or get_canvas_client()
    course = canvas.get_course(course_id)

    # Get all discussion topics
    if only_announcements:
        topics = course.get_discussion_topics(only_announcements=True)
    else:
        topics = course.get_discussion_topics()

    results = {"pulled": [], "skipped": [], "errors": []}

    for topic in topics:
        try:
            topic_id = str(topic.id)
            title = topic.title
            filename = f"{sanitize_filename(title)}.md"
            file_path = output_path / filename

            # Skip if exists and not overwriting
            if file_path.exists() and not overwrite:
                results["skipped"].append({"id": topic_id, "title": title, "reason": "file exists"})
                continue

            # Get full topic data
            is_checkpointed = getattr(topic, 'is_checkpointed', False)
            reply_to_entry_required_count = getattr(topic, 'reply_to_entry_required_count', 0)

            discussion_data = {
                'id': topic_id,
                'title': title,
                'discussion_type': getattr(topic, 'discussion_type', 'threaded'),
                'published': getattr(topic, 'published', True),
                'pinned': getattr(topic, 'pinned', False),
                'locked': getattr(topic, 'locked', False),
                'require_initial_post': getattr(topic, 'require_initial_post', False),
                'is_checkpointed': is_checkpointed,
            }

            if reply_to_entry_required_count:
                discussion_data['reply_to_entry_required_count'] = reply_to_entry_required_count

            # Get assignment data if this is a graded discussion
            assignment_data = None
            assignment_id = getattr(topic, 'assignment_id', None)
            if assignment_id:
                discussion_data['assignment_id'] = str(assignment_id)

                # Get assignment data from the topic's assignment dict (has checkpoints)
                topic_assignment = getattr(topic, 'assignment', {})
                if topic_assignment:
                    assignment_data = {
                        'points_possible': topic_assignment.get('points_possible', 0),
                        'grading_type': topic_assignment.get('grading_type', 'points'),
                        'assignment_group_id': topic_assignment.get('assignment_group_id', None),
                    }

                    # Get checkpoint data from topic's assignment dict
                    if is_checkpointed and 'checkpoints' in topic_assignment:
                        assignment_data['checkpoints'] = topic_assignment['checkpoints']
                    else:
                        # Regular due dates
                        if topic_assignment.get('due_at'):
                            assignment_data['due_at'] = str(topic_assignment['due_at'])
                        if topic_assignment.get('unlock_at'):
                            assignment_data['unlock_at'] = str(topic_assignment['unlock_at'])
                        if topic_assignment.get('lock_at'):
                            assignment_data['lock_at'] = str(topic_assignment['lock_at'])

            # Convert message to markdown
            message = getattr(topic, 'message', '') or ''
            if message and is_pandoc_available():
                message_md = html_to_markdown(message)
            else:
                message_md = message

            # Build file content
            content = create_discussion_frontmatter(discussion_data, assignment_data)
            content += message_md

            # Write file
            file_path.write_text(content, encoding="utf-8")
            results["pulled"].append({
                "id": topic_id,
                "title": title,
                "file": str(file_path)
            })
            logger.info(f"Pulled discussion '{title}' to {file_path}")

        except Exception as e:
            results["errors"].append({
                "id": getattr(topic, 'id', 'unknown'),
                "title": getattr(topic, 'title', 'unknown'),
                "error": str(e)
            })
            logger.error(f"Error pulling discussion: {e}")

    logger.info(f"Pull complete: {len(results['pulled'])} pulled, {len(results['skipped'])} skipped, {len(results['errors'])} errors")
    return results


def push_discussions(
    course_id: str,
    input_dir: str,
    create_missing: bool = True,
    update_existing: bool = True,
    is_announcements: bool = False,
    client: Optional[CanvasClient] = None
) -> Dict[str, Any]:
    """
    Push local markdown files to Canvas as discussion topics.

    Can create new discussions or update existing ones based on parameters.

    Args:
        course_id: Canvas course ID
        input_dir: Directory containing discussion markdown files (or parent dir with discussions subfolder)
        create_missing: Create discussions that don't exist on Canvas (default: True)
        update_existing: Update discussions that already exist (default: True)
        is_announcements: Process announcements instead of discussions
        client: Optional CanvasClient instance

    Returns:
        Dict with results: created, updated, skipped, errors
    """
    # Check if input_dir has a discussions/announcements subfolder
    input_path = Path(input_dir)
    subfolder_name = "announcements" if is_announcements else "discussions"
    subfolder_path = input_path / subfolder_name
    if subfolder_path.exists():
        input_path = subfolder_path

    results = {"created": [], "updated": [], "skipped": [], "errors": []}

    if not input_path.exists():
        return results

    canvas = client or get_canvas_client()

    # Find all .md files
    md_files = list(input_path.glob("*.md"))

    for file_path in md_files:
        try:
            content = file_path.read_text(encoding="utf-8")
            metadata, body = parse_discussion_frontmatter(content)

            title = metadata.get("title", file_path.stem)
            discussion_id = metadata.get("discussion_id")

            # Convert markdown body to HTML
            if body and is_pandoc_available():
                message_html = markdown_to_html(body)
            else:
                message_html = body

            # Build assignment config if graded discussion
            assignment_config = None
            if 'points_possible' in metadata or 'checkpoints' in metadata:
                assignment_config = {
                    'points_possible': metadata.get('points_possible', 0),
                    'grading_type': metadata.get('grading_type', 'points'),
                }

                if 'assignment_group_id' in metadata:
                    assignment_config['assignment_group_id'] = metadata['assignment_group_id']

                if 'checkpoints' in metadata:
                    # Convert checkpoint dates to ISO 8601
                    checkpoints = []
                    for cp in metadata['checkpoints']:
                        checkpoint = {
                            'tag': cp['tag'],
                            'points_possible': cp['points_possible'],
                        }
                        if 'due_at' in cp:
                            checkpoint['due_at'] = convert_to_iso8601(cp['due_at'], use_utc=True)
                        if 'unlock_at' in cp:
                            checkpoint['unlock_at'] = convert_to_iso8601(cp['unlock_at'], use_utc=True)
                        if 'lock_at' in cp:
                            checkpoint['lock_at'] = convert_to_iso8601(cp['lock_at'], use_utc=True)
                        checkpoints.append(checkpoint)

                    assignment_config['checkpoints'] = checkpoints
                    if 'reply_to_entry_required_count' in metadata:
                        assignment_config['reply_to_entry_required_count'] = metadata['reply_to_entry_required_count']
                else:
                    # Regular due dates
                    if 'due_at' in metadata:
                        assignment_config['due_at'] = convert_to_iso8601(metadata['due_at'], use_utc=True)
                    if 'unlock_at' in metadata:
                        assignment_config['unlock_at'] = convert_to_iso8601(metadata['unlock_at'], use_utc=True)
                    if 'lock_at' in metadata:
                        assignment_config['lock_at'] = convert_to_iso8601(metadata['lock_at'], use_utc=True)

            if discussion_id:
                # Discussion exists - update if allowed
                if not update_existing:
                    results["skipped"].append({
                        "file": str(file_path),
                        "reason": "update_existing is false"
                    })
                    continue

                # Update discussion
                update_params = {
                    'title': title if 'title' in metadata else None,
                    'message': message_html,
                    'published': metadata.get('published'),
                    'pinned': metadata.get('pinned'),
                    'locked': metadata.get('locked'),
                    'require_initial_post': metadata.get('require_initial_post'),
                }

                # Remove None values
                update_params = {k: v for k, v in update_params.items() if v is not None}

                # Update assignment if present
                if assignment_config:
                    update_params['assignment_updates'] = assignment_config

                update_discussion(
                    course_id,
                    discussion_id,
                    client=canvas,
                    **update_params
                )

                results["updated"].append({
                    "id": discussion_id,
                    "title": title,
                    "file": str(file_path)
                })
                logger.info(f"Updated discussion '{title}' from {file_path.name}")

            else:
                # Discussion doesn't exist - create if allowed
                if not create_missing:
                    results["skipped"].append({
                        "file": str(file_path),
                        "reason": "no discussion_id and create_missing is false"
                    })
                    continue

                # Create discussion
                new_discussion = create_discussion(
                    course_id,
                    title=title,
                    message=message_html,
                    discussion_type=metadata.get('discussion_type', 'threaded'),
                    published=metadata.get('published', False),
                    assignment=assignment_config,
                    require_initial_post=metadata.get('require_initial_post', False),
                    is_announcement=is_announcements,
                    client=canvas
                )

                results["created"].append({
                    "id": new_discussion['id'],
                    "title": title,
                    "file": str(file_path),
                    "html_url": new_discussion.get('html_url', '')
                })
                logger.info(f"Created discussion '{title}' from {file_path.name}")

        except Exception as e:
            results["errors"].append({
                "file": str(file_path),
                "error": str(e)
            })
            logger.error(f"Error processing {file_path}: {e}")

    logger.info(f"Push complete: {len(results['created'])} created, {len(results['updated'])} updated, {len(results['skipped'])} skipped, {len(results['errors'])} errors")
    return results
