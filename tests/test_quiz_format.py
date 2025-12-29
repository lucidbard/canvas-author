"""Tests for quiz markdown format parser and generator."""

import pytest
from canvas_mcp.quiz_format import (
    parse_quiz_markdown,
    generate_quiz_markdown,
    questions_from_canvas,
    quiz_metadata_from_canvas,
    Question,
    Answer,
    QUESTION_TYPES,
    CANVAS_TO_CODE,
)


class TestParseQuizMarkdown:
    """Tests for parsing quiz markdown files."""

    def test_parse_simple_quiz(self):
        """Test parsing a simple quiz with multiple choice questions."""
        content = """---
title: Sample Quiz
quiz_id: 12345
course_id: 1417021
time_limit: 30
published: true
---

# Sample Quiz

## Questions

### 1. [MC] What is 2 + 2? (2 pts)

a. 3
*b. 4
c. 5
d. 6

---

### 2. [MC] What color is the sky? (1 pt)

*a. Blue
b. Green
c. Red
"""
        metadata, questions = parse_quiz_markdown(content)

        assert metadata["title"] == "Sample Quiz"
        assert metadata["quiz_id"] == 12345
        assert metadata["time_limit"] == 30
        assert metadata["published"] is True

        assert len(questions) == 2

        q1 = questions[0]
        assert q1.number == 1
        assert q1.type == "MC"
        assert q1.text == "What is 2 + 2?"
        assert q1.points == 2.0
        assert len(q1.answers) == 4
        assert q1.answers[1].correct is True
        assert q1.answers[1].text == "4"

        q2 = questions[1]
        assert q2.number == 2
        assert q2.points == 1.0
        assert q2.answers[0].correct is True

    def test_parse_true_false(self):
        """Test parsing true/false questions."""
        content = """---
title: TF Quiz
---

## Questions

### 1. [TF] The Earth is round. (1 pt)

*a. True
b. False
"""
        metadata, questions = parse_quiz_markdown(content)

        assert len(questions) == 1
        q = questions[0]
        assert q.type == "TF"
        assert len(q.answers) == 2
        assert q.answers[0].correct is True
        assert q.answers[0].text == "True"

    def test_parse_short_answer(self):
        """Test parsing short answer questions."""
        content = """---
title: SA Quiz
---

## Questions

### 1. [SA] What year did WWII end? (2 pts)

*1945
*nineteen forty-five
*1945 AD

> Any of these answers are acceptable.
"""
        metadata, questions = parse_quiz_markdown(content)

        q = questions[0]
        assert q.type == "SA"
        assert len(q.answers) == 3
        assert all(a.correct for a in q.answers)
        assert q.answers[0].text == "1945"
        assert q.neutral_feedback == "Any of these answers are acceptable."

    def test_parse_essay(self):
        """Test parsing essay questions."""
        content = """---
title: Essay Quiz
---

## Questions

### 1. [ESS] Explain the causes of WWI. (10 pts)

> Students should discuss nationalism, militarism, and alliances.
"""
        metadata, questions = parse_quiz_markdown(content)

        q = questions[0]
        assert q.type == "ESS"
        assert q.points == 10.0
        assert len(q.answers) == 0
        assert "nationalism" in q.neutral_feedback

    def test_parse_multiple_answers(self):
        """Test parsing multiple answer questions."""
        content = """---
title: MA Quiz
---

## Questions

### 1. [MA] Which are prime numbers? (3 pts)

*a. 2
b. 4
*c. 7
d. 9
*e. 11
"""
        metadata, questions = parse_quiz_markdown(content)

        q = questions[0]
        assert q.type == "MA"
        assert len(q.answers) == 5
        correct_answers = [a for a in q.answers if a.correct]
        assert len(correct_answers) == 3
        assert correct_answers[0].text == "2"
        assert correct_answers[1].text == "7"
        assert correct_answers[2].text == "11"

    def test_parse_matching(self):
        """Test parsing matching questions."""
        content = """---
title: Matching Quiz
---

## Questions

### 1. [MAT] Match the country to its capital. (4 pts)

a. France = Paris
b. Germany = Berlin
c. Japan = Tokyo
d. Australia = Canberra
"""
        metadata, questions = parse_quiz_markdown(content)

        q = questions[0]
        assert q.type == "MAT"
        assert len(q.answers) == 4
        assert q.answers[0].text == "France"
        assert q.answers[0].match_target == "Paris"
        assert q.answers[2].text == "Japan"
        assert q.answers[2].match_target == "Tokyo"

    def test_parse_numerical(self):
        """Test parsing numerical questions."""
        content = """---
title: Numerical Quiz
---

## Questions

### 1. [NUM] What is 15% of 200? (2 pts)

*30
margin: 0.5
"""
        metadata, questions = parse_quiz_markdown(content)

        q = questions[0]
        assert q.type == "NUM"
        assert q.answers[0].text == "30"
        assert q.margin == 0.5

    def test_parse_fill_in_blank(self):
        """Test parsing fill in the blank questions."""
        content = """---
title: FIB Quiz
---

## Questions

### 1. [FIB] The chemical symbol for water is ___. (1 pt)

*H2O
*h2o
"""
        metadata, questions = parse_quiz_markdown(content)

        q = questions[0]
        assert q.type == "FIB"
        assert len(q.answers) == 2
        assert q.answers[0].text == "H2O"

    def test_parse_with_feedback(self):
        """Test parsing questions with correct/incorrect feedback."""
        content = """---
title: Feedback Quiz
---

## Questions

### 1. [MC] What is the capital of France? (2 pts)

a. London
*b. Paris
c. Berlin

> Correct: Paris has been the capital since the 10th century.
> Incorrect: Remember, we're asking about France.
"""
        metadata, questions = parse_quiz_markdown(content)

        q = questions[0]
        assert q.correct_feedback == "Paris has been the capital since the 10th century."
        assert q.incorrect_feedback == "Remember, we're asking about France."

    def test_parse_default_type(self):
        """Test that questions without type code default to MC."""
        content = """---
title: Default Quiz
---

## Questions

### 1. What is 1 + 1? (1 pt)

a. 1
*b. 2
c. 3
"""
        metadata, questions = parse_quiz_markdown(content)

        q = questions[0]
        assert q.type == "MC"


class TestGenerateQuizMarkdown:
    """Tests for generating quiz markdown files."""

    def test_generate_simple_quiz(self):
        """Test generating a simple quiz."""
        metadata = {
            "title": "Test Quiz",
            "quiz_id": 123,
            "course_id": "456",
            "time_limit": 60,
            "published": False,
        }
        questions = [
            Question(
                number=1,
                type="MC",
                text="What is 2 + 2?",
                points=2.0,
                answers=[
                    Answer(text="3", correct=False, letter="a"),
                    Answer(text="4", correct=True, letter="b"),
                    Answer(text="5", correct=False, letter="c"),
                ],
            ),
        ]

        result = generate_quiz_markdown(metadata, questions)

        assert "title: Test Quiz" in result
        assert "quiz_id: 123" in result
        assert "### 1. [MC] What is 2 + 2?" in result
        assert "*b. 4" in result
        assert "a. 3" in result

    def test_generate_with_instructions(self):
        """Test generating quiz with instructions."""
        metadata = {"title": "Test"}
        questions = []

        result = generate_quiz_markdown(
            metadata,
            questions,
            instructions="Complete all questions. No calculators allowed."
        )

        assert "## Instructions" in result
        assert "No calculators allowed" in result

    def test_generate_matching(self):
        """Test generating matching questions."""
        metadata = {"title": "Matching Test"}
        questions = [
            Question(
                number=1,
                type="MAT",
                text="Match countries to capitals",
                points=4.0,
                answers=[
                    Answer(text="France", match_target="Paris", letter="a"),
                    Answer(text="Germany", match_target="Berlin", letter="b"),
                ],
            ),
        ]

        result = generate_quiz_markdown(metadata, questions)

        assert "a. France = Paris" in result
        assert "b. Germany = Berlin" in result

    def test_generate_with_feedback(self):
        """Test generating questions with feedback."""
        metadata = {"title": "Feedback Test"}
        questions = [
            Question(
                number=1,
                type="MC",
                text="Sample question",
                answers=[Answer(text="Answer", correct=True, letter="a")],
                correct_feedback="Great job!",
                incorrect_feedback="Try again.",
            ),
        ]

        result = generate_quiz_markdown(metadata, questions)

        assert "> Correct: Great job!" in result
        assert "> Incorrect: Try again." in result


class TestQuestionToCanvas:
    """Tests for converting questions to Canvas API format."""

    def test_mc_to_canvas(self):
        """Test converting multiple choice to Canvas format."""
        q = Question(
            number=1,
            type="MC",
            text="Sample question",
            points=2.0,
            answers=[
                Answer(text="Wrong", correct=False),
                Answer(text="Right", correct=True),
            ],
        )

        result = q.to_canvas_question()

        assert result["question_type"] == "multiple_choice_question"
        assert result["points_possible"] == 2.0
        assert result["question_text"] == "Sample question"
        assert len(result["answers"]) == 2
        assert result["answers"][0]["answer_weight"] == 0
        assert result["answers"][1]["answer_weight"] == 100

    def test_matching_to_canvas(self):
        """Test converting matching to Canvas format."""
        q = Question(
            number=1,
            type="MAT",
            text="Match items",
            answers=[
                Answer(text="Left1", match_target="Right1"),
                Answer(text="Left2", match_target="Right2"),
            ],
        )

        result = q.to_canvas_question()

        assert result["question_type"] == "matching_question"
        assert result["answers"][0]["answer_match_left"] == "Left1"
        assert result["answers"][0]["answer_match_right"] == "Right1"


class TestQuestionsFromCanvas:
    """Tests for converting Canvas API data to Question objects."""

    def test_convert_mc_from_canvas(self):
        """Test converting Canvas MC question to Question."""
        canvas_questions = [
            {
                "id": 123,
                "question_type": "multiple_choice_question",
                "question_text": "What is 1+1?",
                "points_possible": 2.0,
                "answers": [
                    {"text": "1", "weight": 0},
                    {"text": "2", "weight": 100},
                    {"text": "3", "weight": 0},
                ],
                "correct_comments": "Correct!",
                "incorrect_comments": "Try again.",
            }
        ]

        questions = questions_from_canvas(canvas_questions)

        assert len(questions) == 1
        q = questions[0]
        assert q.type == "MC"
        assert q.text == "What is 1+1?"
        assert q.points == 2.0
        assert q.question_id == 123
        assert len(q.answers) == 3
        assert q.answers[1].correct is True
        assert q.correct_feedback == "Correct!"


class TestQuizMetadataFromCanvas:
    """Tests for extracting quiz metadata from Canvas API data."""

    def test_extract_metadata(self):
        """Test extracting metadata from Canvas quiz."""
        canvas_quiz = {
            "id": 456,
            "title": "Midterm Exam",
            "quiz_type": "assignment",
            "time_limit": 90,
            "shuffle_answers": True,
            "published": False,
            "points_possible": 100,
            "allowed_attempts": 2,
            "description": "This is the midterm.",
        }

        metadata = quiz_metadata_from_canvas(canvas_quiz, "12345")

        assert metadata["title"] == "Midterm Exam"
        assert metadata["quiz_id"] == 456
        assert metadata["course_id"] == "12345"
        assert metadata["time_limit"] == 90
        assert metadata["shuffle_answers"] is True
        assert metadata["published"] is False
        assert metadata["allowed_attempts"] == 2


class TestQuestionTypes:
    """Tests for question type mappings."""

    def test_all_types_have_mapping(self):
        """Test that all type codes have Canvas equivalents."""
        for code in ["MC", "MA", "TF", "SA", "ESS", "FIB", "MAT", "NUM"]:
            assert code in QUESTION_TYPES
            assert QUESTION_TYPES[code] in CANVAS_TO_CODE

    def test_canvas_type_property(self):
        """Test Question.canvas_type property."""
        q = Question(number=1, type="MA", text="Test")
        assert q.canvas_type == "multiple_answers_question"

        q2 = Question(number=1, type="ESS", text="Test")
        assert q2.canvas_type == "essay_question"
