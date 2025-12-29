"""
E2E tests for Canvas quiz operations.

Run with: pytest tests/e2e/test_e2e_quizzes.py -v -m e2e
"""

import pytest
from pathlib import Path
from canvas_mcp.quizzes import (
    list_quizzes, get_quiz, get_quiz_questions,
    create_quiz, update_quiz, delete_quiz,
    create_question, delete_question
)
from canvas_mcp.quiz_sync import pull_quizzes, push_quizzes, quiz_sync_status
from canvas_mcp.quiz_format import (
    parse_quiz_markdown, generate_quiz_markdown,
    Question, Answer
)
from canvas_mcp.exceptions import ResourceNotFoundError


pytestmark = pytest.mark.e2e


@pytest.fixture(scope="function")
def test_quiz_name() -> str:
    """Generate a unique test quiz name with timestamp."""
    from datetime import datetime
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    return f"e2e-test-quiz-{timestamp}"


@pytest.fixture(scope="function")
def cleanup_test_quizzes(canvas_client, test_course_id: str, e2e_config):
    """Cleanup fixture that removes test quizzes before and after test."""

    def _cleanup():
        if e2e_config["skip_cleanup"]:
            return

        try:
            quizzes = list_quizzes(test_course_id, canvas_client)
            for quiz in quizzes:
                if quiz["title"].startswith("e2e-test-"):
                    try:
                        delete_quiz(test_course_id, str(quiz["id"]), canvas_client)
                        print(f"Cleaned up test quiz: {quiz['title']}")
                    except Exception as e:
                        print(f"Failed to cleanup quiz {quiz['title']}: {e}")
        except Exception as e:
            print(f"Failed to list quizzes for cleanup: {e}")

    # Cleanup before test
    _cleanup()

    # Run test
    yield

    # Cleanup after test
    _cleanup()


class TestQuizCRUD:
    """Test quiz CRUD operations."""

    def test_list_quizzes(
        self,
        canvas_client,
        test_course_id: str
    ):
        """Test listing quizzes in a course."""
        quizzes = list_quizzes(test_course_id, canvas_client)

        assert isinstance(quizzes, list)
        if quizzes:
            quiz = quizzes[0]
            assert "id" in quiz
            assert "title" in quiz
            assert "published" in quiz

    def test_create_and_get_quiz(
        self,
        canvas_client,
        test_course_id: str,
        test_quiz_name: str,
        cleanup_test_quizzes
    ):
        """Test creating and retrieving a quiz."""
        # Create quiz
        result = create_quiz(
            course_id=test_course_id,
            title=f"e2e-test-{test_quiz_name}",
            description="Test quiz created by E2E tests",
            quiz_type="practice_quiz",
            time_limit=30,
            published=False,
            client=canvas_client
        )

        assert "id" in result
        assert result["title"] == f"e2e-test-{test_quiz_name}"

        # Get quiz
        quiz = get_quiz(test_course_id, str(result["id"]), canvas_client)

        assert quiz["title"] == f"e2e-test-{test_quiz_name}"
        assert quiz["time_limit"] == 30
        assert quiz["published"] is False

    def test_update_quiz(
        self,
        canvas_client,
        test_course_id: str,
        test_quiz_name: str,
        cleanup_test_quizzes
    ):
        """Test updating a quiz."""
        # Create quiz
        created = create_quiz(
            course_id=test_course_id,
            title=f"e2e-test-{test_quiz_name}",
            time_limit=30,
            client=canvas_client
        )

        # Update quiz
        update_quiz(
            course_id=test_course_id,
            quiz_id=str(created["id"]),
            title=f"e2e-test-{test_quiz_name}-updated",
            time_limit=60,
            client=canvas_client
        )

        # Verify update
        quiz = get_quiz(test_course_id, str(created["id"]), canvas_client)
        assert quiz["title"] == f"e2e-test-{test_quiz_name}-updated"
        assert quiz["time_limit"] == 60

    def test_delete_quiz(
        self,
        canvas_client,
        test_course_id: str,
        test_quiz_name: str
    ):
        """Test deleting a quiz."""
        # Create quiz
        created = create_quiz(
            course_id=test_course_id,
            title=f"e2e-test-{test_quiz_name}",
            client=canvas_client
        )

        # Delete quiz
        result = delete_quiz(test_course_id, str(created["id"]), canvas_client)
        assert result is True

        # Verify deletion - quiz should no longer appear in list
        quizzes = list_quizzes(test_course_id, canvas_client)
        quiz_ids = [str(q["id"]) for q in quizzes]
        assert str(created["id"]) not in quiz_ids


class TestQuizQuestions:
    """Test quiz question operations."""

    def test_create_and_get_questions(
        self,
        canvas_client,
        test_course_id: str,
        test_quiz_name: str,
        cleanup_test_quizzes
    ):
        """Test creating and retrieving quiz questions."""
        # Create quiz
        quiz = create_quiz(
            course_id=test_course_id,
            title=f"e2e-test-{test_quiz_name}",
            client=canvas_client
        )

        # Create a multiple choice question
        question = Question(
            number=1,
            type="MC",
            text="What is 2 + 2?",
            points=2.0,
            answers=[
                Answer(text="3", correct=False),
                Answer(text="4", correct=True),
                Answer(text="5", correct=False),
            ],
            correct_feedback="Correct!",
            incorrect_feedback="Try again.",
        )

        created_q = create_question(
            test_course_id,
            str(quiz["id"]),
            question,
            canvas_client
        )

        assert "id" in created_q
        assert created_q["question_type"] == "multiple_choice_question"

        # Get questions
        questions = get_quiz_questions(test_course_id, str(quiz["id"]), canvas_client)

        assert len(questions) >= 1
        q = questions[0]
        assert "What is 2 + 2?" in q["question_text"]


class TestQuizSync:
    """Test quiz sync operations."""

    def test_pull_quizzes(
        self,
        canvas_client,
        test_course_id: str,
        temp_workspace: Path,
        test_quiz_name: str,
        cleanup_test_quizzes
    ):
        """Test pulling quizzes from Canvas."""
        # Create a quiz first
        quiz = create_quiz(
            course_id=test_course_id,
            title=f"e2e-test-{test_quiz_name}",
            description="Test quiz for pull",
            client=canvas_client
        )

        # Add a question
        question = Question(
            number=1,
            type="MC",
            text="Test question",
            points=1.0,
            answers=[
                Answer(text="A", correct=True),
                Answer(text="B", correct=False),
            ],
        )
        create_question(test_course_id, str(quiz["id"]), question, canvas_client)

        # Pull quizzes
        result = pull_quizzes(
            course_id=test_course_id,
            output_dir=str(temp_workspace),
            overwrite=True,
            client=canvas_client
        )

        assert "pulled" in result
        # Should have pulled at least our test quiz
        pulled_titles = [p["title"] for p in result["pulled"]]
        assert any(f"e2e-test-{test_quiz_name}" in t for t in pulled_titles)

        # Check file was created
        quiz_files = list(temp_workspace.glob("*.quiz.md"))
        assert len(quiz_files) > 0

    def test_push_quizzes(
        self,
        canvas_client,
        test_course_id: str,
        temp_workspace: Path,
        test_quiz_name: str,
        cleanup_test_quizzes
    ):
        """Test pushing quizzes to Canvas."""
        # Create a local quiz file
        quiz_file = temp_workspace / f"e2e-test-{test_quiz_name}.quiz.md"
        quiz_content = f"""---
title: e2e-test-{test_quiz_name}
course_id: {test_course_id}
quiz_type: practice_quiz
time_limit: 15
published: false
---

# e2e-test-{test_quiz_name}

## Questions

### 1. [MC] What is the capital of France? (2 pts)

a. London
*b. Paris
c. Berlin

> Correct: Correct!
"""
        quiz_file.write_text(quiz_content, encoding="utf-8")

        # Push quizzes
        result = push_quizzes(
            course_id=test_course_id,
            input_dir=str(temp_workspace),
            create_missing=True,
            update_existing=False,
            client=canvas_client
        )

        assert len(result["created"]) == 1
        assert result["created"][0]["title"] == f"e2e-test-{test_quiz_name}"

        # Verify quiz was created on Canvas
        quiz_id = result["created"][0]["quiz_id"]
        quiz = get_quiz(test_course_id, str(quiz_id), canvas_client)
        assert quiz["title"] == f"e2e-test-{test_quiz_name}"
        assert quiz["time_limit"] == 15

    def test_quiz_sync_status(
        self,
        canvas_client,
        test_course_id: str,
        temp_workspace: Path
    ):
        """Test quiz sync status checking."""
        status = quiz_sync_status(
            course_id=test_course_id,
            local_dir=str(temp_workspace),
            client=canvas_client
        )

        assert "canvas_only" in status
        assert "local_only" in status
        assert "synced" in status
        assert "summary" in status
