"""
Quiz markdown format parser and generator.

Provides a Respondus-inspired markdown format for Canvas quizzes that can be
version-controlled and edited in any text editor.
"""

import re
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any

from .frontmatter import parse_frontmatter, generate_frontmatter
from .pandoc import html_to_markdown, markdown_to_html, is_pandoc_available

logger = logging.getLogger("canvas_author.quiz_format")


def markdown_to_canvas_html(text: str) -> str:
    """
    Convert markdown text to HTML suitable for Canvas.
    Wraps in <p> tags if no block elements present.
    """
    if not text:
        return ""
    
    if is_pandoc_available():
        html = markdown_to_html(text)
        # Remove wrapping <p> if it's a single paragraph
        html = html.strip()
        return html
    else:
        # Basic conversion without pandoc
        # Convert bold/italic
        html = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
        html = re.sub(r'\*(.+?)\*', r'<em>\1</em>', html)
        html = re.sub(r'`(.+?)`', r'<code>\1</code>', html)
        # Convert line breaks
        html = html.replace('\n\n', '</p><p>')
        html = html.replace('\n', '<br>')
        if '</p>' not in html:
            html = f'<p>{html}</p>'
        return html

# Patterns for script/link tags that Canvas injects (we strip on pull, re-add on push)
SCRIPT_LINK_PATTERN = re.compile(
    r'<(?:script|link)[^>]*(?:custom_mobile|instructure-uploads)[^>]*(?:/>|>(?:</script>)?)',
    re.IGNORECASE | re.DOTALL
)


def clean_question_html(html: str) -> str:
    """
    Clean HTML from Canvas question text:
    - Strip <script> and <link> tags (they'll be re-added on push)
    - Convert remaining HTML to markdown if pandoc available
    - Otherwise strip remaining HTML tags
    """
    if not html:
        return ""
    
    # Remove script and link tags
    cleaned = SCRIPT_LINK_PATTERN.sub('', html)
    
    # Also remove any other script/link tags
    cleaned = re.sub(r'<script[^>]*>.*?</script>', '', cleaned, flags=re.IGNORECASE | re.DOTALL)
    cleaned = re.sub(r'<link[^>]*/?>', '', cleaned, flags=re.IGNORECASE)
    
    # Convert HTML to markdown if pandoc available
    if is_pandoc_available():
        cleaned = html_to_markdown(cleaned)
    else:
        # Basic HTML stripping
        cleaned = re.sub(r'<br\s*/?>', '\n', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'<p[^>]*>', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'</p>', '\n', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'<strong[^>]*>', '**', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'</strong>', '**', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'<em[^>]*>', '*', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'</em>', '*', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'<span[^>]*>', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'</span>', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'<[^>]+>', '', cleaned)  # Strip remaining tags
    
    # Clean up whitespace
    cleaned = re.sub(r'&nbsp;', ' ', cleaned)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    
    return cleaned


# Question type codes and their Canvas API equivalents
QUESTION_TYPES = {
    "MC": "multiple_choice_question",
    "MA": "multiple_answers_question",
    "TF": "true_false_question",
    "SA": "short_answer_question",
    "ESS": "essay_question",
    "FIB": "fill_in_multiple_blanks_question",
    "MAT": "matching_question",
    "NUM": "numerical_question",
}

# Reverse mapping
CANVAS_TO_CODE = {v: k for k, v in QUESTION_TYPES.items()}


@dataclass
class Answer:
    """Represents a single answer option."""
    text: str
    correct: bool = False
    match_target: Optional[str] = None  # For matching questions
    letter: Optional[str] = None  # a, b, c, etc.

    def to_canvas_answer(self, question_type: str, convert_markdown: bool = True) -> Dict[str, Any]:
        """
        Convert to Canvas API answer format.
        
        Args:
            question_type: The Canvas question type
            convert_markdown: If True, convert answer text from markdown to HTML
        """
        # For most answer types, convert markdown to HTML
        answer_text = self.text
        if convert_markdown and answer_text and question_type not in ("numerical_question",):
            # Simple inline conversion for answers (they're usually short)
            answer_text = answer_text.strip()
            if '**' in answer_text or '*' in answer_text or '`' in answer_text:
                answer_text = markdown_to_canvas_html(answer_text)
        
        if question_type == "matching_question":
            match_right = self.match_target or ""
            if convert_markdown and match_right and ('**' in match_right or '*' in match_right):
                match_right = markdown_to_canvas_html(match_right)
            return {
                "answer_match_left": answer_text,
                "answer_match_right": match_right,
            }
        elif question_type in ("short_answer_question", "fill_in_multiple_blanks_question"):
            # Short answers should remain plain text for matching
            return {
                "answer_text": self.text.strip(),
                "answer_weight": 100 if self.correct else 0,
            }
        elif question_type == "numerical_question":
            # Parse numerical value - handle ranges like "5-10" or "5 to 10"
            text = self.text.strip()
            try:
                if '-' in text and not text.startswith('-'):
                    parts = text.split('-')
                    low, high = float(parts[0]), float(parts[1])
                    mid = (low + high) / 2
                    margin = (high - low) / 2
                    return {
                        "numerical_answer_type": "range_answer",
                        "answer_exact": mid,
                        "answer_error_margin": margin,
                    }
                else:
                    return {
                        "numerical_answer_type": "exact_answer",
                        "answer_exact": float(text),
                        "answer_error_margin": 0,
                    }
            except ValueError:
                logger.warning(f"Could not parse numerical answer: {text}")
                return {
                    "numerical_answer_type": "exact_answer",
                    "answer_exact": 0,
                    "answer_error_margin": 0,
                }
        else:
            # MC, MA, TF
            return {
                "answer_text": answer_text,
                "answer_weight": 100 if self.correct else 0,
            }


@dataclass
class Question:
    """Represents a quiz question."""
    number: int
    type: str  # MC, MA, TF, SA, ESS, FIB, MAT, NUM
    text: str
    points: float = 1.0
    answers: List[Answer] = field(default_factory=list)
    correct_feedback: Optional[str] = None
    incorrect_feedback: Optional[str] = None
    neutral_feedback: Optional[str] = None
    question_id: Optional[int] = None  # Canvas question ID if synced
    margin: Optional[float] = None  # For numerical questions

    @property
    def canvas_type(self) -> str:
        """Get the Canvas API question type."""
        return QUESTION_TYPES.get(self.type, "multiple_choice_question")

    def to_canvas_question(self, convert_markdown: bool = True) -> Dict[str, Any]:
        """
        Convert to Canvas API question format.
        
        Args:
            convert_markdown: If True, convert question text from markdown to HTML
        """
        # Convert question text to HTML for Canvas
        question_text = self.text
        if convert_markdown and question_text:
            question_text = markdown_to_canvas_html(question_text)
        
        question_data = {
            "question_name": f"Question {self.number}",
            "question_text": question_text,
            "question_type": self.canvas_type,
            "points_possible": self.points,
            "answers": [a.to_canvas_answer(self.canvas_type, convert_markdown) for a in self.answers],
        }

        if self.correct_feedback:
            question_data["correct_comments"] = self.correct_feedback
        if self.incorrect_feedback:
            question_data["incorrect_comments"] = self.incorrect_feedback
        if self.neutral_feedback:
            question_data["neutral_comments"] = self.neutral_feedback

        # Handle numerical questions with margin
        if self.type == "NUM" and self.margin is not None and self.answers:
            for ans in question_data["answers"]:
                ans["answer_error_margin"] = self.margin

        return question_data


def parse_quiz_markdown(content: str) -> Tuple[Dict[str, Any], List[Question]]:
    """
    Parse a quiz markdown file into metadata and questions.

    Args:
        content: The markdown content of the quiz file

    Returns:
        Tuple of (metadata dict, list of Question objects)
    """
    # Parse frontmatter
    metadata, body = parse_frontmatter(content)

    # Parse questions from body
    questions = _parse_questions(body)

    return metadata, questions


def _parse_questions(body: str) -> List[Question]:
    """Parse questions from the body of a quiz markdown file."""
    questions = []

    # Split by question headers: ### N. [TYPE] or ### N.
    # Pattern matches: ### 1. [MC] Question text (2 pts)
    question_pattern = re.compile(
        r'^###\s+(\d+)\.\s*'  # Question number
        r'(?:\[([A-Z]{2,3})\]\s*)?'  # Optional type code
        r'(.+?)'  # Question text
        r'(?:\((\d+(?:\.\d+)?)\s*pts?\))?'  # Optional points
        r'\s*$',
        re.MULTILINE
    )

    # Find all question headers and their positions
    matches = list(question_pattern.finditer(body))

    for i, match in enumerate(matches):
        # Get content until next question or end
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        question_content = body[start:end].strip()

        # Parse question details
        number = int(match.group(1))
        qtype = match.group(2) or "MC"  # Default to multiple choice
        text = match.group(3).strip()
        points = float(match.group(4)) if match.group(4) else 1.0

        # Parse answers and feedback from question content
        answers, correct_fb, incorrect_fb, neutral_fb, margin = _parse_answers(
            question_content, qtype
        )

        question = Question(
            number=number,
            type=qtype,
            text=text,
            points=points,
            answers=answers,
            correct_feedback=correct_fb,
            incorrect_feedback=incorrect_fb,
            neutral_feedback=neutral_fb,
            margin=margin,
        )
        questions.append(question)

    return questions


def _parse_answers(content: str, qtype: str) -> Tuple[List[Answer], Optional[str], Optional[str], Optional[str], Optional[float]]:
    """
    Parse answers and feedback from question content.

    Returns:
        Tuple of (answers, correct_feedback, incorrect_feedback, neutral_feedback, margin)
    """
    answers = []
    correct_feedback = None
    incorrect_feedback = None
    neutral_feedback = None
    margin = None

    lines = content.split("\n")

    # Answer patterns
    # *a. Answer (correct)
    # a. Answer (incorrect)
    # *Answer (correct, for SA)
    # a. Left = Right (matching)
    lettered_answer = re.compile(r'^(\*)?([a-z])\.\s*(.+)$', re.IGNORECASE)
    unlettered_answer = re.compile(r'^(\*)\s*(.+)$')
    matching_answer = re.compile(r'^([a-z])\.\s*(.+?)\s*=\s*(.+)$', re.IGNORECASE)
    margin_pattern = re.compile(r'^margin:\s*(\d+(?:\.\d+)?)$', re.IGNORECASE)

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Check for feedback (blockquotes)
        if line.startswith(">"):
            feedback_text = line[1:].strip()
            if feedback_text.lower().startswith("correct:"):
                correct_feedback = feedback_text[8:].strip()
            elif feedback_text.lower().startswith("incorrect:"):
                incorrect_feedback = feedback_text[10:].strip()
            else:
                # Neutral feedback or continuation
                if neutral_feedback is None:
                    neutral_feedback = feedback_text
                else:
                    neutral_feedback += " " + feedback_text
            continue

        # Check for margin (numerical questions)
        margin_match = margin_pattern.match(line)
        if margin_match:
            margin = float(margin_match.group(1))
            continue

        # Check for matching question format
        if qtype == "MAT":
            mat_match = matching_answer.match(line)
            if mat_match:
                answers.append(Answer(
                    text=mat_match.group(2).strip(),
                    correct=True,  # All matching pairs are "correct"
                    match_target=mat_match.group(3).strip(),
                    letter=mat_match.group(1).lower(),
                ))
                continue

        # Check for lettered answer
        letter_match = lettered_answer.match(line)
        if letter_match:
            is_correct = letter_match.group(1) == "*"
            letter = letter_match.group(2).lower()
            text = letter_match.group(3).strip()
            answers.append(Answer(
                text=text,
                correct=is_correct,
                letter=letter,
            ))
            continue

        # Check for unlettered answer (SA, FIB)
        if qtype in ("SA", "FIB", "NUM"):
            unletter_match = unlettered_answer.match(line)
            if unletter_match:
                answers.append(Answer(
                    text=unletter_match.group(2).strip(),
                    correct=True,
                ))
                continue

    return answers, correct_feedback, incorrect_feedback, neutral_feedback, margin


def generate_quiz_markdown(
    metadata: Dict[str, Any],
    questions: List[Question],
    instructions: Optional[str] = None,
) -> str:
    """
    Generate a quiz markdown file from metadata and questions.

    Args:
        metadata: Quiz metadata (title, time_limit, etc.)
        questions: List of Question objects
        instructions: Optional instructions text

    Returns:
        Markdown string for the quiz
    """
    parts = []

    # Generate frontmatter
    parts.append(generate_frontmatter(metadata))

    # Title
    title = metadata.get("title", "Quiz")
    parts.append(f"# {title}\n")

    # Instructions section
    if instructions:
        parts.append("## Instructions\n")
        parts.append(instructions)
        parts.append("\n---\n")

    # Questions section
    parts.append("## Questions\n")

    for q in questions:
        parts.append(_generate_question_markdown(q))
        parts.append("\n---\n")

    return "\n".join(parts)


def _generate_question_markdown(question: Question) -> str:
    """Generate markdown for a single question."""
    lines = []

    # Question header
    points_str = f"({question.points} pts)" if question.points != 1 else "(1 pt)"
    lines.append(f"### {question.number}. [{question.type}] {question.text} {points_str}\n")

    # Answers
    if question.type == "MAT":
        # Matching format
        for ans in question.answers:
            letter = ans.letter or chr(ord('a') + question.answers.index(ans))
            lines.append(f"{letter}. {ans.text} = {ans.match_target}")
    elif question.type in ("SA", "FIB", "NUM"):
        # Short answer / fill in blank / numerical
        for ans in question.answers:
            lines.append(f"*{ans.text}")
        if question.margin is not None:
            lines.append(f"margin: {question.margin}")
    elif question.type == "ESS":
        # Essay has no answers
        pass
    else:
        # MC, MA, TF
        for ans in question.answers:
            letter = ans.letter or chr(ord('a') + question.answers.index(ans))
            prefix = "*" if ans.correct else ""
            lines.append(f"{prefix}{letter}. {ans.text}")

    # Feedback
    if question.correct_feedback:
        lines.append(f"\n> Correct: {question.correct_feedback}")
    if question.incorrect_feedback:
        lines.append(f"> Incorrect: {question.incorrect_feedback}")
    if question.neutral_feedback and not question.correct_feedback and not question.incorrect_feedback:
        lines.append(f"\n> {question.neutral_feedback}")

    return "\n".join(lines)


def questions_from_canvas(canvas_questions: List[Dict[str, Any]]) -> List[Question]:
    """
    Convert Canvas API question data to Question objects.

    Args:
        canvas_questions: List of question dicts from Canvas API

    Returns:
        List of Question objects
    """
    questions = []

    for i, cq in enumerate(canvas_questions, 1):
        qtype = CANVAS_TO_CODE.get(cq.get("question_type", ""), "MC")

        # Parse answers - clean HTML from answer text too
        answers = []
        for ans in cq.get("answers", []):
            if qtype == "MAT":
                left_text = ans.get("left", ans.get("answer_match_left", ""))
                right_text = ans.get("right", ans.get("answer_match_right", ""))
                answers.append(Answer(
                    text=clean_question_html(left_text) if left_text else "",
                    match_target=clean_question_html(right_text) if right_text else "",
                    correct=True,
                ))
            elif qtype == "NUM":
                # For numerical, keep the raw value
                answers.append(Answer(
                    text=str(ans.get("exact", ans.get("answer_exact", "0"))),
                    correct=True,
                ))
            else:
                is_correct = ans.get("weight", 0) > 0
                answer_text = ans.get("text", ans.get("answer_text", ""))
                # Clean HTML from answer text (but keep it simple for short answers)
                if qtype in ("SA", "FIB"):
                    clean_text = answer_text.strip() if answer_text else ""
                else:
                    clean_text = clean_question_html(answer_text) if answer_text else ""
                answers.append(Answer(
                    text=clean_text,
                    correct=is_correct,
                ))

        question = Question(
            number=i,
            type=qtype,
            text=clean_question_html(cq.get("question_text", "")),
            points=cq.get("points_possible", 1.0),
            answers=answers,
            correct_feedback=cq.get("correct_comments"),
            incorrect_feedback=cq.get("incorrect_comments"),
            neutral_feedback=cq.get("neutral_comments"),
            question_id=cq.get("id"),
        )
        questions.append(question)

    return questions


def quiz_metadata_from_canvas(canvas_quiz: Dict[str, Any], course_id: str) -> Dict[str, Any]:
    """
    Extract quiz metadata from Canvas API quiz data.

    Args:
        canvas_quiz: Quiz dict from Canvas API
        course_id: The course ID

    Returns:
        Metadata dict suitable for frontmatter
    """
    return {
        "title": canvas_quiz.get("title", ""),
        "quiz_id": canvas_quiz.get("id"),
        "course_id": course_id,
        "quiz_type": canvas_quiz.get("quiz_type", "assignment"),
        "time_limit": canvas_quiz.get("time_limit"),
        "shuffle_answers": canvas_quiz.get("shuffle_answers", False),
        "published": canvas_quiz.get("published", False),
        "points_possible": canvas_quiz.get("points_possible"),
        "allowed_attempts": canvas_quiz.get("allowed_attempts", 1),
        "description": canvas_quiz.get("description"),
        "due_at": canvas_quiz.get("due_at"),
        "lock_at": canvas_quiz.get("lock_at"),
        "unlock_at": canvas_quiz.get("unlock_at"),
    }
