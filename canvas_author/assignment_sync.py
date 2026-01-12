"""
Assignment Sync Module

Two-way sync between Canvas assignments and local markdown files.
"""

import re
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional

from .client import get_canvas_client, CanvasClient
from .assignments import list_assignments, get_assignment
from .pandoc import html_to_markdown, markdown_to_html, is_pandoc_available
from .datetime_utils import convert_to_iso8601, convert_from_iso8601, convert_to_datetime

logger = logging.getLogger("canvas_author.assignment_sync")


def sanitize_filename(name: str) -> str:
    """Convert an assignment name to a safe filename."""
    # Replace spaces and special chars with hyphens
    safe = re.sub(r'[^\w\s-]', '', name.lower())
    safe = re.sub(r'[-\s]+', '-', safe).strip('-')
    return safe


def create_assignment_frontmatter(
    assignment: Dict[str, Any],
    course_id: str,
) -> str:
    """Create YAML frontmatter for an assignment file."""
    lines = ["---"]
    lines.append(f"title: {assignment.get('name', 'Untitled')}")

    if assignment.get('id'):
        lines.append(f"assignment_id: {assignment['id']}")

    if assignment.get('assignment_group_id'):
        lines.append(f"assignment_group_id: {assignment['assignment_group_id']}")

    lines.append(f"points_possible: {assignment.get('points_possible', 0)}")

    # Convert datetime fields from ISO 8601 to simple format
    if assignment.get('due_at'):
        due_at = convert_from_iso8601(assignment['due_at'])
        if due_at:
            lines.append(f"due_at: \"{due_at}\"")
    if assignment.get('unlock_at'):
        unlock_at = convert_from_iso8601(assignment['unlock_at'])
        if unlock_at:
            lines.append(f"unlock_at: \"{unlock_at}\"")
    if assignment.get('lock_at'):
        lock_at = convert_from_iso8601(assignment['lock_at'])
        if lock_at:
            lines.append(f"lock_at: \"{lock_at}\"")

    # Submission types as a list
    submission_types = assignment.get('submission_types', [])
    if submission_types:
        lines.append("submission_types:")
        for st in submission_types:
            lines.append(f"  - {st}")

    # Allowed extensions (for online_upload submissions)
    allowed_extensions = assignment.get('allowed_extensions', [])
    if allowed_extensions:
        lines.append("allowed_extensions:")
        for ext in allowed_extensions:
            lines.append(f"  - {ext}")

    lines.append(f"grading_type: {assignment.get('grading_type', 'points')}")
    lines.append(f"published: {str(assignment.get('published', False)).lower()}")

    lines.append("---")
    lines.append("")
    return "\n".join(lines)


def parse_assignment_frontmatter(content: str) -> tuple[Dict[str, Any], str]:
    """Parse YAML frontmatter from an assignment markdown file.

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

    for line in frontmatter.split("\n"):
        line = line.rstrip()
        if not line:
            continue

        # Check for list item
        if line.startswith("  - ") and current_key:
            if current_list is None:
                current_list = []
            current_list.append(line[4:])
            metadata[current_key] = current_list
            continue

        # Check for key: value
        if ":" in line:
            if current_list is not None:
                current_list = None

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
            elif value.isdigit():
                value = int(value)
            elif re.match(r'^\d+\.\d+$', value):
                value = float(value)

            # Empty value means upcoming list
            if value == "":
                current_key = key
                current_list = []
                metadata[key] = current_list
            else:
                metadata[key] = value
                current_key = key

    return metadata, body


def _create_assignment_from_markdown(
    course_id: str,
    metadata: Dict[str, Any],
    body: str,
    client: CanvasClient
) -> Dict[str, Any]:
    """Create a new assignment from parsed markdown data."""
    course = client.get_course(course_id)

    # Convert markdown body to HTML
    if body and is_pandoc_available():
        description_html = markdown_to_html(body)
    else:
        description_html = body

    # Build assignment parameters from metadata
    assignment_params = {
        "name": metadata.get("title", "Untitled Assignment"),
        "description": description_html,
        "points_possible": metadata.get("points_possible", 0),
        "grading_type": metadata.get("grading_type", "points"),
        "published": metadata.get("published", False),
    }

    # NOTE: Canvas API appears to have issues accepting due_at, unlock_at, and lock_at
    # during assignment creation. We'll create the assignment first, then update dates separately.
    has_dates = bool(metadata.get("due_at") or metadata.get("unlock_at") or metadata.get("lock_at"))
    date_params = {}

    if metadata.get("due_at"):
        logger.info(f"Will set due_at after creation: '{metadata.get('due_at')}'")
        date_params["due_at"] = convert_to_iso8601(metadata["due_at"], use_utc=True)
    if metadata.get("unlock_at"):
        logger.info(f"Will set unlock_at after creation: '{metadata.get('unlock_at')}'")
        date_params["unlock_at"] = convert_to_iso8601(metadata["unlock_at"], use_utc=True)
    if metadata.get("lock_at"):
        logger.info(f"Will set lock_at after creation: '{metadata.get('lock_at')}'")
        date_params["lock_at"] = convert_to_iso8601(metadata["lock_at"], use_utc=True)

    # Add submission types
    if metadata.get("submission_types"):
        assignment_params["submission_types"] = metadata["submission_types"]

    # Add allowed extensions (for file uploads)
    if metadata.get("allowed_extensions"):
        assignment_params["allowed_extensions"] = metadata["allowed_extensions"]

    logger.info(f"Creating assignment '{metadata.get('title')}' with params: {assignment_params}")

    # Create the assignment via Canvas API
    assignment = course.create_assignment(assignment=assignment_params)

    # Update with dates separately if present
    if has_dates:
        logger.info(f"Updating assignment {assignment.id} with dates: {date_params}")
        assignment = assignment.edit(assignment=date_params)

    return {
        "id": str(assignment.id),
        "name": assignment.name,
        "points_possible": assignment.points_possible,
        "html_url": assignment.html_url if hasattr(assignment, 'html_url') else None,
    }


def pull_assignments(
    course_id: str,
    output_dir: str,
    overwrite: bool = False,
    client: Optional[CanvasClient] = None
) -> Dict[str, Any]:
    """
    Pull all assignments from Canvas and save as markdown files.

    Args:
        course_id: Canvas course ID
        output_dir: Directory to save markdown files (assignments subfolder will be created)
        overwrite: Overwrite existing files
        client: Optional CanvasClient instance

    Returns:
        Dict with results: pulled, skipped, errors
    """
    # Create assignments subfolder
    output_path = Path(output_dir) / "assignments"
    output_path.mkdir(parents=True, exist_ok=True)

    assignments = list_assignments(course_id, client)
    results = {"pulled": [], "skipped": [], "errors": []}

    for assignment_meta in assignments:
        try:
            assignment_id = assignment_meta["id"]
            name = assignment_meta.get("name", f"assignment-{assignment_id}")
            filename = f"{sanitize_filename(name)}.md"
            file_path = output_path / filename

            # Skip if exists and not overwriting
            if file_path.exists() and not overwrite:
                results["skipped"].append({"id": assignment_id, "name": name, "reason": "file exists"})
                continue

            # Get full assignment content
            assignment = get_assignment(course_id, assignment_id, client)

            # Convert HTML description to markdown
            description_html = assignment.get("description", "") or ""
            if description_html and is_pandoc_available():
                description_md = html_to_markdown(description_html)
            else:
                description_md = description_html

            # Build content with frontmatter
            content = create_assignment_frontmatter(assignment, course_id)
            content += description_md

            # Write file
            file_path.write_text(content, encoding="utf-8")
            results["pulled"].append({
                "id": assignment_id,
                "name": name,
                "file": str(file_path)
            })
            logger.info(f"Pulled assignment '{name}' to {file_path}")

        except Exception as e:
            results["errors"].append({
                "id": assignment_meta.get("id", "unknown"),
                "name": assignment_meta.get("name", "unknown"),
                "error": str(e)
            })
            logger.error(f"Error pulling assignment: {e}")

    logger.info(f"Pull complete: {len(results['pulled'])} pulled, {len(results['skipped'])} skipped, {len(results['errors'])} errors")
    return results


def push_assignments(
    course_id: str,
    input_dir: str,
    create_missing: bool = True,
    update_existing: bool = True,
    client: Optional[CanvasClient] = None
) -> Dict[str, Any]:
    """
    Push local markdown files to Canvas as assignments.

    Can create new assignments or update existing ones based on parameters.

    Args:
        course_id: Canvas course ID
        input_dir: Directory containing assignment markdown files (or parent dir with assignments subfolder)
        create_missing: Create assignments that don't exist on Canvas (default: True)
        update_existing: Update assignments that already exist (default: True)
        client: Optional CanvasClient instance

    Returns:
        Dict with results: created, updated, skipped, errors
    """
    # Check if input_dir has an assignments subfolder
    input_path = Path(input_dir)
    assignments_path = input_path / "assignments"
    if assignments_path.exists():
        input_path = assignments_path

    results = {"created": [], "updated": [], "skipped": [], "errors": []}

    if not input_path.exists():
        return results

    canvas = client or get_canvas_client()
    course = canvas.get_course(course_id)

    # Find all .md files
    md_files = list(input_path.glob("*.md"))

    for file_path in md_files:
        try:
            content = file_path.read_text(encoding="utf-8")
            metadata, body = parse_assignment_frontmatter(content)

            title = metadata.get("title", file_path.stem)
            assignment_id = metadata.get("assignment_id")

            if assignment_id:
                # Assignment exists - update if allowed
                if not update_existing:
                    results["skipped"].append({
                        "file": str(file_path),
                        "reason": "update_existing is false"
                    })
                    continue

                # Convert markdown body to HTML
                if body and is_pandoc_available():
                    description_html = markdown_to_html(body)
                else:
                    description_html = body

                # Build update parameters from metadata
                update_params = {
                    "description": description_html,
                }

                # Add optional fields if present in metadata
                if "points_possible" in metadata:
                    update_params["points_possible"] = metadata["points_possible"]
                if "grading_type" in metadata:
                    update_params["grading_type"] = metadata["grading_type"]
                if "published" in metadata:
                    update_params["published"] = metadata["published"]
                if "submission_types" in metadata:
                    update_params["submission_types"] = metadata["submission_types"]
                if "allowed_extensions" in metadata:
                    update_params["allowed_extensions"] = metadata["allowed_extensions"]

                # Add date fields with ISO 8601 conversion (UTC format with 'Z')
                if metadata.get("due_at"):
                    update_params["due_at"] = convert_to_iso8601(metadata["due_at"], use_utc=True)
                if metadata.get("unlock_at"):
                    update_params["unlock_at"] = convert_to_iso8601(metadata["unlock_at"], use_utc=True)
                if metadata.get("lock_at"):
                    update_params["lock_at"] = convert_to_iso8601(metadata["lock_at"], use_utc=True)

                # Update the assignment
                assignment = course.get_assignment(assignment_id)
                logger.debug(f"Update params for assignment {assignment_id}: {update_params}")
                assignment.edit(assignment=update_params)

                results["updated"].append({
                    "id": assignment_id,
                    "name": title,
                    "file": str(file_path)
                })
                logger.info(f"Updated assignment '{title}' from {file_path.name}")

            else:
                # Assignment doesn't exist - create if allowed
                if not create_missing:
                    results["skipped"].append({
                        "file": str(file_path),
                        "reason": "no assignment_id and create_missing is false"
                    })
                    continue

                new_assignment = _create_assignment_from_markdown(
                    course_id, metadata, body, canvas
                )

                # Update the file with the new assignment_id
                metadata["assignment_id"] = new_assignment["id"]
                updated_content = create_assignment_frontmatter(new_assignment, course_id)
                updated_content += body
                file_path.write_text(updated_content, encoding="utf-8")

                results["created"].append({
                    "id": new_assignment["id"],
                    "name": title,
                    "file": str(file_path),
                    "url": new_assignment.get("html_url")
                })
                logger.info(f"Created assignment '{title}' from {file_path.name}")

        except Exception as e:
            results["errors"].append({
                "file": str(file_path),
                "error": str(e)
            })
            logger.error(f"Error pushing assignment {file_path}: {e}")

    logger.info(f"Push complete: {len(results['created'])} created, {len(results['updated'])} updated, {len(results['skipped'])} skipped, {len(results['errors'])} errors")
    return results


def assignment_sync_status(
    course_id: str,
    local_dir: str,
    client: Optional[CanvasClient] = None
) -> Dict[str, Any]:
    """
    Compare Canvas assignments with local files.

    Args:
        course_id: Canvas course ID
        local_dir: Local directory (checks for assignments subfolder)
        client: Optional CanvasClient instance

    Returns:
        Dict with synced, canvas_only, local_only lists and summary counts
    """
    # Check for assignments subfolder
    local_path = Path(local_dir)
    assignments_path = local_path / "assignments"
    if assignments_path.exists():
        local_path = assignments_path

    # Get Canvas assignments
    canvas_assignments = list_assignments(course_id, client)
    canvas_by_id = {a["id"]: a for a in canvas_assignments}

    # Get local assignments
    local_by_id = {}
    if local_path.exists():
        for file_path in local_path.glob("*.md"):
            content = file_path.read_text(encoding="utf-8")
            metadata, _ = parse_assignment_frontmatter(content)
            assignment_id = metadata.get("assignment_id")
            if assignment_id:
                local_by_id[assignment_id] = {
                    "file": str(file_path),
                    "name": metadata.get("title", file_path.stem)
                }

    # Compare
    synced = []
    canvas_only = []
    local_only = []

    canvas_ids = set(canvas_by_id.keys())
    local_ids = set(local_by_id.keys())

    for aid in canvas_ids & local_ids:
        synced.append({
            "id": aid,
            "name": canvas_by_id[aid].get("name", ""),
            "file": local_by_id[aid]["file"]
        })

    for aid in canvas_ids - local_ids:
        canvas_only.append({
            "id": aid,
            "name": canvas_by_id[aid].get("name", "")
        })

    for aid in local_ids - canvas_ids:
        local_only.append({
            "id": aid,
            "name": local_by_id[aid]["name"],
            "file": local_by_id[aid]["file"]
        })

    return {
        "synced": synced,
        "canvas_only": canvas_only,
        "local_only": local_only,
        "summary": {
            "synced_count": len(synced),
            "canvas_only_count": len(canvas_only),
            "local_only_count": len(local_only)
        }
    }
