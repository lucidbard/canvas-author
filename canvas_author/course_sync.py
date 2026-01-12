"""
Course Sync

Sync Canvas course settings with local course.yaml file.
Handles conflict detection and link transformation.
"""

import logging
import re
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime
import yaml

from .client import get_canvas_client, CanvasClient
from .assignment_groups import list_assignment_groups

logger = logging.getLogger("canvas_author.course_sync")

COURSE_FILE = "course.yaml"

# Course settings that can be synced via API
SYNCABLE_SETTINGS = {
    # Basic info
    "name": {"api_field": "name", "editable": True},
    "course_code": {"api_field": "course_code", "editable": True},

    # Display settings
    "default_view": {"api_field": "default_view", "editable": True},  # modules, syllabus, assignments, feed, wiki
    "front_page": {"api_field": None, "editable": True},  # Special handling via set_front_page

    # Syllabus
    "syllabus_body": {"api_field": "syllabus_body", "editable": True},
    "public_syllabus": {"api_field": "public_syllabus", "editable": True},
    "public_syllabus_to_auth": {"api_field": "public_syllabus_to_auth", "editable": True},

    # Dates
    "start_at": {"api_field": "start_at", "editable": True},
    "end_at": {"api_field": "end_at", "editable": True},
    "time_zone": {"api_field": "time_zone", "editable": True},
    "restrict_enrollments_to_course_dates": {"api_field": "restrict_enrollments_to_course_dates", "editable": True},

    # Visibility
    "is_public": {"api_field": "is_public", "editable": True},
    "is_public_to_auth_users": {"api_field": "is_public_to_auth_users", "editable": True},
    "license": {"api_field": "license", "editable": True},

    # Grading
    "hide_final_grades": {"api_field": "hide_final_grades", "editable": True},
    "apply_assignment_group_weights": {"api_field": "apply_assignment_group_weights", "editable": True},

    # Read-only info (for reference)
    "id": {"api_field": "id", "editable": False},
    "account_id": {"api_field": "account_id", "editable": False},
    "uuid": {"api_field": "uuid", "editable": False},
    "workflow_state": {"api_field": "workflow_state", "editable": False},
    "created_at": {"api_field": "created_at", "editable": False},
}


def pull_course(
    course_id: str,
    directory: str,
    client: Optional[CanvasClient] = None,
    interactive: bool = True
) -> Dict[str, Any]:
    """
    Pull course settings from Canvas to course.yaml.

    Args:
        course_id: Canvas course ID
        directory: Local directory path
        client: Optional CanvasClient instance
        interactive: If True, prompt on conflicts

    Returns:
        Dict with pull results including any conflicts
    """
    canvas = client or get_canvas_client()
    course = canvas.get_course(course_id)

    dir_path = Path(directory)
    course_file = dir_path / COURSE_FILE

    # Get current Canvas settings
    canvas_settings = _get_course_settings(course)

    # Get front page if default_view is wiki
    try:
        front_page = course.show_front_page()
        canvas_settings["front_page"] = front_page.url
    except Exception:
        canvas_settings["front_page"] = None

    # Get assignment groups
    assignment_groups_list = list_assignment_groups(course_id, client=canvas)

    # Check for existing local file
    local_settings = {}
    conflicts = []

    if course_file.exists():
        with open(course_file, encoding="utf-8") as f:
            local_data = yaml.safe_load(f) or {}
            local_settings = local_data.get("settings", {})

        # Detect conflicts (fields that differ)
        for key in SYNCABLE_SETTINGS:
            if key in local_settings and key in canvas_settings:
                local_val = local_settings[key]
                canvas_val = canvas_settings[key]
                if local_val != canvas_val and local_val is not None:
                    conflicts.append({
                        "field": key,
                        "local": local_val,
                        "canvas": canvas_val
                    })

    # Build course.yaml data
    yaml_data = {
        "canvas": {
            "course_id": str(course_id),
            "domain": canvas.domain,
        },
        "settings": canvas_settings,
        "assignment_groups": assignment_groups_list,
        "sync": {
            "last_pull": datetime.utcnow().isoformat() + "Z",
        }
    }

    # Write to file
    with open(course_file, "w", encoding="utf-8") as f:
        yaml.dump(yaml_data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    logger.info(f"Pulled course settings to {course_file}")

    return {
        "file": str(course_file),
        "settings_count": len(canvas_settings),
        "conflicts": conflicts,
    }


def push_course(
    directory: str,
    client: Optional[CanvasClient] = None,
    dry_run: bool = False
) -> Dict[str, Any]:
    """
    Push course.yaml settings to Canvas.

    Args:
        directory: Local directory path
        client: Optional CanvasClient instance
        dry_run: If True, show what would change without applying

    Returns:
        Dict with push results
    """
    dir_path = Path(directory)
    course_file = dir_path / COURSE_FILE

    if not course_file.exists():
        return {"error": f"No {COURSE_FILE} found in {directory}"}

    with open(course_file, encoding="utf-8") as f:
        yaml_data = yaml.safe_load(f) or {}

    canvas_config = yaml_data.get("canvas", {})
    course_id = canvas_config.get("course_id")

    if not course_id:
        return {"error": "No course_id in course.yaml"}

    canvas = client or get_canvas_client()
    course = canvas.get_course(course_id)

    local_settings = yaml_data.get("settings", {})
    current_settings = _get_course_settings(course)

    # Determine what needs to be updated
    updates = {}
    changes = []

    for key, config in SYNCABLE_SETTINGS.items():
        if not config["editable"]:
            continue
        if key not in local_settings:
            continue

        local_val = local_settings[key]
        current_val = current_settings.get(key)

        if local_val != current_val:
            if key == "front_page":
                # Special handling for front page
                changes.append({
                    "field": key,
                    "from": current_val,
                    "to": local_val
                })
            elif config["api_field"]:
                updates[f"course[{config['api_field']}]"] = local_val
                changes.append({
                    "field": key,
                    "from": current_val,
                    "to": local_val
                })

    if dry_run:
        return {
            "dry_run": True,
            "changes": changes,
        }

    # Apply updates
    errors = []

    if updates:
        try:
            course.update(**{k.replace("course[", "").replace("]", ""): v
                           for k, v in updates.items()})
        except Exception as e:
            errors.append(f"Failed to update course settings: {e}")

    # Handle front page separately
    if "front_page" in local_settings and local_settings["front_page"]:
        try:
            course.edit_front_page(wiki_page={"url": local_settings["front_page"]})
        except Exception as e:
            errors.append(f"Failed to set front page: {e}")

    # Update sync timestamp
    yaml_data["sync"]["last_push"] = datetime.utcnow().isoformat() + "Z"
    with open(course_file, "w", encoding="utf-8") as f:
        yaml.dump(yaml_data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    logger.info(f"Pushed {len(changes)} changes to Canvas")

    return {
        "changes": changes,
        "errors": errors,
    }


def course_status(
    directory: str,
    client: Optional[CanvasClient] = None
) -> Dict[str, Any]:
    """
    Compare local course.yaml with Canvas settings.

    Args:
        directory: Local directory path
        client: Optional CanvasClient instance

    Returns:
        Dict with status comparison
    """
    dir_path = Path(directory)
    course_file = dir_path / COURSE_FILE

    if not course_file.exists():
        return {"error": f"No {COURSE_FILE} found", "has_local": False}

    with open(course_file, encoding="utf-8") as f:
        yaml_data = yaml.safe_load(f) or {}

    canvas_config = yaml_data.get("canvas", {})
    course_id = canvas_config.get("course_id")

    if not course_id:
        return {"error": "No course_id in course.yaml"}

    canvas = client or get_canvas_client()
    course = canvas.get_course(course_id)

    local_settings = yaml_data.get("settings", {})
    canvas_settings = _get_course_settings(course)

    # Get front page
    try:
        front_page = course.show_front_page()
        canvas_settings["front_page"] = front_page.url
    except Exception:
        canvas_settings["front_page"] = None

    # Compare
    synced = []
    local_differs = []
    canvas_only = []

    all_keys = set(local_settings.keys()) | set(canvas_settings.keys())

    for key in all_keys:
        local_val = local_settings.get(key)
        canvas_val = canvas_settings.get(key)

        if local_val == canvas_val:
            synced.append({"field": key, "value": local_val})
        elif key in local_settings and key in canvas_settings:
            local_differs.append({
                "field": key,
                "local": local_val,
                "canvas": canvas_val
            })
        elif key not in local_settings:
            canvas_only.append({"field": key, "value": canvas_val})

    return {
        "synced": synced,
        "differs": local_differs,
        "canvas_only": canvas_only,
        "summary": {
            "synced_count": len(synced),
            "differs_count": len(local_differs),
            "canvas_only_count": len(canvas_only),
        }
    }


def _get_course_settings(course) -> Dict[str, Any]:
    """Extract syncable settings from a course object."""
    settings = {}

    for key, config in SYNCABLE_SETTINGS.items():
        api_field = config["api_field"]
        if api_field:
            val = getattr(course, api_field, None)
            # Convert datetime objects to ISO strings
            if hasattr(val, "isoformat"):
                val = val.isoformat()
            elif isinstance(val, str) and val.endswith("+00:00"):
                # Already ISO format
                pass
            settings[key] = val

    return settings


# ============== Link Transformation ==============


def transform_links_to_local(
    content: str,
    course_id: str,
    domain: str
) -> str:
    """
    Transform Canvas internal links to local markdown links.

    Converts:
      /courses/123/pages/my-page -> ./my-page.md
      https://canvas.edu/courses/123/pages/my-page -> ./my-page.md
      /courses/123/files/456/download -> ./files/456 (preserved)
    """
    # Full URL pattern
    full_url_pattern = rf'https?://{re.escape(domain)}/courses/{course_id}/pages/([a-zA-Z0-9_-]+)'
    content = re.sub(full_url_pattern, r'./\1.md', content)

    # Relative URL pattern
    relative_pattern = rf'/courses/{course_id}/pages/([a-zA-Z0-9_-]+)'
    content = re.sub(relative_pattern, r'./\1.md', content)

    # Handle wiki page links in markdown format
    # [text](/courses/123/pages/slug) -> [text](./slug.md)
    md_link_pattern = rf'\]\(/courses/{course_id}/pages/([a-zA-Z0-9_-]+)\)'
    content = re.sub(md_link_pattern, r'](./\1.md)', content)

    return content


def transform_links_to_canvas(
    content: str,
    course_id: str,
    domain: str
) -> str:
    """
    Transform local markdown links to Canvas internal links.

    Converts:
      ./my-page.md -> /courses/123/pages/my-page
      [text](./my-page.md) -> [text](/courses/123/pages/my-page)
      [text](my-page.md) -> [text](/courses/123/pages/my-page)
      [text](my-page) -> [text](/courses/123/pages/my-page)
    """
    # Pattern for markdown links to .md files
    # Handles ./page.md, page.md, and just page (without extension)
    def replace_link(match):
        link_text = match.group(1)
        link_target = match.group(2)

        # Remove ./ prefix and .md suffix
        page_url = link_target.lstrip('./').removesuffix('.md')

        # Skip external links and anchors
        if page_url.startswith('http') or page_url.startswith('#'):
            return match.group(0)

        # Skip file links
        if '/' in page_url and not page_url.startswith('.'):
            return match.group(0)

        return f'[{link_text}](/courses/{course_id}/pages/{page_url})'

    # Match markdown links: [text](target)
    # But not images: ![text](target)
    link_pattern = r'(?<!!)\[([^\]]+)\]\((\./[^)]+\.md|[^/)][^)]*\.md|[a-zA-Z0-9_-]+)\)'
    content = re.sub(link_pattern, replace_link, content)

    return content


def init_course(
    course_id: str,
    directory: str,
    client: Optional[CanvasClient] = None
) -> Dict[str, Any]:
    """
    Initialize a directory for a Canvas course.

    Creates course.yaml and necessary directories.

    Args:
        course_id: Canvas course ID
        directory: Local directory path
        client: Optional CanvasClient instance

    Returns:
        Dict with initialization results
    """
    canvas = client or get_canvas_client()
    course = canvas.get_course(course_id)

    dir_path = Path(directory)
    dir_path.mkdir(parents=True, exist_ok=True)

    # Create subdirectories
    (dir_path / "pages").mkdir(exist_ok=True)

    # Pull initial course settings
    result = pull_course(course_id, directory, client=canvas)

    # Create .gitignore if not exists
    gitignore = dir_path / ".gitignore"
    if not gitignore.exists():
        gitignore.write_text(".env\n")

    logger.info(f"Initialized course directory at {directory}")

    return {
        "directory": str(dir_path),
        "course_id": course_id,
        "course_name": course.name,
        "files_created": [
            str(dir_path / COURSE_FILE),
            str(dir_path / "pages"),
            str(gitignore),
        ]
    }
