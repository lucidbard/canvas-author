"""
Quizzes Module

CRUD operations for Canvas quizzes using the Classic Quizzes API.
"""

import logging
from typing import List, Dict, Any, Optional
from canvasapi.exceptions import ResourceDoesNotExist

from .client import get_canvas_client, CanvasClient
from .exceptions import ResourceNotFoundError
from .quiz_format import Question, Answer, QUESTION_TYPES

logger = logging.getLogger("canvas_author.quizzes")


def list_quizzes(course_id: str, client: Optional[CanvasClient] = None) -> List[Dict[str, Any]]:
    """
    List all quizzes in a course.

    Args:
        course_id: Canvas course ID
        client: Optional CanvasClient instance

    Returns:
        List of quiz metadata dicts
    """
    canvas = client or get_canvas_client()
    course = canvas.get_course(course_id)
    quizzes = course.get_quizzes()

    result = []
    for quiz in quizzes:
        result.append({
            "id": quiz.id,
            "title": quiz.title,
            "quiz_type": getattr(quiz, "quiz_type", "assignment"),
            "time_limit": getattr(quiz, "time_limit", None),
            "points_possible": getattr(quiz, "points_possible", None),
            "question_count": getattr(quiz, "question_count", 0),
            "published": getattr(quiz, "published", False),
            "due_at": str(getattr(quiz, "due_at", None)),
            "unlock_at": str(getattr(quiz, "unlock_at", None)),
            "lock_at": str(getattr(quiz, "lock_at", None)),
        })

    logger.info(f"Listed {len(result)} quizzes for course {course_id}")
    return result


def get_quiz(
    course_id: str,
    quiz_id: str,
    client: Optional[CanvasClient] = None
) -> Dict[str, Any]:
    """
    Get a quiz by ID.

    Args:
        course_id: Canvas course ID
        quiz_id: Quiz ID
        client: Optional CanvasClient instance

    Returns:
        Quiz data dict
    """
    canvas = client or get_canvas_client()
    course = canvas.get_course(course_id)

    try:
        quiz = course.get_quiz(int(quiz_id))
    except ResourceDoesNotExist:
        raise ResourceNotFoundError("quiz", quiz_id)

    return {
        "id": quiz.id,
        "title": quiz.title,
        "description": getattr(quiz, "description", ""),
        "quiz_type": getattr(quiz, "quiz_type", "assignment"),
        "time_limit": getattr(quiz, "time_limit", None),
        "shuffle_answers": getattr(quiz, "shuffle_answers", False),
        "points_possible": getattr(quiz, "points_possible", None),
        "question_count": getattr(quiz, "question_count", 0),
        "published": getattr(quiz, "published", False),
        "allowed_attempts": getattr(quiz, "allowed_attempts", 1),
        "due_at": str(getattr(quiz, "due_at", None)),
        "unlock_at": str(getattr(quiz, "unlock_at", None)),
        "lock_at": str(getattr(quiz, "lock_at", None)),
    }


def quiz_has_submissions(
    course_id: str,
    quiz_id: str,
    client: Optional[CanvasClient] = None
) -> bool:
    """
    Check if a quiz has any submissions.

    Args:
        course_id: Canvas course ID
        quiz_id: Quiz ID
        client: Optional CanvasClient instance

    Returns:
        True if the quiz has submissions, False otherwise
    """
    canvas = client or get_canvas_client()
    course = canvas.get_course(course_id)

    try:
        quiz = course.get_quiz(int(quiz_id))
        submissions = list(quiz.get_submissions())
        # Filter out submissions that are just previews or haven't been started
        actual_submissions = [
            s for s in submissions
            if getattr(s, 'workflow_state', '') not in ('untaken', 'preview')
        ]
        return len(actual_submissions) > 0
    except ResourceDoesNotExist:
        raise ResourceNotFoundError("quiz", quiz_id)
    except Exception as e:
        logger.warning(f"Error checking quiz submissions: {e}")
        return False  # Assume no submissions if we can't check


def get_quiz_questions(
    course_id: str,
    quiz_id: str,
    client: Optional[CanvasClient] = None
) -> List[Dict[str, Any]]:
    """
    Get all questions for a quiz.

    Args:
        course_id: Canvas course ID
        quiz_id: Quiz ID
        client: Optional CanvasClient instance

    Returns:
        List of question dicts
    """
    canvas = client or get_canvas_client()
    course = canvas.get_course(course_id)

    try:
        quiz = course.get_quiz(int(quiz_id))
    except ResourceDoesNotExist:
        raise ResourceNotFoundError("quiz", quiz_id)

    questions = quiz.get_questions()

    result = []
    for q in questions:
        result.append({
            "id": q.id,
            "question_name": getattr(q, "question_name", ""),
            "question_type": getattr(q, "question_type", "multiple_choice_question"),
            "question_text": getattr(q, "question_text", ""),
            "points_possible": getattr(q, "points_possible", 1.0),
            "position": getattr(q, "position", 0),
            "answers": getattr(q, "answers", []),
            "correct_comments": getattr(q, "correct_comments", None),
            "incorrect_comments": getattr(q, "incorrect_comments", None),
            "neutral_comments": getattr(q, "neutral_comments", None),
        })

    logger.info(f"Retrieved {len(result)} questions for quiz {quiz_id}")
    return result


def create_quiz(
    course_id: str,
    title: str,
    description: str = "",
    quiz_type: str = "assignment",
    time_limit: Optional[int] = None,
    shuffle_answers: bool = False,
    published: bool = False,
    allowed_attempts: int = 1,
    due_at: Optional[str] = None,
    unlock_at: Optional[str] = None,
    lock_at: Optional[str] = None,
    client: Optional[CanvasClient] = None
) -> Dict[str, Any]:
    """
    Create a new quiz.

    Args:
        course_id: Canvas course ID
        title: Quiz title
        description: Quiz description/instructions
        quiz_type: 'practice_quiz', 'assignment', 'graded_survey', 'survey'
        time_limit: Time limit in minutes (None for unlimited)
        shuffle_answers: Whether to shuffle answer choices
        published: Whether to publish immediately
        allowed_attempts: Number of attempts allowed (-1 for unlimited)
        due_at: Due date (ISO format)
        unlock_at: Unlock date (ISO format)
        lock_at: Lock date (ISO format)
        client: Optional CanvasClient instance

    Returns:
        Created quiz data
    """
    canvas = client or get_canvas_client()
    course = canvas.get_course(course_id)

    quiz_data = {
        "title": title,
        "description": description,
        "quiz_type": quiz_type,
        "shuffle_answers": shuffle_answers,
        "published": published,
        "allowed_attempts": allowed_attempts,
    }

    if time_limit is not None:
        quiz_data["time_limit"] = time_limit
    if due_at:
        quiz_data["due_at"] = due_at
    if unlock_at:
        quiz_data["unlock_at"] = unlock_at
    if lock_at:
        quiz_data["lock_at"] = lock_at

    quiz = course.create_quiz(quiz=quiz_data)

    logger.info(f"Created quiz '{title}' in course {course_id}")

    return {
        "id": quiz.id,
        "title": quiz.title,
        "quiz_type": getattr(quiz, "quiz_type", quiz_type),
        "published": getattr(quiz, "published", published),
    }


def update_quiz(
    course_id: str,
    quiz_id: str,
    title: Optional[str] = None,
    description: Optional[str] = None,
    time_limit: Optional[int] = None,
    shuffle_answers: Optional[bool] = None,
    published: Optional[bool] = None,
    allowed_attempts: Optional[int] = None,
    client: Optional[CanvasClient] = None
) -> Dict[str, Any]:
    """
    Update an existing quiz.

    Args:
        course_id: Canvas course ID
        quiz_id: Quiz ID
        title: New title (optional)
        description: New description (optional)
        time_limit: New time limit (optional)
        shuffle_answers: Whether to shuffle answers (optional)
        published: Whether to publish (optional)
        allowed_attempts: Number of attempts (optional)
        client: Optional CanvasClient instance

    Returns:
        Updated quiz data
    """
    canvas = client or get_canvas_client()
    course = canvas.get_course(course_id)

    try:
        quiz = course.get_quiz(int(quiz_id))
    except ResourceDoesNotExist:
        raise ResourceNotFoundError("quiz", quiz_id)

    update_data = {}
    if title is not None:
        update_data["title"] = title
    if description is not None:
        update_data["description"] = description
    if time_limit is not None:
        update_data["time_limit"] = time_limit
    if shuffle_answers is not None:
        update_data["shuffle_answers"] = shuffle_answers
    if published is not None:
        update_data["published"] = published
    if allowed_attempts is not None:
        update_data["allowed_attempts"] = allowed_attempts

    if update_data:
        quiz = quiz.edit(quiz=update_data)
        logger.info(f"Updated quiz {quiz_id} in course {course_id}")

    return {
        "id": quiz.id,
        "title": quiz.title,
        "published": getattr(quiz, "published", False),
    }


def delete_quiz(
    course_id: str,
    quiz_id: str,
    client: Optional[CanvasClient] = None
) -> bool:
    """
    Delete a quiz.

    Args:
        course_id: Canvas course ID
        quiz_id: Quiz ID
        client: Optional CanvasClient instance

    Returns:
        True if deleted successfully
    """
    canvas = client or get_canvas_client()
    course = canvas.get_course(course_id)

    try:
        quiz = course.get_quiz(int(quiz_id))
    except ResourceDoesNotExist:
        raise ResourceNotFoundError("quiz", quiz_id)

    quiz.delete()
    logger.info(f"Deleted quiz {quiz_id} from course {course_id}")
    return True


def create_question(
    course_id: str,
    quiz_id: str,
    question: Question,
    client: Optional[CanvasClient] = None
) -> Dict[str, Any]:
    """
    Create a new question in a quiz.

    Args:
        course_id: Canvas course ID
        quiz_id: Quiz ID
        question: Question object with type, text, answers, etc.
        client: Optional CanvasClient instance

    Returns:
        Created question data
    """
    canvas = client or get_canvas_client()
    course = canvas.get_course(course_id)

    try:
        quiz = course.get_quiz(int(quiz_id))
    except ResourceDoesNotExist:
        raise ResourceNotFoundError("quiz", quiz_id)

    question_data = question.to_canvas_question()
    created = quiz.create_question(question=question_data)

    logger.info(f"Created question in quiz {quiz_id}")

    return {
        "id": created.id,
        "question_name": getattr(created, "question_name", ""),
        "question_type": getattr(created, "question_type", ""),
        "points_possible": getattr(created, "points_possible", 1.0),
    }


def update_question(
    course_id: str,
    quiz_id: str,
    question_id: str,
    question: Question,
    client: Optional[CanvasClient] = None
) -> Dict[str, Any]:
    """
    Update an existing question in a quiz.

    Args:
        course_id: Canvas course ID
        quiz_id: Quiz ID
        question_id: Question ID
        question: Updated Question object
        client: Optional CanvasClient instance

    Returns:
        Updated question data
    """
    canvas = client or get_canvas_client()
    course = canvas.get_course(course_id)

    try:
        quiz = course.get_quiz(int(quiz_id))
    except ResourceDoesNotExist:
        raise ResourceNotFoundError("quiz", quiz_id)

    try:
        q = quiz.get_question(int(question_id))
    except ResourceDoesNotExist:
        raise ResourceNotFoundError("question", question_id)

    question_data = question.to_canvas_question()
    updated = q.edit(question=question_data)

    logger.info(f"Updated question {question_id} in quiz {quiz_id}")

    return {
        "id": updated.id,
        "question_name": getattr(updated, "question_name", ""),
        "question_type": getattr(updated, "question_type", ""),
        "points_possible": getattr(updated, "points_possible", 1.0),
    }


def delete_question(
    course_id: str,
    quiz_id: str,
    question_id: str,
    client: Optional[CanvasClient] = None
) -> bool:
    """
    Delete a question from a quiz.

    Args:
        course_id: Canvas course ID
        quiz_id: Quiz ID
        question_id: Question ID
        client: Optional CanvasClient instance

    Returns:
        True if deleted successfully
    """
    canvas = client or get_canvas_client()
    course = canvas.get_course(course_id)

    try:
        quiz = course.get_quiz(int(quiz_id))
    except ResourceDoesNotExist:
        raise ResourceNotFoundError("quiz", quiz_id)

    try:
        q = quiz.get_question(int(question_id))
    except ResourceDoesNotExist:
        raise ResourceNotFoundError("question", question_id)

    q.delete()
    logger.info(f"Deleted question {question_id} from quiz {quiz_id}")
    return True
