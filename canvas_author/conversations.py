"""
Conversations Module

Send messages to students via Canvas Conversations API.
"""

import logging
from typing import List, Dict, Any, Optional, Set
from canvasapi.exceptions import CanvasException

from canvas_common import get_canvas_client, CanvasClient
from canvas_common import ResourceNotFoundError

logger = logging.getLogger("canvas_author.conversations")


def get_student_enrollments(
    course_id: str,
    client: Optional[CanvasClient] = None
) -> List[Dict[str, Any]]:
    """
    Get all student enrollments for a course.

    Args:
        course_id: Canvas course ID
        client: Optional CanvasClient instance

    Returns:
        List of enrollment dicts with user_id, user info
    """
    canvas = client or get_canvas_client()
    course = canvas.get_course(course_id)

    enrollments = []
    for enrollment in course.get_enrollments(type=["StudentEnrollment"]):
        enrollments.append({
            "user_id": enrollment.user_id,
            "user": {
                "id": enrollment.user_id,
                "name": getattr(enrollment.user, "name", f"User {enrollment.user_id}"),
                "sortable_name": getattr(enrollment.user, "sortable_name", ""),
            }
        })

    logger.info(f"Found {len(enrollments)} student enrollments in course {course_id}")
    return enrollments


def get_submitted_user_ids(
    course_id: str,
    assignment_id: str,
    client: Optional[CanvasClient] = None
) -> Set[int]:
    """
    Get user IDs of all students who have submitted an assignment.

    Args:
        course_id: Canvas course ID
        assignment_id: Canvas assignment ID
        client: Optional CanvasClient instance

    Returns:
        Set of user IDs who have submitted
    """
    canvas = client or get_canvas_client()
    course = canvas.get_course(course_id)
    assignment = course.get_assignment(assignment_id)

    submitted_ids = set()
    for submission in assignment.get_submissions():
        # Consider submitted if workflow_state is 'submitted' or 'graded'
        if submission.workflow_state in ['submitted', 'graded', 'pending_review']:
            submitted_ids.add(submission.user_id)

    logger.info(f"Found {len(submitted_ids)} submissions for assignment {assignment_id}")
    return submitted_ids


def send_conversation(
    recipient_ids: List[int],
    subject: str,
    body: str,
    context_code: str,
    client: Optional[CanvasClient] = None
) -> Dict[str, Any]:
    """
    Send a conversation message to multiple recipients.

    Args:
        recipient_ids: List of Canvas user IDs
        subject: Message subject
        body: Message body (HTML or plain text)
        context_code: Context code (e.g., 'course_1234')
        client: Optional CanvasClient instance

    Returns:
        Dict with conversation data

    Raises:
        CanvasException: If message fails to send
    """
    canvas = client or get_canvas_client()

    try:
        # Use the Canvas API directly via requests
        # canvasapi doesn't have a clean wrapper for conversations
        api_url = f"https://{canvas.domain}/api/v1/conversations"
        headers = {"Authorization": f"Bearer {canvas.token}"}

        # Canvas expects recipients as array of IDs (strings)
        data = {
            "recipients[]": [str(uid) for uid in recipient_ids],
            "subject": subject,
            "body": body,
            "context_code": context_code,
            "group_conversation": False,  # Individual messages to each recipient
        }

        import requests
        response = requests.post(api_url, headers=headers, data=data)
        response.raise_for_status()

        result = response.json()
        logger.info(f"Sent conversation to {len(recipient_ids)} recipients")
        return result

    except Exception as e:
        logger.error(f"Failed to send conversation: {e}")
        raise CanvasException(f"Failed to send message: {e}")


def message_non_submitters(
    course_id: str,
    assignment_id: str,
    subject: str,
    message: str,
    anonymize: bool = True,
    client: Optional[CanvasClient] = None
) -> Dict[str, Any]:
    """
    Send a message to all students who haven't submitted an assignment.

    Args:
        course_id: Canvas course ID
        assignment_id: Canvas assignment ID
        subject: Message subject
        message: Message body (can include HTML)
        anonymize: Anonymize student names in response (default: True for AI privacy)
        client: Optional CanvasClient instance

    Returns:
        Dict with:
            - message_sent: bool
            - recipient_count: int
            - recipients: List of user info (anonymized if anonymize=True)
            - assignment_name: str
            - total_students: int
            - submitted_count: int
    """
    canvas = client or get_canvas_client()
    course = canvas.get_course(course_id)
    assignment = course.get_assignment(assignment_id)

    # Get all student enrollments
    enrollments = get_student_enrollments(course_id, canvas)
    all_student_ids = {e["user_id"] for e in enrollments}

    # Get submitted user IDs
    submitted_ids = get_submitted_user_ids(course_id, assignment_id, canvas)

    # Find non-submitters
    non_submitter_ids = all_student_ids - submitted_ids

    if not non_submitter_ids:
        logger.info(f"No non-submitters found for assignment {assignment_id}")
        return {
            "message_sent": False,
            "recipient_count": 0,
            "recipients": [],
            "assignment_name": assignment.name,
            "total_students": len(all_student_ids),
            "submitted_count": len(submitted_ids),
            "message": "All students have submitted"
        }

    # Send message
    context_code = f"course_{course_id}"
    conversation = send_conversation(
        recipient_ids=list(non_submitter_ids),
        subject=subject,
        body=message,
        context_code=context_code,
        client=canvas
    )

    # Build recipient list
    recipient_list = []
    for enrollment in enrollments:
        if enrollment["user_id"] in non_submitter_ids:
            if anonymize:
                # Anonymize for AI privacy
                recipient_list.append({
                    "id": f"Student {len(recipient_list) + 1}",
                    "name": f"Student {len(recipient_list) + 1}"
                })
            else:
                recipient_list.append({
                    "id": enrollment["user_id"],
                    "name": enrollment["user"]["name"]
                })

    return {
        "message_sent": True,
        "recipient_count": len(non_submitter_ids),
        "recipients": recipient_list,
        "assignment_name": assignment.name,
        "total_students": len(all_student_ids),
        "submitted_count": len(submitted_ids),
        "conversation_id": conversation[0].get("id") if conversation else None
    }
