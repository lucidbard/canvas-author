"""
Canvas MCP Server

FastMCP server exposing Canvas LMS operations for wiki pages, assignments,
discussions, and rubrics with markdown support via pandoc.
"""

import json
import logging
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime, timedelta

from mcp.server import FastMCP

from . import pages, assignments, assignment_groups, discussions, rubrics, sync, quizzes, quiz_sync, course_sync, rubric_sync, submission_sync, module_sync, assignment_sync, files as files_module, discussion_sync, announcement_sync, draft_storage
from .pandoc import is_pandoc_available
from .workflow import (
    WorkflowManager,
    WorktreeReviewSession,
    ItemReview,
    ReviewPass,
    create_agent_worktree
)

logger = logging.getLogger("canvas_author.server")

# Initialize MCP server
mcp = FastMCP(
    name="canvas-author",
    instructions="""Tools for managing Canvas LMS content including wiki pages,
assignments, discussions, and rubrics. Uses pandoc for markdown ↔ HTML conversion.
Supports two-way sync between Canvas and local markdown files.""",
)

# Simple in-memory cache for submissions with TTL
# Format: {cache_key: (data, timestamp)}
_submissions_cache: Dict[str, Tuple[Any, datetime]] = {}
_CACHE_TTL_SECONDS = 30  # Cache for 30 seconds to avoid redundant API calls


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


@mcp.tool()
def bulk_delete_pages(course_id: str, page_urls: str) -> str:
    """
    Delete multiple wiki pages efficiently.

    Args:
        course_id: Canvas course ID
        page_urls: Comma-separated list of page URL slugs to delete

    Returns:
        JSON with deleted, failed, and errors lists
    """
    try:
        urls_list = [url.strip() for url in page_urls.split(",")]
        result = pages.bulk_delete_pages(course_id, urls_list)
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


# =============================================================================
# Page Sync Tools
# =============================================================================

@mcp.tool()
def pull_pages(
    course_id: str,
    output_dir: str,
    overwrite: bool = False,
    download_images: bool = True
) -> str:
    """
    Pull all wiki pages from Canvas and save as local markdown files.
    Images are downloaded to files/ directory with URLs rewritten to relative paths.

    Args:
        course_id: Canvas course ID
        output_dir: Directory to save markdown files
        overwrite: Overwrite existing files (default: false)
        download_images: Download embedded images to files/ directory (default: true)

    Returns:
        JSON with results: pulled, skipped, errors, images_downloaded
    """
    try:
        result = sync.pull_pages(course_id, output_dir, overwrite=overwrite, download_images=download_images)
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def push_pages(
    course_id: str,
    input_dir: str,
    create_missing: bool = True,
    update_existing: bool = True,
    upload_images: bool = True,
    validate_links: bool = True
) -> str:
    """
    Push local markdown files to Canvas as wiki pages.
    Local images are uploaded to Canvas with URLs rewritten to Canvas paths.

    Validates internal links before pushing to prevent broken links on Canvas.
    If validation fails, returns an error without pushing any pages.

    Args:
        course_id: Canvas course ID
        input_dir: Directory containing markdown files
        create_missing: Create pages that don't exist on Canvas (default: true)
        update_existing: Update pages that already exist (default: true)
        upload_images: Upload local images to Canvas (default: true)
        validate_links: Validate internal links before pushing (default: true)

    Returns:
        JSON with results: created, updated, skipped, errors, images_uploaded, validation

    Raises:
        ValueError: If validate_links=true and broken links are found
    """
    try:
        result = sync.push_pages(
            course_id, input_dir,
            create_missing=create_missing,
            update_existing=update_existing,
            upload_images=upload_images,
            validate_links=validate_links
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


@mcp.tool()
def pull_course(course_id: str, directory: str) -> str:
    """
    Pull course settings from Canvas to local course.yaml file.

    Downloads course configuration including name, dates, visibility settings,
    and syllabus to a local YAML file for editing and version control.

    Args:
        course_id: Canvas course ID
        directory: Local directory path (course.yaml will be created here)

    Returns:
        JSON with pull results including file path and settings count
    """
    try:
        result = course_sync.pull_course(course_id, directory, interactive=False)
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def push_course(directory: str) -> str:
    """
    Push local course.yaml settings to Canvas.

    Updates Canvas course configuration from local YAML file.
    The file must contain a valid course_id.

    Args:
        directory: Local directory path containing course.yaml

    Returns:
        JSON with push results including updated settings count
    """
    try:
        result = course_sync.push_course(directory, interactive=False)
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def course_status(course_id: str, directory: str) -> str:
    """
    Compare local course.yaml with Canvas settings.

    Shows differences between local settings and Canvas configuration.

    Args:
        course_id: Canvas course ID
        directory: Local directory path containing course.yaml

    Returns:
        JSON with differences and sync status
    """
    try:
        result = course_sync.course_status(course_id, directory)
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


# =============================================================================
# Assignment Groups Tools
# =============================================================================

@mcp.tool()
def list_assignment_groups(course_id: str) -> str:
    """
    List all assignment groups in a course.

    Args:
        course_id: Canvas course ID

    Returns:
        JSON list of assignment groups with id, name, position, group_weight
    """
    try:
        result = assignment_groups.list_assignment_groups(course_id)
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
        error_str = str(e)
        # Check for expired or invalid token errors
        if "expired" in error_str.lower() or "invalid" in error_str.lower() or "401" in error_str:
            return json.dumps({
                "error": error_str,
                "error_type": "authentication",
                "message": "Your Canvas API token has expired or is invalid. Please update your token."
            })
        return json.dumps({"error": error_str})


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
def list_submissions(course_id: str, assignment_id: str, anonymize: bool = True) -> str:
    """
    List all submissions for an assignment.
    
    NOTE: By default, student identities are anonymized to protect privacy when
    using AI assistants. Student names are replaced with anonymous IDs (e.g., "Student 1").
    Use anonymize=False only when working locally without AI review.

    Args:
        course_id: Canvas course ID
        assignment_id: Canvas assignment ID
        anonymize: Whether to anonymize student identities (default: True for AI privacy)

    Returns:
        JSON list of submissions with user info, grades, and status
    """
    try:
        result = assignments.list_submissions(course_id, assignment_id)
        
        # Anonymize student information for AI review
        if anonymize:
            anonymized = []
            for idx, submission in enumerate(result, 1):
                anon_sub = submission.copy()
                # Replace user info with anonymous ID
                if 'user' in anon_sub:
                    anon_sub['user'] = {
                        'id': f'anon_{idx}',
                        'name': f'Student {idx}',
                        'sortable_name': f'Student {idx}'
                    }
                # Keep the anonymous user_id for reference
                anon_sub['user_id'] = f'anon_{idx}'
                anonymized.append(anon_sub)
            result = anonymized
        
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def get_submission(course_id: str, assignment_id: str, user_id: str, anonymize: bool = True) -> str:
    """
    Get a specific student's submission.
    
    NOTE: By default, student identity is anonymized to protect privacy when
    using AI assistants. Use anonymize=False only when working locally without AI review.

    Args:
        course_id: Canvas course ID
        assignment_id: Canvas assignment ID
        user_id: Student user ID
        anonymize: Whether to anonymize student identity (default: True for AI privacy)

    Returns:
        JSON with submission details including rubric assessment
    """
    try:
        result = assignments.get_submission(course_id, assignment_id, user_id)
        
        # Anonymize student information for AI review
        if anonymize and result:
            if 'user' in result:
                result['user'] = {
                    'id': 'anon_user',
                    'name': 'Student',
                    'sortable_name': 'Student'
                }
            result['user_id'] = 'anon_user'
        
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def update_grade(
    course_id: str,
    assignment_id: str,
    user_id: str,
    grade: str,
    comment: str = ""
) -> str:
    """
    Update a student's grade for an assignment.

    Args:
        course_id: Canvas course ID
        assignment_id: Canvas assignment ID
        user_id: Student user ID
        grade: Grade to assign (number or letter grade)
        comment: Optional comment for the student

    Returns:
        JSON with updated submission info
    """
    try:
        result = assignments.update_grade(course_id, assignment_id, user_id, grade, comment)
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def delete_assignment(course_id: str, assignment_id: str) -> str:
    """
    Delete an assignment from Canvas.

    Args:
        course_id: Canvas course ID
        assignment_id: Canvas assignment ID

    Returns:
        JSON with deletion status
    """
    try:
        result = assignments.delete_assignment(course_id, assignment_id)
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def delete_page(course_id: str, page_id: str) -> str:
    """
    Delete a wiki page from Canvas.

    Args:
        course_id: Canvas course ID
        page_id: Canvas page ID (numeric or URL)

    Returns:
        JSON with deletion status
    """
    try:
        result = pages.delete_page(course_id, page_id)
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
    create_missing: bool = True,
    update_existing: bool = True
) -> str:
    """
    Push local markdown files to Canvas as assignments.

    Can create new assignments or update existing ones. If a markdown file has no
    assignment_id in frontmatter and create_missing is true, a new assignment will
    be created in Canvas and the file will be updated with the new ID.

    Args:
        course_id: Canvas course ID
        input_dir: Directory containing assignment markdown files
        create_missing: Create assignments that don't exist on Canvas (default: true)
        update_existing: Update assignments that already exist (default: true)

    Returns:
        JSON with results: created, updated, skipped, errors
    """
    try:
        result = assignment_sync.push_assignments(
            course_id, input_dir,
            create_missing=create_missing,
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


@mcp.tool()
def create_discussion(
    course_id: str,
    title: str,
    message: str,
    published: bool = True,
    require_initial_post: bool = False,
    is_announcement: bool = False
) -> str:
    """
    Create a new discussion topic or announcement.

    Args:
        course_id: Canvas course ID
        title: Discussion title
        message: Discussion message (HTML or markdown)
        published: Whether to publish immediately (default: True)
        require_initial_post: Students must post before seeing others (default: False)
        is_announcement: Create as announcement instead of discussion (default: False)

    Returns:
        JSON with created discussion data including id and html_url
    """
    try:
        result = discussions.create_discussion(
            course_id,
            title,
            message,
            published=published,
            require_initial_post=require_initial_post,
            is_announcement=is_announcement
        )
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def update_discussion(
    course_id: str,
    discussion_id: str,
    title: Optional[str] = None,
    message: Optional[str] = None,
    published: Optional[bool] = None
) -> str:
    """
    Update an existing discussion topic.

    Args:
        course_id: Canvas course ID
        discussion_id: Discussion topic ID
        title: New title (optional)
        message: New message (HTML or markdown, optional)
        published: Publication status (optional)

    Returns:
        JSON with updated discussion data
    """
    try:
        result = discussions.update_discussion(
            course_id,
            discussion_id,
            title=title,
            message=message,
            published=published
        )
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def delete_discussion(course_id: str, discussion_id: str) -> str:
    """
    Delete a discussion topic.

    Args:
        course_id: Canvas course ID
        discussion_id: Discussion topic ID

    Returns:
        JSON with success status
    """
    try:
        result = discussions.delete_discussion(course_id, discussion_id)
        return json.dumps({"success": result})
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def pull_discussions(course_id: str, output_dir: str, overwrite: bool = False) -> str:
    """
    Pull all discussions from Canvas to local markdown files.

    Args:
        course_id: Canvas course ID
        output_dir: Directory to save files (discussions subfolder will be created)
        overwrite: Overwrite existing files (default: False)

    Returns:
        JSON with results: pulled, skipped, errors
    """
    try:
        result = discussion_sync.pull_discussions(
            course_id,
            output_dir,
            overwrite=overwrite,
            only_announcements=False
        )
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def push_discussions(
    course_id: str,
    input_dir: str,
    create_missing: bool = True,
    update_existing: bool = True
) -> str:
    """
    Push local markdown files to Canvas as discussions.

    Args:
        course_id: Canvas course ID
        input_dir: Directory containing discussion markdown files
        create_missing: Create discussions that don't exist (default: True)
        update_existing: Update existing discussions (default: True)

    Returns:
        JSON with results: created, updated, skipped, errors
    """
    try:
        result = discussion_sync.push_discussions(
            course_id,
            input_dir,
            create_missing=create_missing,
            update_existing=update_existing,
            is_announcements=False
        )
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def pull_announcements(course_id: str, output_dir: str, overwrite: bool = False, limit: int = 50) -> str:
    """
    Pull announcements from Canvas to local markdown files.

    Args:
        course_id: Canvas course ID
        output_dir: Directory to save files (announcements subfolder will be created)
        overwrite: Overwrite existing files (default: False)
        limit: Maximum number of announcements to pull (default: 50)

    Returns:
        JSON with results: pulled, skipped, errors
    """
    try:
        result = announcement_sync.pull_announcements(
            course_id,
            output_dir,
            overwrite=overwrite,
            limit=limit
        )
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def push_announcements(
    course_id: str,
    input_dir: str,
    create_missing: bool = True,
    update_existing: bool = True
) -> str:
    """
    Push local markdown files to Canvas as announcements.

    Args:
        course_id: Canvas course ID
        input_dir: Directory containing announcement markdown files
        create_missing: Create announcements that don't exist (default: True)
        update_existing: Update existing announcements (default: True)

    Returns:
        JSON with results: created, updated, skipped, errors
    """
    try:
        result = announcement_sync.push_announcements(
            course_id,
            input_dir,
            create_missing=create_missing,
            update_existing=update_existing
        )
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
async def push_rubrics(
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
        result = await rubric_sync.push_rubrics(
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


@mcp.tool()
def get_all_submissions_hierarchical(
    course_id: str,
    include_user: bool = True,
    include_rubric: bool = False,
    force_refresh: bool = False
) -> str:
    """
    Get all submissions organized hierarchically by assignment.

    Returns all assignments with their submissions pre-loaded in a single call,
    eliminating the need to click into each assignment individually.

    Uses a 30-second cache to avoid redundant API calls. Set force_refresh=True
    to bypass cache and fetch fresh data.

    Perfect for UI views that show:
    - Assignment 1
      - Student A submission
      - Student B submission
    - Assignment 2
      - Student A submission
      - Student B submission

    Args:
        course_id: Canvas course ID
        include_user: Include user/student info in submissions (default: true)
        include_rubric: Include rubric assessment data (default: false)
        force_refresh: Force refresh from API, bypassing cache (default: false)

    Returns:
        JSON array of assignments, each containing:
        - id, name, due_at, points_possible (assignment metadata)
        - submissions: Array of submission objects with student info
        - submission_counts: Summary counts (submitted, graded, needs_grading, etc.)
    """
    cache_key = f"submissions_hierarchical:{course_id}:{include_user}:{include_rubric}"

    # Check cache unless force refresh
    if not force_refresh and cache_key in _submissions_cache:
        cached_data, cached_time = _submissions_cache[cache_key]
        age_seconds = (datetime.now() - cached_time).total_seconds()

        if age_seconds < _CACHE_TTL_SECONDS:
            logger.info(f"Returning cached submissions (age: {age_seconds:.1f}s)")
            return json.dumps(cached_data, indent=2)
        else:
            logger.info(f"Cache expired (age: {age_seconds:.1f}s), fetching fresh data")

    try:
        result = submission_sync.get_all_submissions_hierarchical(
            course_id,
            include_user=include_user,
            include_rubric=include_rubric
        )

        # Cache the result
        _submissions_cache[cache_key] = (result, datetime.now())
        logger.info(f"Cached fresh submissions data for course {course_id}")

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
    overwrite: bool = False,
    download_images: bool = True
) -> str:
    """
    Pull all quizzes from Canvas and save as local markdown files.
    Images are downloaded to files/ directory with URLs rewritten to relative paths.

    Args:
        course_id: Canvas course ID
        output_dir: Directory to save quiz markdown files
        overwrite: Overwrite existing files (default: false)
        download_images: Download embedded images to files/ directory (default: true)

    Returns:
        JSON with results: pulled, skipped, errors, images_downloaded
    """
    try:
        result = quiz_sync.pull_quizzes(course_id, output_dir, overwrite=overwrite, download_images=download_images)
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def push_quizzes(
    course_id: str,
    input_dir: str,
    create_missing: bool = True,
    update_existing: bool = True,
    upload_images: bool = True
) -> str:
    """
    Push local quiz markdown files to Canvas.
    Local images are uploaded to Canvas with URLs rewritten to Canvas paths.

    Args:
        course_id: Canvas course ID
        input_dir: Directory containing quiz markdown files (*.quiz.md)
        create_missing: Create quizzes that don't exist on Canvas (default: true)
        update_existing: Update quizzes that already exist (default: true)
        upload_images: Upload local images to Canvas (default: true)

    Returns:
        JSON with results: created, updated, skipped, errors, images_uploaded
    """
    try:
        result = quiz_sync.push_quizzes(
            course_id, input_dir,
            create_missing=create_missing,
            update_existing=update_existing,
            upload_images=upload_images
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


@mcp.tool()
def list_course_files(course_id: str) -> str:
    """
    List all files in a Canvas course.

    Args:
        course_id: Canvas course ID

    Returns:
        JSON list of files with id, display_name, size, content_type
    """
    try:
        result = files_module.list_course_files(course_id)
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def pull_course_files(
    course_id: str,
    output_dir: str,
    size_threshold_mb: float = 2.0,
    overwrite: bool = False
) -> str:
    """
    Pull all files from a Canvas course to local directory.

    Large files (exceeding size_threshold_mb) create placeholder files instead
    of downloading immediately. Use download_pending_files() to get them later.

    Args:
        course_id: Canvas course ID
        output_dir: Directory to save files (files go in {output_dir}/files/)
        size_threshold_mb: Max file size in MB to auto-download (default: 2.0)
        overwrite: Overwrite existing files (default: false)

    Returns:
        JSON with results: downloaded, pending, skipped, errors
    """
    try:
        threshold_bytes = int(size_threshold_mb * 1024 * 1024)
        result = files_module.pull_course_files(
            course_id, output_dir,
            size_threshold=threshold_bytes,
            overwrite=overwrite
        )
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def download_pending_files(
    course_id: str,
    files_dir: str,
    file_ids: Optional[str] = None
) -> str:
    """
    Download files that were skipped due to size during pull.

    Args:
        course_id: Canvas course ID
        files_dir: Directory containing the files/ folder with placeholders
        file_ids: Optional comma-separated list of file IDs to download (default: all pending)

    Returns:
        JSON with results: downloaded, errors
    """
    try:
        ids_list = file_ids.split(",") if file_ids else None
        result = files_module.download_pending_files(course_id, files_dir, file_ids=ids_list)
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def list_pending_files(files_dir: str) -> str:
    """
    List files that have placeholders but haven't been downloaded yet.

    Args:
        files_dir: Directory to check for pending files

    Returns:
        JSON list of pending files with size and metadata
    """
    try:
        result = files_module.list_pending_files(files_dir)
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


# =============================================================================
# Workflow & Review Tools (Multi-Agent Review System)
# =============================================================================

@mcp.tool()
def create_agent_worktree_tool(
    course_id: str,
    course_path: str,
    agent_name: str,
    agent_role: str,
    scope: str
) -> str:
    """
    Create a new git worktree for an agent with role-based tool restrictions.
    
    Args:
        course_id: Canvas course ID
        course_path: Path to course directory
        agent_name: Name/ID of the agent (e.g., 'copilot-grading')
        agent_role: Role of agent (content_agent, style_agent, fact_check_agent, consistency_agent, approval_agent)
        scope: Comma-separated list of content types (e.g., 'pages,quizzes')
    
    Returns:
        JSON with worktree info and allowed/restricted tools
    """
    try:
        scope_list = [s.strip() for s in scope.split(",")]
        result = create_agent_worktree(course_id, course_path, agent_name, agent_role, scope_list)
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def submit_style_review(
    course_id: str,
    course_path: str,
    worktree_name: str,
    item_id: str,
    item_title: str,
    item_type: str,
    canvas_id: str,
    file_path: str,
    agent_id: str,
    decision: str,
    reasoning: str,
    severity: str = "medium"
) -> str:
    """
    Submit a style review pass for an item (tone, grammar, consistency).
    
    Args:
        course_id: Canvas course ID
        course_path: Path to course directory
        worktree_name: Name of the worktree being reviewed
        item_id: Unified item ID (e.g., 'page:12345')
        item_title: Human-readable item title
        item_type: Type of item (page, quiz, assignment, rubric)
        canvas_id: Canvas object ID
        file_path: Local file path
        agent_id: ID of reviewing agent
        decision: approved, rejected, needs_revision
        reasoning: Explanation of the review decision
        severity: low, medium, high
    
    Returns:
        JSON with review result
    """
    try:
        wm = WorkflowManager(course_path)
        
        # Create or load session
        session = None
        for review_file in wm.reviews_dir.glob(f"{worktree_name}_*.json"):
            try:
                session = wm.load_review_session(review_file.name)
                break
            except:
                pass
        
        if not session:
            session = WorktreeReviewSession(worktree_name, course_id)
        
        # Add or update item review
        item_review = session.get_item_review(item_id)
        if not item_review:
            item_review = ItemReview(item_id, item_title, item_type, canvas_id, file_path)
        
        review_pass = ReviewPass(
            pass_type="style",
            agent_id=agent_id,
            agent_role="style_agent",
            decision=decision,
            reasoning=reasoning,
            severity=severity
        )
        item_review.add_pass(review_pass)
        session.add_item_review(item_review)
        
        # Save session
        wm.save_review_session(session)
        
        return json.dumps({
            "status": "success",
            "review_pass": review_pass.to_dict(),
            "item_status": item_review.get_status()
        }, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def submit_fact_check_review(
    course_id: str,
    course_path: str,
    worktree_name: str,
    item_id: str,
    item_title: str,
    item_type: str,
    canvas_id: str,
    file_path: str,
    agent_id: str,
    decision: str,
    reasoning: str,
    references: str = "",
    severity: str = "medium"
) -> str:
    """
    Submit a fact-check review pass for an item (claims, sources, accuracy).
    
    Args:
        course_id: Canvas course ID
        course_path: Path to course directory
        worktree_name: Name of the worktree being reviewed
        item_id: Unified item ID (e.g., 'page:12345')
        item_title: Human-readable item title
        item_type: Type of item (page, quiz, assignment, rubric)
        canvas_id: Canvas object ID
        file_path: Local file path
        agent_id: ID of reviewing agent
        decision: approved, rejected, needs_revision
        reasoning: Explanation of what was fact-checked
        references: Comma-separated list of related item IDs
        severity: low, medium, high
    
    Returns:
        JSON with review result
    """
    try:
        wm = WorkflowManager(course_path)
        
        # Create or load session
        session = None
        for review_file in wm.reviews_dir.glob(f"{worktree_name}_*.json"):
            try:
                session = wm.load_review_session(review_file.name)
                break
            except:
                pass
        
        if not session:
            session = WorktreeReviewSession(worktree_name, course_id)
        
        # Add or update item review
        item_review = session.get_item_review(item_id)
        if not item_review:
            item_review = ItemReview(item_id, item_title, item_type, canvas_id, file_path)
        
        ref_list = [r.strip() for r in references.split(",")] if references else []
        
        review_pass = ReviewPass(
            pass_type="fact_check",
            agent_id=agent_id,
            agent_role="fact_check_agent",
            decision=decision,
            reasoning=reasoning,
            references=ref_list,
            severity=severity
        )
        item_review.add_pass(review_pass)
        session.add_item_review(item_review)
        
        # Save session
        wm.save_review_session(session)
        
        return json.dumps({
            "status": "success",
            "review_pass": review_pass.to_dict(),
            "item_status": item_review.get_status()
        }, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def submit_consistency_review(
    course_id: str,
    course_path: str,
    worktree_name: str,
    item_id: str,
    item_title: str,
    item_type: str,
    canvas_id: str,
    file_path: str,
    agent_id: str,
    decision: str,
    reasoning: str,
    references: str = "",
    severity: str = "medium"
) -> str:
    """
    Submit a consistency review pass for an item (integration, alignment, structure).
    
    Args:
        course_id: Canvas course ID
        course_path: Path to course directory
        worktree_name: Name of the worktree being reviewed
        item_id: Unified item ID (e.g., 'page:12345')
        item_title: Human-readable item title
        item_type: Type of item (page, quiz, assignment, rubric)
        canvas_id: Canvas object ID
        file_path: Local file path
        agent_id: ID of reviewing agent
        decision: approved, rejected, needs_revision
        reasoning: Explanation of consistency issues found
        references: Comma-separated list of related item IDs for context
        severity: low, medium, high
    
    Returns:
        JSON with review result
    """
    try:
        wm = WorkflowManager(course_path)
        
        # Create or load session
        session = None
        for review_file in wm.reviews_dir.glob(f"{worktree_name}_*.json"):
            try:
                session = wm.load_review_session(review_file.name)
                break
            except:
                pass
        
        if not session:
            session = WorktreeReviewSession(worktree_name, course_id)
        
        # Add or update item review
        item_review = session.get_item_review(item_id)
        if not item_review:
            item_review = ItemReview(item_id, item_title, item_type, canvas_id, file_path)
        
        ref_list = [r.strip() for r in references.split(",")] if references else []
        
        review_pass = ReviewPass(
            pass_type="consistency",
            agent_id=agent_id,
            agent_role="consistency_agent",
            decision=decision,
            reasoning=reasoning,
            references=ref_list,
            severity=severity
        )
        item_review.add_pass(review_pass)
        session.add_item_review(item_review)
        
        # Save session
        wm.save_review_session(session)
        
        return json.dumps({
            "status": "success",
            "review_pass": review_pass.to_dict(),
            "item_status": item_review.get_status()
        }, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def get_item_review_history(
    course_path: str,
    item_id: str,
    include_archived: bool = True
) -> str:
    """
    Get all review history for a specific item across all worktrees.
    
    Args:
        course_path: Path to course directory
        item_id: Unified item ID (e.g., 'page:12345')
        include_archived: Include archived reviews (default: true)
    
    Returns:
        JSON array of all reviews for this item
    """
    try:
        wm = WorkflowManager(course_path)
        history = wm.get_item_review_history(item_id, include_archived)
        return json.dumps(history, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def get_worktree_review_status(
    course_path: str,
    worktree_name: str
) -> str:
    """
    Get review status summary for a worktree.
    
    Args:
        course_path: Path to course directory
        worktree_name: Name of the worktree
    
    Returns:
        JSON with approved/rejected/escalation counts and items list
    """
    try:
        wm = WorkflowManager(course_path)
        
        # Find and load session
        for review_file in wm.reviews_dir.glob(f"{worktree_name}_*.json"):
            try:
                session = wm.load_review_session(review_file.name)
                return json.dumps({
                    "worktree_name": worktree_name,
                    "summary": session.get_summary(),
                    "items": [item.to_dict() for item in session.items.values()]
                }, indent=2)
            except:
                pass
        
        return json.dumps({"error": f"No reviews found for worktree: {worktree_name}"})
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def get_review_conflicts(
    course_path: str,
    worktree_name: str = ""
) -> str:
    """
    Get all items with conflicts/escalations that need human review.
    
    Args:
        course_path: Path to course directory
        worktree_name: Optional filter to specific worktree
    
    Returns:
        JSON array of conflicted items with reviewer reasoning
    """
    try:
        wm = WorkflowManager(course_path)
        conflicts = wm.get_worktree_review_conflicts(
            worktree_name if worktree_name else None
        )
        return json.dumps({
            "total_conflicts": len(conflicts),
            "conflicts": conflicts
        }, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def escalate_review_conflict(
    course_path: str,
    worktree_name: str,
    item_id: str,
    escalation_reason: str,
    conflicting_reviews: str
) -> str:
    """
    Escalate a review conflict to human review.
    
    Args:
        course_path: Path to course directory
        worktree_name: Name of the worktree
        item_id: Item ID with conflict
        escalation_reason: Reason for escalation
        conflicting_reviews: JSON string of conflicting review passes
    
    Returns:
        JSON with escalation record
    """
    try:
        import json as json_lib
        wm = WorkflowManager(course_path)
        
        # Find and load session
        for review_file in wm.reviews_dir.glob(f"{worktree_name}_*.json"):
            try:
                session = wm.load_review_session(review_file.name)
                item_review = session.get_item_review(item_id)
                
                if item_review:
                    item_review.escalation = {
                        "status": "pending_human_review",
                        "reason": escalation_reason,
                        "escalated_at": datetime.utcnow().isoformat() + "Z",
                        "conflicting_reviews": json_lib.loads(conflicting_reviews) if conflicting_reviews else []
                    }
                    
                    session.add_item_review(item_review)
                    wm.save_review_session(session)
                    
                    return json.dumps({
                        "status": "escalated",
                        "item_id": item_id,
                        "escalation": item_review.escalation
                    }, indent=2)
            except Exception as e:
                logger.error(f"Error processing review file: {e}")
        
        return json.dumps({"error": f"Could not find reviews for worktree: {worktree_name}"})
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def approve_and_merge_worktree(
    course_path: str,
    worktree_name: str,
    approved_by_agent_id: str,
    review_summary: str = ""
) -> str:
    """
    Approve and merge a worktree back to main branch, then clean up.
    
    Args:
        course_path: Path to course directory
        worktree_name: Name of worktree to merge
        approved_by_agent_id: ID of approving entity (agent or human)
        review_summary: Optional summary of reviews/approvals
    
    Returns:
        JSON with merge result, commit hash, Canvas sync status
    """
    try:
        import subprocess
        from pathlib import Path
        from datetime import datetime
        
        wm = WorkflowManager(course_path)
        
        # Find worktree path
        worktree_path = None
        for item in Path(course_path).iterdir():
            if item.is_dir() and item.name == worktree_name:
                worktree_path = item
                break
        
        if not worktree_path:
            return json.dumps({"error": f"Worktree not found: {worktree_name}"})
        
        # Get worktree branch name
        try:
            branch_result = subprocess.run(
                ["git", "symbolic-ref", "--short", "HEAD"],
                cwd=str(worktree_path),
                capture_output=True,
                text=True,
                timeout=5
            )
            branch_name = branch_result.stdout.strip()
        except:
            return json.dumps({"error": "Could not determine worktree branch"})
        
        # Perform merge
        try:
            merge_msg = f"Merge {worktree_name}"
            if review_summary:
                merge_msg += f"\n\n{review_summary}"
            
            merge_result = subprocess.run(
                ["git", "merge", branch_name, "-m", merge_msg],
                cwd=course_path,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if merge_result.returncode != 0:
                return json.dumps({
                    "status": "merge_conflict",
                    "error": merge_result.stderr
                })
        except Exception as e:
            return json.dumps({"error": f"Merge failed: {str(e)}"})
        
        # Get merge commit hash
        try:
            commit_result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=course_path,
                capture_output=True,
                text=True,
                timeout=5
            )
            merge_commit = commit_result.stdout.strip()
        except:
            merge_commit = None
        
        # Delete worktree
        try:
            subprocess.run(
                ["git", "worktree", "remove", str(worktree_path), "--force"],
                cwd=course_path,
                capture_output=True,
                timeout=10
            )
        except Exception as e:
            logger.error(f"Failed to remove worktree: {e}")
        
        # Archive reviews
        try:
            for review_file in wm.reviews_dir.glob(f"{worktree_name}_*.json"):
                session = wm.load_review_session(review_file.name)
                session.archive(approved_by_agent_id, merge_commit or "unknown")
                wm.save_review_session(session)
        except Exception as e:
            logger.error(f"Failed to archive reviews: {e}")
        
        return json.dumps({
            "status": "success",
            "merge_commit": merge_commit,
            "deleted_worktree": True,
            "reviews_archived": True,
            "next_step": "Check Canvas sync status and push to Canvas if needed"
        }, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


# =============================================================================
# Draft Grade Storage Tools
# =============================================================================

@mcp.tool()
def load_draft_grade(assignment_id: str, user_id: str) -> str:
    """
    Load a draft grade from local storage.

    Args:
        assignment_id: Canvas assignment ID
        user_id: Canvas user ID

    Returns:
        JSON with draft grade data including runs, or null if not found
    """
    try:
        result = draft_storage.load_draft_grade(assignment_id, user_id)
        if result is None:
            return json.dumps(None)
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def save_draft_grade(assignment_id: str, user_id: str, draft_data: str) -> str:
    """
    Save a draft grade to local storage.

    Args:
        assignment_id: Canvas assignment ID
        user_id: Canvas user ID
        draft_data: JSON string with draft data (must have 'runs' and 'current_run')

    Returns:
        JSON with success status
    """
    try:
        data = json.loads(draft_data)
        success = draft_storage.save_draft_grade(assignment_id, user_id, data)
        return json.dumps({"success": success})
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def add_draft_run(
    assignment_id: str,
    user_id: str,
    run_data: str,
    set_as_current: bool = True
) -> str:
    """
    Add a new draft run to an existing draft grade.

    Args:
        assignment_id: Canvas assignment ID
        user_id: Canvas user ID
        run_data: JSON string with run data (rubric_assessment, comments, model, etc.)
        set_as_current: Whether to set this as the current run (default: True)

    Returns:
        JSON with run_id if successful
    """
    try:
        data = json.loads(run_data)
        run_id = draft_storage.add_draft_run(assignment_id, user_id, data, set_as_current)
        if run_id:
            return json.dumps({"success": True, "run_id": run_id})
        return json.dumps({"error": "Failed to add draft run"})
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def get_current_draft_run(assignment_id: str, user_id: str) -> str:
    """
    Get the current draft run for a student.

    Args:
        assignment_id: Canvas assignment ID
        user_id: Canvas user ID

    Returns:
        JSON with current run data or null if not found
    """
    try:
        result = draft_storage.get_current_run(assignment_id, user_id)
        if result is None:
            return json.dumps(None)
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def set_current_draft_run(assignment_id: str, user_id: str, run_id: str) -> str:
    """
    Set a specific run as the current run.

    Args:
        assignment_id: Canvas assignment ID
        user_id: Canvas user ID
        run_id: Run ID to set as current

    Returns:
        JSON with success status
    """
    try:
        success = draft_storage.set_current_run(assignment_id, user_id, run_id)
        return json.dumps({"success": success})
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def list_draft_grades(assignment_id: str) -> str:
    """
    List all draft grades for an assignment.

    Args:
        assignment_id: Canvas assignment ID

    Returns:
        JSON list of drafts with user_id and summary info
    """
    try:
        result = draft_storage.list_draft_grades(assignment_id)
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def delete_draft_grade(assignment_id: str, user_id: str) -> str:
    """
    Delete a draft grade file.

    Args:
        assignment_id: Canvas assignment ID
        user_id: Canvas user ID

    Returns:
        JSON with success status
    """
    try:
        success = draft_storage.delete_draft_grade(assignment_id, user_id)
        return json.dumps({"success": success})
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def update_draft_run(
    assignment_id: str,
    user_id: str,
    run_id: str,
    updates: str
) -> str:
    """
    Update an existing draft run.

    Args:
        assignment_id: Canvas assignment ID
        user_id: Canvas user ID
        run_id: Run ID to update
        updates: JSON string with fields to update

    Returns:
        JSON with success status
    """
    try:
        update_data = json.loads(updates)
        success = draft_storage.update_run(assignment_id, user_id, run_id, update_data)
        return json.dumps({"success": success})
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def set_official_rubric(assignment_id: str, user_id: str, rubric_data: str) -> str:
    """
    Set the official rubric (formatted for Canvas API submission).

    Args:
        assignment_id: Canvas assignment ID
        user_id: Canvas user ID
        rubric_data: JSON string with rubric data formatted for Canvas API

    Returns:
        JSON with success status
    """
    try:
        data = json.loads(rubric_data)
        success = draft_storage.set_official_rubric(assignment_id, user_id, data)
        return json.dumps({"success": success})
    except Exception as e:
        return json.dumps({"error": str(e)})


def main():
    """Run the Canvas MCP server."""
    print("Starting Canvas MCP Server...")
    print("Tools: list_pages, get_page, create_page, update_page, delete_page,")
    print("       pull_pages, push_pages, sync_status,")
    print("       list_quizzes, get_quiz, get_quiz_questions,")
    print("       pull_quizzes, push_quizzes, quiz_sync_status,")
    print("       pull_modules, push_modules, module_sync_status,")
    print("       pull_course_files, download_pending_files, list_pending_files,")
    print("       list_courses, list_assignments, get_assignment,")
    print("       list_submissions, get_submission, update_grade,")
    print("       list_discussions, get_discussion_posts,")
    print("       get_rubric, update_rubric,")
    print("       load_draft_grade, save_draft_grade, add_draft_run,")
    print("       get_current_draft_run, set_current_draft_run,")
    print("       list_draft_grades, delete_draft_grade, update_draft_run,")
    print("       set_official_rubric")
    print()
    print("NOTE: Submission tools anonymize student data by default for AI privacy.")
    print("      Use anonymize=False only when working locally without AI review.")
    print()
    mcp.run()


if __name__ == "__main__":
    main()
