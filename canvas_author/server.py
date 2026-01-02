"""
Canvas MCP Server

FastMCP server exposing Canvas LMS operations for wiki pages, assignments,
discussions, and rubrics with markdown support via pandoc.
"""

import json
import logging
from typing import Optional

from mcp.server import FastMCP

from . import pages, assignments, discussions, rubrics, sync, quizzes, quiz_sync, course_sync, rubric_sync, submission_sync, module_sync, assignment_sync
from .pandoc import is_pandoc_available

logger = logging.getLogger("canvas_author.server")

# Initialize MCP server
mcp = FastMCP(
    name="canvas-author",
    instructions="""Tools for managing Canvas LMS content including wiki pages,
assignments, discussions, and rubrics. Uses pandoc for markdown ↔ HTML conversion.
Supports two-way sync between Canvas and local markdown files.""",
)


# =============================================================================
# Wiki Pages Tools
# =============================================================================

@mcp.tool()
def list_pages(course_id: str) -> str:
    """
    List all wiki pages in a Canvas course.

    Args:
        course_id: Canvas course ID

    Returns:
        JSON list of pages with url, title, published status
    """
    try:
        result = pages.list_pages(course_id)
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def get_page(course_id: str, page_url: str, as_markdown: bool = True) -> str:
    """
    Get a wiki page's content.

    Args:
        course_id: Canvas course ID
        page_url: Page URL slug (e.g., 'syllabus')
        as_markdown: If true, return body as markdown (default). If false, return HTML.

    Returns:
        JSON with page data including title and body
    """
    try:
        result = pages.get_page(course_id, page_url, as_markdown=as_markdown)
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def create_page(
    course_id: str,
    title: str,
    body: str,
    published: bool = True
) -> str:
    """
    Create a new wiki page from markdown content.

    Args:
        course_id: Canvas course ID
        title: Page title
        body: Page body in markdown format
        published: Whether to publish the page (default: true)

    Returns:
        JSON with created page data
    """
    try:
        result = pages.create_page(
            course_id, title, body,
            from_markdown=True,
            published=published
        )
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def update_page(
    course_id: str,
    page_url: str,
    body: Optional[str] = None,
    title: Optional[str] = None,
    published: Optional[bool] = None
) -> str:
    """
    Update an existing wiki page with markdown content.

    Args:
        course_id: Canvas course ID
        page_url: Page URL slug
        body: New page body in markdown format (optional)
        title: New page title (optional)
        published: Whether to publish the page (optional)

    Returns:
        JSON with updated page data
    """
    try:
        result = pages.update_page(
            course_id, page_url,
            title=title,
            body=body,
            from_markdown=True,
            published=published
        )
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def delete_page(course_id: str, page_url: str) -> str:
    """
    Delete a wiki page.

    Args:
        course_id: Canvas course ID
        page_url: Page URL slug

    Returns:
        JSON with success status
    """
    try:
        pages.delete_page(course_id, page_url)
        return json.dumps({"success": True, "deleted": page_url})
    except Exception as e:
        return json.dumps({"error": str(e)})


# =============================================================================
# Page Sync Tools
# =============================================================================

@mcp.tool()
def pull_pages(
    course_id: str,
    output_dir: str,
    overwrite: bool = False
) -> str:
    """
    Pull all wiki pages from Canvas and save as local markdown files.

    Args:
        course_id: Canvas course ID
        output_dir: Directory to save markdown files
        overwrite: Overwrite existing files (default: false)

    Returns:
        JSON with results: pulled, skipped, errors
    """
    try:
        result = sync.pull_pages(course_id, output_dir, overwrite=overwrite)
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def push_pages(
    course_id: str,
    input_dir: str,
    create_missing: bool = True,
    update_existing: bool = True
) -> str:
    """
    Push local markdown files to Canvas as wiki pages.

    Args:
        course_id: Canvas course ID
        input_dir: Directory containing markdown files
        create_missing: Create pages that don't exist on Canvas (default: true)
        update_existing: Update pages that already exist (default: true)

    Returns:
        JSON with results: created, updated, skipped, errors
    """
    try:
        result = sync.push_pages(
            course_id, input_dir,
            create_missing=create_missing,
            update_existing=update_existing
        )
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def sync_status(course_id: str, local_dir: str) -> str:
    """
    Check sync status between Canvas pages and local files.

    Args:
        course_id: Canvas course ID
        local_dir: Directory containing local markdown files

    Returns:
        JSON with status: canvas_only, local_only, both, summary
    """
    try:
        result = sync.sync_status(course_id, local_dir)
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def init_course(course_id: str, directory: str) -> str:
    """
    Initialize a local directory for a Canvas course.

    Creates course configuration files, directory structure, and pulls initial content.

    Args:
        course_id: Canvas course ID
        directory: Local directory path to initialize

    Returns:
        JSON with initialization results including course name and files created
    """
    try:
        result = course_sync.init_course(course_id, directory)
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


# =============================================================================
# Course & Assignment Tools
# =============================================================================

@mcp.tool()
def list_courses(enrollment_state: str = "active") -> str:
    """
    List courses where you are a teacher.

    Args:
        enrollment_state: 'active' for current courses, 'all' for all courses

    Returns:
        JSON list of courses with id, name, course_code
    """
    try:
        result = assignments.list_courses(enrollment_state=enrollment_state)
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def list_assignments(course_id: str) -> str:
    """
    List all assignments in a course.

    Args:
        course_id: Canvas course ID

    Returns:
        JSON list of assignments with id, name, due_at, points_possible
    """
    try:
        result = assignments.list_assignments(course_id)
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def get_assignment(course_id: str, assignment_id: str) -> str:
    """
    Get details for a specific assignment.

    Args:
        course_id: Canvas course ID
        assignment_id: Canvas assignment ID

    Returns:
        JSON with assignment details including rubric and discussion info
    """
    try:
        result = assignments.get_assignment(course_id, assignment_id)
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def list_submissions(course_id: str, assignment_id: str) -> str:
    """
    List all submissions for an assignment.

    Args:
        course_id: Canvas course ID
        assignment_id: Canvas assignment ID

    Returns:
        JSON list of submissions with user info, grades, and status
    """
    try:
        result = assignments.list_submissions(course_id, assignment_id)
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def get_submission(course_id: str, assignment_id: str, user_id: str) -> str:
    """
    Get a specific student's submission.

    Args:
        course_id: Canvas course ID
        assignment_id: Canvas assignment ID
        user_id: Student user ID

    Returns:
        JSON with submission details including rubric assessment
    """
    try:
        result = assignments.get_submission(course_id, assignment_id, user_id)
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def pull_assignments(
    course_id: str,
    output_dir: str,
    overwrite: bool = False
) -> str:
    """
    Pull all assignments from Canvas and save as local markdown files.

    Args:
        course_id: Canvas course ID
        output_dir: Directory to save files (assignments subfolder will be created)
        overwrite: Overwrite existing files (default: false)

    Returns:
        JSON with results: pulled, skipped, errors
    """
    try:
        result = assignment_sync.pull_assignments(course_id, output_dir, overwrite=overwrite)
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def push_assignments(
    course_id: str,
    input_dir: str,
    update_existing: bool = True
) -> str:
    """
    Push local markdown files to Canvas as assignment description updates.

    Args:
        course_id: Canvas course ID
        input_dir: Directory containing assignment markdown files
        update_existing: Update assignments that already exist (default: true)

    Returns:
        JSON with results: updated, skipped, errors
    """
    try:
        result = assignment_sync.push_assignments(
            course_id, input_dir,
            update_existing=update_existing
        )
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def assignment_sync_status(course_id: str, local_dir: str) -> str:
    """
    Compare Canvas assignments with local files.

    Args:
        course_id: Canvas course ID
        local_dir: Local directory to check

    Returns:
        JSON with synced, canvas_only, local_only lists
    """
    try:
        result = assignment_sync.assignment_sync_status(course_id, local_dir)
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


# =============================================================================
# Discussion Tools
# =============================================================================

@mcp.tool()
def list_discussions(course_id: str) -> str:
    """
    List all discussion topics in a course.

    Args:
        course_id: Canvas course ID

    Returns:
        JSON list of discussion topics
    """
    try:
        result = discussions.list_discussions(course_id)
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def list_discussion_assignments(course_id: str) -> str:
    """
    List all graded discussion assignments in a course.

    Args:
        course_id: Canvas course ID

    Returns:
        JSON list of discussion assignments with topic_id
    """
    try:
        result = discussions.list_discussion_assignments(course_id)
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def get_discussion_posts(course_id: str, discussion_id: str) -> str:
    """
    Get all posts and replies for a discussion topic.

    Args:
        course_id: Canvas course ID
        discussion_id: Discussion topic ID

    Returns:
        JSON with topic info and all entries with replies (as markdown)
    """
    try:
        result = discussions.get_discussion_posts(course_id, discussion_id, as_markdown=True)
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def get_posts_by_user(course_id: str, discussion_id: str) -> str:
    """
    Get discussion posts organized by user.

    Args:
        course_id: Canvas course ID
        discussion_id: Discussion topic ID

    Returns:
        JSON mapping user_id to their posts and replies
    """
    try:
        result = discussions.get_posts_by_user(course_id, discussion_id, as_markdown=True)
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


# =============================================================================
# Rubric Tools
# =============================================================================

@mcp.tool()
def get_rubric(course_id: str, assignment_id: str) -> str:
    """
    Get the rubric for an assignment.

    Args:
        course_id: Canvas course ID
        assignment_id: Canvas assignment ID

    Returns:
        JSON with rubric data including criteria and ratings
    """
    try:
        result = rubrics.get_rubric(course_id, assignment_id)
        if result is None:
            return json.dumps({"error": "No rubric found for this assignment"})
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
async def update_rubric(
    course_id: str,
    assignment_id: str,
    rubric_data: str
) -> str:
    """
    Update an assignment's rubric.

    Args:
        course_id: Canvas course ID
        assignment_id: Canvas assignment ID
        rubric_data: JSON string with rubric criteria

    Returns:
        JSON with success status and updated rubric
    """
    try:
        data = json.loads(rubric_data)
        success, result = await rubrics.update_rubric(
            course_id, assignment_id,
            rubric_data=data.get('data'),
            rubric_settings=data.get('rubric_settings')
        )
        if success:
            return json.dumps({"success": True, "rubric": result}, indent=2)
        else:
            return json.dumps({"success": False, "error": result})
    except json.JSONDecodeError as e:
        return json.dumps({"error": f"Invalid JSON: {e}"})
    except Exception as e:
        return json.dumps({"error": str(e)})


# =============================================================================
# Rubric Sync Tools
# =============================================================================

@mcp.tool()
def pull_rubrics(
    course_id: str,
    output_dir: str,
    overwrite: bool = False
) -> str:
    """
    Pull all rubrics from Canvas assignments and save as local YAML files.

    Args:
        course_id: Canvas course ID
        output_dir: Directory to save rubric YAML files
        overwrite: Overwrite existing files (default: false)

    Returns:
        JSON with results: pulled, skipped, no_rubric, errors
    """
    try:
        result = rubric_sync.pull_rubrics(course_id, output_dir, overwrite=overwrite)
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def push_rubrics(
    course_id: str,
    input_dir: str,
    create_only: bool = False
) -> str:
    """
    Push local YAML rubric files to Canvas.

    Args:
        course_id: Canvas course ID
        input_dir: Directory containing rubric YAML files (*.rubric.yaml)
        create_only: Only create new rubrics, don't update existing (default: false)

    Returns:
        JSON with results: created, updated, skipped, errors
    """
    try:
        result = rubric_sync.push_rubrics(
            course_id, input_dir,
            create_only=create_only
        )
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def rubric_sync_status(course_id: str, local_dir: str) -> str:
    """
    Check sync status between Canvas rubrics and local YAML files.

    Args:
        course_id: Canvas course ID
        local_dir: Directory containing local rubric files

    Returns:
        JSON with status: canvas_only, local_only, synced, summary
    """
    try:
        result = rubric_sync.rubric_sync_status(course_id, local_dir)
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


# =============================================================================
# Submission Sync Tools
# =============================================================================

@mcp.tool()
def pull_submissions(
    course_id: str,
    assignment_id: str,
    output_dir: str,
    include_attachments: bool = True,
    anonymize: bool = False
) -> str:
    """
    Pull all submissions for an assignment from Canvas.

    Downloads submissions with optional attachments. Use anonymize=true for blind grading.

    Args:
        course_id: Canvas course ID
        assignment_id: Canvas assignment ID
        output_dir: Directory to save submissions
        include_attachments: Download attachment files (default: true)
        anonymize: Anonymize student identities for blind grading (default: false)

    Returns:
        JSON with results: pulled count, attachments downloaded, directory path
    """
    try:
        result = submission_sync.pull_submissions(
            course_id, assignment_id, output_dir,
            include_attachments=include_attachments,
            anonymize=anonymize
        )
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def submission_status(
    course_id: str,
    assignment_id: str,
    local_dir: Optional[str] = None
) -> str:
    """
    Get submission status for an assignment.

    Shows counts of submitted, graded, needs grading, late, missing submissions.

    Args:
        course_id: Canvas course ID
        assignment_id: Canvas assignment ID
        local_dir: Optional directory to check for local downloads

    Returns:
        JSON with submission counts and grading status
    """
    try:
        result = submission_sync.submission_status(
            course_id, assignment_id,
            local_dir=local_dir
        )
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


# =============================================================================
# Quiz Tools
# =============================================================================

@mcp.tool()
def list_quizzes(course_id: str) -> str:
    """
    List all quizzes in a Canvas course.

    Args:
        course_id: Canvas course ID

    Returns:
        JSON list of quizzes with id, title, points_possible, published
    """
    try:
        result = quizzes.list_quizzes(course_id)
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def get_quiz(course_id: str, quiz_id: str) -> str:
    """
    Get details for a specific quiz.

    Args:
        course_id: Canvas course ID
        quiz_id: Canvas quiz ID

    Returns:
        JSON with quiz details including settings and question count
    """
    try:
        result = quizzes.get_quiz(course_id, quiz_id)
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def get_quiz_questions(course_id: str, quiz_id: str) -> str:
    """
    Get all questions for a quiz.

    Args:
        course_id: Canvas course ID
        quiz_id: Canvas quiz ID

    Returns:
        JSON list of questions with type, text, answers, and points
    """
    try:
        result = quizzes.get_quiz_questions(course_id, quiz_id)
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def pull_quizzes(
    course_id: str,
    output_dir: str,
    overwrite: bool = False
) -> str:
    """
    Pull all quizzes from Canvas and save as local markdown files.

    Args:
        course_id: Canvas course ID
        output_dir: Directory to save quiz markdown files
        overwrite: Overwrite existing files (default: false)

    Returns:
        JSON with results: pulled, skipped, errors
    """
    try:
        result = quiz_sync.pull_quizzes(course_id, output_dir, overwrite=overwrite)
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def push_quizzes(
    course_id: str,
    input_dir: str,
    create_missing: bool = True,
    update_existing: bool = True
) -> str:
    """
    Push local quiz markdown files to Canvas.

    Args:
        course_id: Canvas course ID
        input_dir: Directory containing quiz markdown files (*.quiz.md)
        create_missing: Create quizzes that don't exist on Canvas (default: true)
        update_existing: Update quizzes that already exist (default: true)

    Returns:
        JSON with results: created, updated, skipped, errors
    """
    try:
        result = quiz_sync.push_quizzes(
            course_id, input_dir,
            create_missing=create_missing,
            update_existing=update_existing
        )
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def quiz_sync_status(course_id: str, local_dir: str) -> str:
    """
    Check sync status between Canvas quizzes and local files.

    Args:
        course_id: Canvas course ID
        local_dir: Directory containing local quiz files

    Returns:
        JSON with status: canvas_only, local_only, synced, summary
    """
    try:
        result = quiz_sync.quiz_sync_status(course_id, local_dir)
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


# =============================================================================
# Module Sync Tools
# =============================================================================

@mcp.tool()
def pull_modules(
    course_id: str,
    output_dir: str
) -> str:
    """
    Pull all modules from Canvas and save as local YAML file (modules.yaml).

    Args:
        course_id: Canvas course ID
        output_dir: Directory to save modules.yaml file

    Returns:
        JSON with results: modules pulled, items count
    """
    try:
        result = module_sync.pull_modules(course_id, output_dir)
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def push_modules(
    course_id: str,
    input_dir: str,
    create_missing: bool = True,
    update_existing: bool = True
) -> str:
    """
    Push local modules.yaml to Canvas.

    Args:
        course_id: Canvas course ID
        input_dir: Directory containing modules.yaml file
        create_missing: Create modules that don't exist on Canvas (default: true)
        update_existing: Update modules that already exist (default: true)

    Returns:
        JSON with results: created, updated, skipped, errors
    """
    try:
        result = module_sync.push_modules(
            course_id, input_dir,
            create_missing=create_missing,
            update_existing=update_existing
        )
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def module_sync_status(course_id: str, local_dir: str) -> str:
    """
    Check sync status between Canvas modules and local modules.yaml.

    Args:
        course_id: Canvas course ID
        local_dir: Directory containing local modules.yaml file

    Returns:
        JSON with status: canvas_only, local_only, synced, summary
    """
    try:
        result = module_sync.module_sync_status(course_id, local_dir)
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


# =============================================================================
# Utility Tools
# =============================================================================

@mcp.tool()
def check_pandoc() -> str:
    """
    Check if pandoc is available for markdown conversion.

    Returns:
        JSON with pandoc availability status
    """
    available = is_pandoc_available()
    return json.dumps({
        "pandoc_available": available,
        "message": "Pandoc is ready" if available else "Pandoc is not installed. Install with: apt install pandoc"
    })


def main():
    """Run the Canvas MCP server."""
    print("Starting Canvas MCP Server...")
    print("Tools: list_pages, get_page, create_page, update_page, delete_page,")
    print("       pull_pages, push_pages, sync_status,")
    print("       list_quizzes, get_quiz, get_quiz_questions,")
    print("       pull_quizzes, push_quizzes, quiz_sync_status,")
    print("       pull_modules, push_modules, module_sync_status,")
    print("       list_courses, list_assignments, get_assignment, list_submissions,")
    print("       list_discussions, get_discussion_posts,")
    print("       get_rubric, update_rubric")
    print()
    mcp.run()


if __name__ == "__main__":
    main()
