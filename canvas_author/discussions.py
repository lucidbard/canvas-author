"""
Discussions Module

Operations for Canvas discussion topics and posts.
"""

import logging
from typing import List, Dict, Any, Optional
from canvasapi.exceptions import ResourceDoesNotExist, CanvasException

from .client import get_canvas_client, CanvasClient
from .exceptions import ResourceNotFoundError
from .pandoc import html_to_markdown

logger = logging.getLogger("canvas_author.discussions")


def list_discussions(
    course_id: str,
    client: Optional[CanvasClient] = None
) -> List[Dict[str, Any]]:
    """
    List all discussion topics in a course.

    Args:
        course_id: Canvas course ID
        client: Optional CanvasClient instance

    Returns:
        List of discussion topic dicts
    """
    canvas = client or get_canvas_client()
    course = canvas.get_course(course_id)
    discussions = course.get_discussion_topics()

    result = []
    for topic in discussions:
        result.append({
            "id": str(topic.id),
            "title": topic.title,
            "message": getattr(topic, "message", None),
            "posted_at": str(getattr(topic, "posted_at", None)),
            "discussion_type": getattr(topic, "discussion_type", ""),
            "published": getattr(topic, "published", True),
            "locked": getattr(topic, "locked", False),
            "pinned": getattr(topic, "pinned", False),
            "assignment_id": str(getattr(topic, "assignment_id", "")) if getattr(topic, "assignment_id", None) else None,
            "html_url": getattr(topic, "html_url", ""),
        })

    logger.info(f"Listed {len(result)} discussion topics for course {course_id}")
    return result


def list_discussion_assignments(
    course_id: str,
    client: Optional[CanvasClient] = None
) -> List[Dict[str, Any]]:
    """
    List all graded discussion assignments in a course.

    Args:
        course_id: Canvas course ID
        client: Optional CanvasClient instance

    Returns:
        List of discussion assignment dicts with topic info
    """
    canvas = client or get_canvas_client()
    course = canvas.get_course(course_id)
    assignments = course.get_assignments()

    result = []
    for assignment in assignments:
        if hasattr(assignment, 'discussion_topic') and assignment.discussion_topic:
            result.append({
                "id": str(assignment.id),
                "name": assignment.name,
                "description": getattr(assignment, "description", ""),
                "topic_id": str(assignment.discussion_topic.get('id')),
                "points_possible": getattr(assignment, "points_possible", 0),
                "due_at": str(getattr(assignment, "due_at", None)),
                "published": getattr(assignment, "published", True),
            })

    logger.info(f"Found {len(result)} discussion assignments in course {course_id}")
    return result


def get_discussion(
    course_id: str,
    discussion_id: str,
    as_markdown: bool = True,
    client: Optional[CanvasClient] = None
) -> Dict[str, Any]:
    """
    Get a discussion topic by ID.

    Args:
        course_id: Canvas course ID
        discussion_id: Discussion topic ID
        as_markdown: Convert HTML message to markdown
        client: Optional CanvasClient instance

    Returns:
        Discussion topic data
    """
    canvas = client or get_canvas_client()
    course = canvas.get_course(course_id)

    try:
        topic = course.get_discussion_topic(discussion_id)
    except ResourceDoesNotExist:
        raise ResourceNotFoundError("discussion", discussion_id)

    message = getattr(topic, "message", "") or ""
    if as_markdown and message:
        message = html_to_markdown(message)

    return {
        "id": str(topic.id),
        "title": topic.title,
        "message": message,
        "posted_at": str(getattr(topic, "posted_at", None)),
        "discussion_type": getattr(topic, "discussion_type", ""),
        "published": getattr(topic, "published", True),
        "locked": getattr(topic, "locked", False),
        "pinned": getattr(topic, "pinned", False),
        "assignment_id": str(getattr(topic, "assignment_id", "")) if getattr(topic, "assignment_id", None) else None,
        "html_url": getattr(topic, "html_url", ""),
        "user_id": str(getattr(topic, "user_id", "")),
    }


def get_discussion_posts(
    course_id: str,
    discussion_id: str,
    as_markdown: bool = True,
    client: Optional[CanvasClient] = None
) -> Dict[str, Any]:
    """
    Get all posts (entries and replies) for a discussion topic.

    Args:
        course_id: Canvas course ID
        discussion_id: Discussion topic ID
        as_markdown: Convert HTML messages to markdown
        client: Optional CanvasClient instance

    Returns:
        Dict with topic info and entries with replies
    """
    canvas = client or get_canvas_client()
    course = canvas.get_course(course_id)

    try:
        discussion = course.get_discussion_topic(discussion_id)
    except ResourceDoesNotExist:
        raise ValueError(f"Discussion topic not found: {discussion_id}")

    # Get topic message
    topic_message = getattr(discussion, "message", "") or ""
    if as_markdown and topic_message:
        topic_message = html_to_markdown(topic_message)

    # Build result structure
    result = {
        "topic": {
            "id": str(discussion.id),
            "title": discussion.title,
            "message": topic_message,
            "posted_at": str(getattr(discussion, "posted_at", None)),
            "author_id": str(getattr(discussion, "user_id", "")),
        },
        "entries": []
    }

    # Get all entries (top-level posts)
    try:
        entries = discussion.get_topic_entries()

        for entry in entries:
            message = getattr(entry, "message", "") or ""
            if as_markdown and message:
                message = html_to_markdown(message)

            entry_data = {
                "id": str(entry.id),
                "message": message,
                "user_id": str(entry.user_id),
                "created_at": str(entry.created_at),
                "updated_at": str(getattr(entry, "updated_at", None)),
                "replies": []
            }

            # Get replies for this entry
            try:
                replies = entry.get_replies()
                for reply in replies:
                    reply_message = getattr(reply, "message", "") or ""
                    if as_markdown and reply_message:
                        reply_message = html_to_markdown(reply_message)

                    entry_data["replies"].append({
                        "id": str(reply.id),
                        "message": reply_message,
                        "user_id": str(reply.user_id),
                        "created_at": str(reply.created_at),
                        "updated_at": str(getattr(reply, "updated_at", None)),
                    })
            except Exception as e:
                logger.warning(f"Error getting replies for entry {entry.id}: {e}")

            result["entries"].append(entry_data)

    except Exception as e:
        logger.error(f"Error getting discussion entries: {e}")

    logger.info(f"Retrieved {len(result['entries'])} entries for discussion {discussion_id}")
    return result


def get_posts_by_user(
    course_id: str,
    discussion_id: str,
    as_markdown: bool = True,
    client: Optional[CanvasClient] = None
) -> Dict[str, Dict[str, Any]]:
    """
    Get discussion posts organized by user.

    Args:
        course_id: Canvas course ID
        discussion_id: Discussion topic ID
        as_markdown: Convert HTML messages to markdown
        client: Optional CanvasClient instance

    Returns:
        Dict mapping user_id to their posts and replies
    """
    posts_data = get_discussion_posts(course_id, discussion_id, as_markdown, client)

    users = {}

    for entry in posts_data["entries"]:
        user_id = entry["user_id"]
        if user_id not in users:
            users[user_id] = {"posts": [], "replies": []}

        users[user_id]["posts"].append({
            "id": entry["id"],
            "message": entry["message"],
            "created_at": entry["created_at"],
        })

        # Process replies
        for reply in entry["replies"]:
            reply_user_id = reply["user_id"]
            if reply_user_id not in users:
                users[reply_user_id] = {"posts": [], "replies": []}

            users[reply_user_id]["replies"].append({
                "id": reply["id"],
                "message": reply["message"],
                "created_at": reply["created_at"],
                "in_reply_to_entry_id": entry["id"],
            })

    return users
