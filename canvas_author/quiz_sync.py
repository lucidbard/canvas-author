"""
Quiz Sync Module

Pull and push operations for syncing quizzes between Canvas and local markdown files.
Includes automatic image download/upload with relative path rewriting.
"""

import logging
import os
import re
from pathlib import Path
from typing import Dict, Any, List, Optional

from .client import get_canvas_client, CanvasClient
from .quizzes import (
    list_quizzes,
    get_quiz,
    get_quiz_questions,
    create_quiz,
    update_quiz,
    create_question,
    delete_question,
    quiz_has_submissions,
)
from .quiz_format import (
    parse_quiz_markdown,
    generate_quiz_markdown,
    questions_from_canvas,
    quiz_metadata_from_canvas,
    Question,
)
from .files import download_images_from_content, upload_images_from_content
from .exceptions import ResourceNotFoundError
from .pandoc import markdown_to_html, is_pandoc_available

logger = logging.getLogger("canvas_author.quiz_sync")


def _slugify(title: str) -> str:
    """Convert a title to a filesystem-safe slug."""
    slug = title.lower()
    slug = re.sub(r'[^\w\s-]', '', slug)
    slug = re.sub(r'[\s_]+', '-', slug)
    slug = re.sub(r'-+', '-', slug)
    return slug.strip('-')


def pull_quizzes(
    course_id: str,
    output_dir: str,
    overwrite: bool = False,
    download_images: bool = True,
    client: Optional[CanvasClient] = None
) -> Dict[str, Any]:
    """
    Pull all quizzes from Canvas to local markdown files.

    Args:
        course_id: Canvas course ID
        output_dir: Directory to write quiz files (quizzes subfolder will be created)
        overwrite: Whether to overwrite existing files
        download_images: Download embedded images to files/ directory
        client: Optional CanvasClient instance

    Returns:
        Dict with 'pulled', 'skipped', 'errors', and 'images_downloaded'
    """
    canvas = client or get_canvas_client()

    # Create quizzes subfolder
    output_path = Path(output_dir) / "quizzes"
    output_path.mkdir(parents=True, exist_ok=True)

    # Get domain for URL matching
    domain = canvas.api_url.replace("https://", "").replace("http://", "").rstrip("/")

    result = {
        "pulled": [],
        "skipped": [],
        "errors": [],
        "images_downloaded": 0,
    }

    quizzes = list_quizzes(course_id, client=canvas)
    logger.info(f"Found {len(quizzes)} quizzes in course {course_id}")

    for quiz_meta in quizzes:
        quiz_id = str(quiz_meta["id"])
        title = quiz_meta["title"]
        slug = _slugify(title)
        filename = f"{slug}.quiz.md"
        file_path = output_path / filename

        try:
            # Check if file exists and skip if not overwriting
            if file_path.exists() and not overwrite:
                result["skipped"].append({
                    "quiz_id": quiz_id,
                    "title": title,
                    "file": filename,
                    "reason": "file exists",
                })
                continue

            # Get full quiz data
            quiz_data = get_quiz(course_id, quiz_id, client=canvas)

            # Get questions
            questions_data = get_quiz_questions(course_id, quiz_id, client=canvas)
            questions = questions_from_canvas(questions_data)

            # Download images from question text and rewrite to relative paths
            if download_images:
                for question in questions:
                    if question.text:
                        question.text, downloaded = download_images_from_content(
                            question.text, course_id, output_path, domain, canvas, is_html=False
                        )
                        result["images_downloaded"] += len(downloaded)

            # Build metadata
            metadata = quiz_metadata_from_canvas(quiz_data, course_id)

            # Get description as instructions
            instructions = quiz_data.get("description", "")

            # Download images from instructions too
            if download_images and instructions:
                instructions, downloaded = download_images_from_content(
                    instructions, course_id, output_path, domain, canvas, is_html=False
                )
                result["images_downloaded"] += len(downloaded)

            # Generate markdown
            content = generate_quiz_markdown(metadata, questions, instructions)

            # Write file
            file_path.write_text(content, encoding="utf-8")

            result["pulled"].append({
                "quiz_id": quiz_id,
                "title": title,
                "file": filename,
                "question_count": len(questions),
            })
            logger.info(f"Pulled quiz '{title}' to {filename}")

        except Exception as e:
            logger.error(f"Error pulling quiz {quiz_id}: {e}")
            result["errors"].append({
                "quiz_id": quiz_id,
                "title": title,
                "error": str(e),
            })

    return result


def push_quizzes(
    course_id: str,
    input_dir: str,
    create_missing: bool = True,
    update_existing: bool = True,
    upload_images: bool = True,
    client: Optional[CanvasClient] = None
) -> Dict[str, Any]:
    """
    Push local quiz markdown files to Canvas.

    Args:
        course_id: Canvas course ID
        input_dir: Directory containing quiz markdown files (or parent dir with quizzes subfolder)
        create_missing: Whether to create quizzes that don't exist on Canvas
        update_existing: Whether to update quizzes that already exist
        upload_images: Upload local images to Canvas
        client: Optional CanvasClient instance

    Returns:
        Dict with 'created', 'updated', 'skipped', 'errors', and 'images_uploaded'
    """
    canvas = client or get_canvas_client()

    # Check if input_dir has a quizzes subfolder
    input_path = Path(input_dir)
    quizzes_path = input_path / "quizzes"
    if quizzes_path.exists():
        input_path = quizzes_path

    result = {
        "created": [],
        "updated": [],
        "skipped": [],
        "errors": [],
        "images_uploaded": 0,
    }

    # Find all quiz markdown files
    quiz_files = list(input_path.glob("*.quiz.md"))
    logger.info(f"Found {len(quiz_files)} quiz files in {input_dir}")

    # Get existing quizzes for comparison
    existing_quizzes = {str(q["id"]): q for q in list_quizzes(course_id, client=canvas)}

    for file_path in quiz_files:
        try:
            content = file_path.read_text(encoding="utf-8")
            metadata, questions = parse_quiz_markdown(content)

            title = metadata.get("title", file_path.stem.replace(".quiz", ""))
            quiz_id = metadata.get("quiz_id")

            # Upload images from question text and rewrite to Canvas URLs
            if upload_images:
                for question in questions:
                    if question.text:
                        question.text, uploaded = upload_images_from_content(
                            question.text, course_id, input_path, canvas, is_markdown=True
                        )
                        result["images_uploaded"] += len(uploaded)
                # Also handle description/instructions in metadata
                if metadata.get("description"):
                    metadata["description"], uploaded = upload_images_from_content(
                        metadata["description"], course_id, input_path, canvas, is_markdown=True
                    )
                    result["images_uploaded"] += len(uploaded)

            # Check if quiz exists
            if quiz_id and str(quiz_id) in existing_quizzes:
                # Update existing quiz
                if not update_existing:
                    result["skipped"].append({
                        "file": file_path.name,
                        "title": title,
                        "reason": "update_existing is False",
                    })
                    continue

                # Check for submissions - don't update if students have taken the quiz
                if quiz_has_submissions(course_id, str(quiz_id), client=canvas):
                    result["skipped"].append({
                        "file": file_path.name,
                        "title": title,
                        "reason": "quiz has student submissions - cannot modify",
                    })
                    logger.warning(f"Skipping quiz '{title}' - has student submissions")
                    continue

                _update_quiz_from_markdown(
                    course_id, str(quiz_id), metadata, questions, canvas
                )
                result["updated"].append({
                    "file": file_path.name,
                    "title": title,
                    "quiz_id": quiz_id,
                })
                logger.info(f"Updated quiz '{title}' from {file_path.name}")

            else:
                # Create new quiz
                if not create_missing:
                    result["skipped"].append({
                        "file": file_path.name,
                        "title": title,
                        "reason": "create_missing is False",
                    })
                    continue

                new_quiz = _create_quiz_from_markdown(
                    course_id, metadata, questions, canvas
                )
                result["created"].append({
                    "file": file_path.name,
                    "title": title,
                    "quiz_id": new_quiz["id"],
                })

                # Update the file with the new quiz_id
                metadata["quiz_id"] = new_quiz["id"]
                updated_content = generate_quiz_markdown(
                    metadata, questions, metadata.get("description", "")
                )
                file_path.write_text(updated_content, encoding="utf-8")

                logger.info(f"Created quiz '{title}' from {file_path.name}")

        except Exception as e:
            logger.error(f"Error pushing {file_path.name}: {e}")
            result["errors"].append({
                "file": file_path.name,
                "error": str(e),
            })

    return result


def _create_quiz_from_markdown(
    course_id: str,
    metadata: Dict[str, Any],
    questions: List[Question],
    client: CanvasClient
) -> Dict[str, Any]:
    """Create a new quiz from parsed markdown data."""
    # Convert markdown description to HTML
    description = metadata.get("description", "")
    if description and is_pandoc_available():
        description = markdown_to_html(description)

    # Create the quiz
    quiz = create_quiz(
        course_id=course_id,
        title=metadata.get("title", "Untitled Quiz"),
        description=description,
        quiz_type=metadata.get("quiz_type", "assignment"),
        time_limit=metadata.get("time_limit"),
        shuffle_answers=metadata.get("shuffle_answers", False),
        published=metadata.get("published", False),
        allowed_attempts=metadata.get("allowed_attempts", 1),
        due_at=metadata.get("due_at"),
        unlock_at=metadata.get("unlock_at"),
        lock_at=metadata.get("lock_at"),
        client=client,
    )

    # Add questions
    quiz_id = str(quiz["id"])
    for question in questions:
        create_question(course_id, quiz_id, question, client=client)

    return quiz


def _update_quiz_from_markdown(
    course_id: str,
    quiz_id: str,
    metadata: Dict[str, Any],
    questions: List[Question],
    client: CanvasClient
) -> Dict[str, Any]:
    """Update an existing quiz from parsed markdown data."""
    # Convert markdown description to HTML
    description = metadata.get("description")
    if description and is_pandoc_available():
        description = markdown_to_html(description)

    # Update quiz settings
    quiz = update_quiz(
        course_id=course_id,
        quiz_id=quiz_id,
        title=metadata.get("title"),
        description=description,
        time_limit=metadata.get("time_limit"),
        shuffle_answers=metadata.get("shuffle_answers"),
        published=metadata.get("published"),
        allowed_attempts=metadata.get("allowed_attempts"),
        client=client,
    )

    # Get existing questions
    existing_questions = get_quiz_questions(course_id, quiz_id, client=client)

    # Delete existing questions (simpler than trying to match/update)
    for eq in existing_questions:
        try:
            delete_question(course_id, quiz_id, str(eq["id"]), client=client)
        except Exception as e:
            logger.warning(f"Failed to delete question {eq['id']}: {e}")

    # Create new questions
    for question in questions:
        create_question(course_id, quiz_id, question, client=client)

    return quiz


def quiz_sync_status(
    course_id: str,
    local_dir: str,
    client: Optional[CanvasClient] = None
) -> Dict[str, Any]:
    """
    Check sync status between local quiz files and Canvas.

    Args:
        course_id: Canvas course ID
        local_dir: Directory containing local quiz files (checks for quizzes subfolder)
        client: Optional CanvasClient instance

    Returns:
        Dict with 'canvas_only', 'local_only', 'synced', and 'summary'
    """
    canvas = client or get_canvas_client()

    # Check for quizzes subfolder
    local_path = Path(local_dir)
    quizzes_path = local_path / "quizzes"
    if quizzes_path.exists():
        local_path = quizzes_path

    # Get Canvas quizzes
    canvas_quizzes = {str(q["id"]): q for q in list_quizzes(course_id, client=canvas)}

    # Get local quiz files
    local_quizzes = {}
    for file_path in local_path.glob("*.quiz.md"):
        try:
            content = file_path.read_text(encoding="utf-8")
            metadata, _ = parse_quiz_markdown(content)
            quiz_id = metadata.get("quiz_id")
            if quiz_id:
                local_quizzes[str(quiz_id)] = {
                    "file": file_path.name,
                    "title": metadata.get("title", ""),
                    "quiz_id": quiz_id,
                }
            else:
                # No quiz_id means it's local-only
                local_quizzes[f"local:{file_path.name}"] = {
                    "file": file_path.name,
                    "title": metadata.get("title", ""),
                    "quiz_id": None,
                }
        except Exception as e:
            logger.warning(f"Error reading {file_path.name}: {e}")

    # Compute differences
    canvas_ids = set(canvas_quizzes.keys())
    local_ids = {k for k in local_quizzes.keys() if not k.startswith("local:")}
    local_only_files = [v for k, v in local_quizzes.items() if k.startswith("local:")]

    canvas_only = [canvas_quizzes[qid] for qid in canvas_ids - local_ids]
    synced = [
        {**local_quizzes[qid], "canvas_title": canvas_quizzes[qid]["title"]}
        for qid in canvas_ids & local_ids
    ]

    return {
        "canvas_only": canvas_only,
        "local_only": local_only_files,
        "synced": synced,
        "summary": {
            "canvas_count": len(canvas_quizzes),
            "local_count": len(local_quizzes),
            "canvas_only_count": len(canvas_only),
            "local_only_count": len(local_only_files),
            "synced_count": len(synced),
        },
    }
