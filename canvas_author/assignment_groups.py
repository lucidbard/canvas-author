"""
Assignment Groups Module

Operations for Canvas assignment groups.
"""

import logging
from typing import List, Dict, Any, Optional
from canvasapi.exceptions import ResourceDoesNotExist

from canvas_common import get_canvas_client, CanvasClient
from canvas_common import ResourceNotFoundError

logger = logging.getLogger("canvas_author.assignment_groups")

# Fields to include in assignment group responses
ASSIGNMENT_GROUP_FIELDS = [
    "id", "name", "position", "group_weight", "rules", "course_id"
]


def list_assignment_groups(
    course_id: str,
    client: Optional[CanvasClient] = None
) -> List[Dict[str, Any]]:
    """
    List all assignment groups in a course.

    Args:
        course_id: Canvas course ID
        client: Optional CanvasClient instance

    Returns:
        List of assignment group dicts
    """
    canvas = client or get_canvas_client()
    course = canvas.get_course(course_id)
    assignment_groups = list(course.get_assignment_groups())

    result = []
    for group in assignment_groups:
        group_data = {"id": str(group.id)}
        for field in ASSIGNMENT_GROUP_FIELDS:
            if hasattr(group, field):
                value = getattr(group, field)
                group_data[field] = value
        result.append(group_data)

    logger.info(f"Listed {len(result)} assignment groups for course {course_id}")
    return result


def get_assignment_group(
    course_id: str,
    group_id: str,
    client: Optional[CanvasClient] = None
) -> Dict[str, Any]:
    """
    Get details for a specific assignment group.

    Args:
        course_id: Canvas course ID
        group_id: Canvas assignment group ID
        client: Optional CanvasClient instance

    Returns:
        Assignment group data dict
    """
    canvas = client or get_canvas_client()
    course = canvas.get_course(course_id)

    try:
        group = course.get_assignment_group(group_id)
    except ResourceDoesNotExist:
        raise ResourceNotFoundError("assignment_group", group_id)

    result = {"id": str(group.id)}
    for field in ASSIGNMENT_GROUP_FIELDS:
        if hasattr(group, field):
            value = getattr(group, field)
            result[field] = value

    logger.info(f"Retrieved assignment group {group_id} from course {course_id}")
    return result
