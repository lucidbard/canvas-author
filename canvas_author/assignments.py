"""
Assignments Module

Operations for Canvas assignments and submissions.
"""

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from canvasapi.exceptions import ResourceDoesNotExist, CanvasException

from .client import get_canvas_client, CanvasClient
from .exceptions import ResourceNotFoundError

logger = logging.getLogger("canvas_author.assignments")

# Fields to include in assignment responses
ASSIGNMENT_FIELDS = [
    "id", "name", "description", "due_at", "unlock_at", "lock_at",
    "points_possible", "grading_type", "submission_types", "published",
    "html_url", "has_submitted_submissions", "needs_grading_count",
    "peer_reviews", "automatic_peer_reviews", "workflow_state",
]


def list_courses(
    enrollment_type: str = "teacher",
    enrollment_state: str = "active",
    client: Optional[CanvasClient] = None
) -> List[Dict[str, Any]]:
    """
    List courses for the current user.

    Args:
        enrollment_type: Filter by enrollment type ('teacher', 'student', etc.)
        enrollment_state: Filter by state ('active', 'all')
        client: Optional CanvasClient instance

    Returns:
        List of course dicts with keys: id, name, course_code, workflow_state
    """
    canvas = client or get_canvas_client()
    all_courses = list(canvas.get_courses(
        enrollment_type=enrollment_type,
        include=["favorites"]
    ))

    if enrollment_state == "active":
        now = datetime.now(timezone.utc)
        active_courses = []

        for course in all_courses:
            start_at = getattr(course, "start_at", None)
            end_at = getattr(course, "end_at", None)

            course_started = True
            course_ended = False

            if start_at:
                try:
                    start_date = datetime.fromisoformat(start_at.replace('Z', '+00:00'))
                    course_started = now >= start_date
                except (ValueError, TypeError):
                    pass

            if end_at:
                try:
                    end_date = datetime.fromisoformat(end_at.replace('Z', '+00:00'))
                    course_ended = now > end_date
                except (ValueError, TypeError):
                    pass

            if course_started and not course_ended:
                active_courses.append(course)

        courses = active_courses
    else:
        courses = all_courses

    result = []
    for course in courses:
        result.append({
            "id": str(course.id),
            "name": getattr(course, "name", f"Course {course.id}"),
            "course_code": getattr(course, "course_code", ""),
            "workflow_state": getattr(course, "workflow_state", ""),
            "start_at": getattr(course, "start_at", None),
            "end_at": getattr(course, "end_at", None),
        })

    logger.info(f"Listed {len(result)} courses")
    return result


def list_assignments(
    course_id: str,
    client: Optional[CanvasClient] = None
) -> List[Dict[str, Any]]:
    """
    List all assignments in a course.

    Args:
        course_id: Canvas course ID
        client: Optional CanvasClient instance

    Returns:
        List of assignment dicts
    """
    canvas = client or get_canvas_client()
    course = canvas.get_course(course_id)
    assignments = list(course.get_assignments())

    result = []
    for assignment in assignments:
        assignment_data = {"id": str(assignment.id)}
        for field in ASSIGNMENT_FIELDS:
            if hasattr(assignment, field):
                value = getattr(assignment, field)
                assignment_data[field] = str(value) if field.endswith("_at") and value else value
        result.append(assignment_data)

    logger.info(f"Listed {len(result)} assignments for course {course_id}")
    return result


def get_assignment(
    course_id: str,
    assignment_id: str,
    client: Optional[CanvasClient] = None
) -> Dict[str, Any]:
    """
    Get details for a specific assignment.

    Args:
        course_id: Canvas course ID
        assignment_id: Canvas assignment ID
        client: Optional CanvasClient instance

    Returns:
        Assignment data dict
    """
    canvas = client or get_canvas_client()
    course = canvas.get_course(course_id)

    try:
        assignment = course.get_assignment(assignment_id)
    except ResourceDoesNotExist:
        raise ResourceNotFoundError("assignment", assignment_id)

    result = {"id": str(assignment.id)}
    for field in ASSIGNMENT_FIELDS:
        if hasattr(assignment, field):
            value = getattr(assignment, field)
            result[field] = str(value) if field.endswith("_at") and value else value

    # Include rubric info if available
    if hasattr(assignment, 'rubric_settings') and assignment.rubric_settings:
        result["has_rubric"] = True
        result["rubric_settings"] = assignment.rubric_settings
    else:
        result["has_rubric"] = False

    # Include discussion topic info if available
    if hasattr(assignment, 'discussion_topic') and assignment.discussion_topic:
        result["is_discussion"] = True
        result["discussion_topic_id"] = assignment.discussion_topic.get('id')
    else:
        result["is_discussion"] = False

    logger.info(f"Retrieved assignment {assignment_id} from course {course_id}")
    return result


def list_submissions(
    course_id: str,
    assignment_id: str,
    include_user: bool = True,
    include_rubric: bool = True,
    client: Optional[CanvasClient] = None
) -> List[Dict[str, Any]]:
    """
    List all submissions for an assignment.

    Args:
        course_id: Canvas course ID
        assignment_id: Canvas assignment ID
        include_user: Include user info in response
        include_rubric: Include rubric assessment in response
        client: Optional CanvasClient instance

    Returns:
        List of submission dicts
    """
    canvas = client or get_canvas_client()
    course = canvas.get_course(course_id)

    try:
        assignment = course.get_assignment(assignment_id)
    except ResourceDoesNotExist:
        raise ResourceNotFoundError("assignment", assignment_id)

    include = []
    if include_user:
        include.append("user")
    if include_rubric:
        include.extend(["submission_comments", "rubric_assessment"])

    submissions = assignment.get_submissions(include=include)

    result = []
    for submission in submissions:
        sub_data = {
            "id": str(submission.id),
            "user_id": str(submission.user_id),
            "submitted_at": str(getattr(submission, "submitted_at", None)),
            "grade": getattr(submission, "grade", None),
            "score": getattr(submission, "score", None),
            "workflow_state": getattr(submission, "workflow_state", ""),
            "late": getattr(submission, "late", False),
            "missing": getattr(submission, "missing", False),
            "attempt": getattr(submission, "attempt", None),
        }

        if include_user and hasattr(submission, "user"):
            user = submission.user
            sub_data["user"] = {
                "id": str(user.get("id", "")),
                "name": user.get("name", "Unknown"),
                "sortable_name": user.get("sortable_name", ""),
            }

        if include_rubric and hasattr(submission, "rubric_assessment"):
            sub_data["rubric_assessment"] = submission.rubric_assessment

        # Include attachment info
        if hasattr(submission, "attachments") and submission.attachments:
            sub_data["attachments"] = [
                {
                    "id": str(att.get("id", "")),
                    "filename": att.get("filename", ""),
                    "display_name": att.get("display_name", ""),
                    "content_type": att.get("content-type", ""),
                    "url": att.get("url", ""),
                }
                for att in submission.attachments
            ]

        result.append(sub_data)

    logger.info(f"Listed {len(result)} submissions for assignment {assignment_id}")
    return result


def get_submission(
    course_id: str,
    assignment_id: str,
    user_id: str,
    include_rubric: bool = True,
    client: Optional[CanvasClient] = None
) -> Dict[str, Any]:
    """
    Get a specific submission.

    Args:
        course_id: Canvas course ID
        assignment_id: Canvas assignment ID
        user_id: Student user ID
        include_rubric: Include rubric assessment in response
        client: Optional CanvasClient instance

    Returns:
        Submission data dict
    """
    canvas = client or get_canvas_client()
    course = canvas.get_course(course_id)

    try:
        assignment = course.get_assignment(assignment_id)
    except ResourceDoesNotExist:
        raise ResourceNotFoundError("assignment", assignment_id)

    include = ["user", "submission_comments"]
    if include_rubric:
        include.append("rubric_assessment")

    try:
        submission = assignment.get_submission(user_id, include=include)
    except ResourceDoesNotExist:
        raise ResourceNotFoundError("submission", user_id, f"Submission not found for user {user_id}")

    result = {
        "id": str(submission.id),
        "user_id": str(submission.user_id),
        "submitted_at": str(getattr(submission, "submitted_at", None)),
        "grade": getattr(submission, "grade", None),
        "score": getattr(submission, "score", None),
        "workflow_state": getattr(submission, "workflow_state", ""),
        "late": getattr(submission, "late", False),
        "missing": getattr(submission, "missing", False),
        "attempt": getattr(submission, "attempt", None),
    }

    if hasattr(submission, "user"):
        user = submission.user
        result["user"] = {
            "id": str(user.get("id", "")),
            "name": user.get("name", "Unknown"),
            "sortable_name": user.get("sortable_name", ""),
        }

    if include_rubric and hasattr(submission, "rubric_assessment"):
        result["rubric_assessment"] = submission.rubric_assessment

    if hasattr(submission, "submission_comments"):
        result["comments"] = submission.submission_comments

    logger.info(f"Retrieved submission for user {user_id} on assignment {assignment_id}")
    return result
