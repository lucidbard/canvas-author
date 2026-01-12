"""
Discussions Module

Operations for Canvas discussion topics and posts.
"""

import logging
from typing import List, Dict, Any, Optional
from canvasapi.exceptions import ResourceDoesNotExist, CanvasException

from .client import get_canvas_client, CanvasClient
from .exceptions import ResourceNotFoundError
from .pandoc import html_to_markdown, markdown_to_html, is_pandoc_available

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


def create_discussion(
    course_id: str,
    title: str,
    message: str,
    discussion_type: str = 'threaded',
    published: bool = True,
    assignment: Optional[Dict[str, Any]] = None,
    require_initial_post: bool = False,
    is_announcement: bool = False,
    delayed_post_at: Optional[str] = None,
    client: Optional[CanvasClient] = None
) -> Dict[str, Any]:
    """
    Create a new discussion topic with optional assignment.

    Args:
        course_id: Canvas course ID
        title: Discussion title
        message: Discussion message (HTML or markdown)
        discussion_type: Type of discussion ('threaded' or 'side_comment')
        published: Whether to publish immediately
        assignment: Optional assignment configuration with:
            - points_possible: Total points
            - assignment_group_id: Assignment group ID
            - due_at: Due date (ISO 8601 format)
            - unlock_at: Unlock date
            - lock_at: Lock date
            - grading_type: Grading type (default: 'points')
            - checkpoints: Optional list of checkpoint dicts for checkpointed discussions:
                [{
                    'tag': 'reply_to_topic',
                    'points_possible': 6.0,
                    'due_at': '2026-01-19T04:59:59Z'
                }, {
                    'tag': 'reply_to_entry',
                    'points_possible': 4.0,
                    'due_at': '2026-01-26T04:59:59Z'
                }]
            - reply_to_entry_required_count: Required number of peer replies (for checkpoints)
        require_initial_post: Students must post before seeing others' posts
        is_announcement: Create as announcement instead of discussion
        delayed_post_at: Schedule for later posting (ISO 8601 format)
        client: Optional CanvasClient instance

    Returns:
        Dict with discussion topic data including:
            - id: Discussion topic ID
            - title: Topic title
            - assignment_id: Assignment ID (if graded)
            - html_url: Canvas URL

    Example:
        # Create simple discussion
        discussion = create_discussion(
            course_id='1503378',
            title='Week 1 Discussion',
            message='<p>Share your thoughts...</p>',
            published=True
        )

        # Create graded checkpointed discussion
        discussion = create_discussion(
            course_id='1503378',
            title='Week 1 Discussion: AI Development',
            message='<p>Discuss your experience...</p>',
            require_initial_post=True,
            assignment={
                'points_possible': 10,
                'assignment_group_id': 2396054,
                'grading_type': 'points',
                'reply_to_entry_required_count': 2,
                'checkpoints': [
                    {
                        'tag': 'reply_to_topic',
                        'points_possible': 6.0,
                        'due_at': '2026-01-19T04:59:59Z'
                    },
                    {
                        'tag': 'reply_to_entry',
                        'points_possible': 4.0,
                        'due_at': '2026-01-26T04:59:59Z'
                    }
                ]
            }
        )
    """
    canvas = client or get_canvas_client()
    course = canvas.get_course(course_id)

    # Convert markdown to HTML if pandoc is available
    message_html = message
    if is_pandoc_available() and not message.strip().startswith('<'):
        message_html = markdown_to_html(message)

    # Build discussion parameters
    discussion_params = {
        'title': title,
        'message': message_html,
        'discussion_type': discussion_type,
        'published': published,
        'require_initial_post': require_initial_post,
        'is_announcement': is_announcement,
    }

    if delayed_post_at:
        discussion_params['delayed_post_at'] = delayed_post_at

    # Add assignment parameters if this is a graded discussion
    if assignment:
        assignment_params = {
            'points_possible': assignment.get('points_possible', 0),
            'grading_type': assignment.get('grading_type', 'points'),
            'submission_types': ['discussion_topic'],
        }

        if 'assignment_group_id' in assignment:
            assignment_params['assignment_group_id'] = assignment['assignment_group_id']
        if 'due_at' in assignment:
            assignment_params['due_at'] = assignment['due_at']
        if 'unlock_at' in assignment:
            assignment_params['unlock_at'] = assignment['unlock_at']
        if 'lock_at' in assignment:
            assignment_params['lock_at'] = assignment['lock_at']

        # Handle reply requirements for checkpointed discussions
        if 'reply_to_entry_required_count' in assignment:
            discussion_params['reply_to_entry_required_count'] = assignment['reply_to_entry_required_count']

        discussion_params['assignment'] = assignment_params

    # Create the discussion topic
    logger.info(f"Creating discussion '{title}' in course {course_id}")
    topic = course.create_discussion_topic(**discussion_params)

    result = {
        'id': str(topic.id),
        'title': topic.title,
        'discussion_type': getattr(topic, 'discussion_type', discussion_type),
        'published': getattr(topic, 'published', published),
        'assignment_id': str(getattr(topic, 'assignment_id', '')) if getattr(topic, 'assignment_id', None) else None,
        'html_url': getattr(topic, 'html_url', ''),
    }

    # If checkpoints were provided, we need to update the assignment separately
    # Canvas requires checkpoints to be set via assignment update after creation
    if assignment and 'checkpoints' in assignment and result['assignment_id']:
        logger.info(f"Setting checkpoints for assignment {result['assignment_id']}")
        try:
            assignment_obj = course.get_assignment(result['assignment_id'])
            checkpoint_params = {
                'checkpoints': assignment['checkpoints']
            }
            assignment_obj.edit(assignment=checkpoint_params)
            logger.info(f"Checkpoints set successfully for assignment {result['assignment_id']}")
        except Exception as e:
            logger.warning(f"Error setting checkpoints: {e}")

    logger.info(f"Created discussion topic {result['id']}: {title}")
    return result


def update_discussion(
    course_id: str,
    discussion_id: str,
    title: Optional[str] = None,
    message: Optional[str] = None,
    published: Optional[bool] = None,
    pinned: Optional[bool] = None,
    locked: Optional[bool] = None,
    require_initial_post: Optional[bool] = None,
    assignment_updates: Optional[Dict[str, Any]] = None,
    client: Optional[CanvasClient] = None
) -> Dict[str, Any]:
    """
    Update an existing discussion topic.

    Args:
        course_id: Canvas course ID
        discussion_id: Discussion topic ID to update
        title: New title
        message: New message (HTML or markdown)
        published: Publication status
        pinned: Pin to top of discussions
        locked: Lock the discussion
        require_initial_post: Require initial post before seeing others
        assignment_updates: Optional dict with assignment updates:
            - points_possible: Update points
            - due_at: Update due date
            - checkpoints: Update checkpoint configuration
        client: Optional CanvasClient instance

    Returns:
        Dict with updated discussion data
    """
    canvas = client or get_canvas_client()
    course = canvas.get_course(course_id)

    try:
        topic = course.get_discussion_topic(discussion_id)
    except ResourceDoesNotExist:
        raise ResourceNotFoundError("discussion", discussion_id)

    # Build update parameters (only include provided values)
    update_params = {}

    if title is not None:
        update_params['title'] = title
    if message is not None:
        # Convert markdown to HTML if needed
        message_html = message
        if is_pandoc_available() and not message.strip().startswith('<'):
            message_html = markdown_to_html(message)
        update_params['message'] = message_html
    if published is not None:
        update_params['published'] = published
    if pinned is not None:
        update_params['pinned'] = pinned
    if locked is not None:
        update_params['locked'] = locked
    if require_initial_post is not None:
        update_params['require_initial_post'] = require_initial_post

    # Update the discussion topic
    if update_params:
        logger.info(f"Updating discussion {discussion_id} with params: {update_params}")
        topic.update(**update_params)

    # Update assignment if provided and discussion has an assignment
    if assignment_updates and hasattr(topic, 'assignment_id') and topic.assignment_id:
        logger.info(f"Updating assignment {topic.assignment_id}")
        assignment_obj = course.get_assignment(topic.assignment_id)

        assignment_params = {}
        if 'points_possible' in assignment_updates:
            assignment_params['points_possible'] = assignment_updates['points_possible']
        if 'due_at' in assignment_updates:
            assignment_params['due_at'] = assignment_updates['due_at']
        if 'unlock_at' in assignment_updates:
            assignment_params['unlock_at'] = assignment_updates['unlock_at']
        if 'lock_at' in assignment_updates:
            assignment_params['lock_at'] = assignment_updates['lock_at']
        if 'checkpoints' in assignment_updates:
            assignment_params['checkpoints'] = assignment_updates['checkpoints']

        if assignment_params:
            assignment_obj.edit(assignment=assignment_params)
            logger.info(f"Updated assignment {topic.assignment_id}")

    # Refresh topic data
    topic = course.get_discussion_topic(discussion_id)

    return {
        'id': str(topic.id),
        'title': topic.title,
        'published': getattr(topic, 'published', True),
        'locked': getattr(topic, 'locked', False),
        'pinned': getattr(topic, 'pinned', False),
        'assignment_id': str(getattr(topic, 'assignment_id', '')) if getattr(topic, 'assignment_id', None) else None,
        'html_url': getattr(topic, 'html_url', ''),
    }


def delete_discussion(
    course_id: str,
    discussion_id: str,
    client: Optional[CanvasClient] = None
) -> bool:
    """
    Delete a discussion topic.

    Args:
        course_id: Canvas course ID
        discussion_id: Discussion topic ID to delete
        client: Optional CanvasClient instance

    Returns:
        True if deleted successfully

    Raises:
        ResourceNotFoundError: If discussion not found
    """
    canvas = client or get_canvas_client()
    course = canvas.get_course(course_id)

    try:
        topic = course.get_discussion_topic(discussion_id)
    except ResourceDoesNotExist:
        raise ResourceNotFoundError("discussion", discussion_id)

    logger.info(f"Deleting discussion {discussion_id}: {topic.title}")
    topic.delete()
    logger.info(f"Deleted discussion {discussion_id}")

    return True
