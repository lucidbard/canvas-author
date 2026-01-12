"""
Wiki Pages Module

CRUD operations for Canvas wiki pages with markdown support via pandoc.
"""

import logging
from typing import List, Dict, Any, Optional
from canvasapi.exceptions import ResourceDoesNotExist, CanvasException

from .client import get_canvas_client, CanvasClient
from .pandoc import markdown_to_html, html_to_markdown
from .exceptions import ResourceNotFoundError, APIError

logger = logging.getLogger("canvas_author.pages")


def list_pages(course_id: str, client: Optional[CanvasClient] = None, course=None) -> List[Dict[str, Any]]:
    """
    List all wiki pages in a course.

    Args:
        course_id: Canvas course ID
        client: Optional CanvasClient instance
        course: Optional cached course object to avoid redundant API calls

    Returns:
        List of page metadata dicts with keys: url, title, created_at, updated_at, published
    """
    if course is None:
        canvas = client or get_canvas_client()
        course = canvas.get_course(course_id)
    pages = course.get_pages()

    result = []
    for page in pages:
        result.append({
            "url": page.url,
            "title": page.title,
            "created_at": str(getattr(page, "created_at", None)),
            "updated_at": str(getattr(page, "updated_at", None)),
            "published": getattr(page, "published", True),
            "front_page": getattr(page, "front_page", False),
        })

    logger.info(f"Listed {len(result)} pages for course {course_id}")
    return result


def get_page(
    course_id: str,
    page_url: str,
    as_markdown: bool = True,
    client: Optional[CanvasClient] = None,
    course=None
) -> Dict[str, Any]:
    """
    Get a wiki page by URL.

    Args:
        course_id: Canvas course ID
        page_url: Page URL slug (e.g., 'syllabus' or 'week-1-notes')
        as_markdown: If True, convert HTML body to markdown
        client: Optional CanvasClient instance
        course: Optional cached course object to avoid redundant API calls

    Returns:
        Page data dict with keys: url, title, body, created_at, updated_at, published
    """
    if course is None:
        canvas = client or get_canvas_client()
        course = canvas.get_course(course_id)

    try:
        page = course.get_page(page_url)
    except ResourceDoesNotExist:
        raise ResourceNotFoundError("page", page_url)

    body = getattr(page, "body", "") or ""
    if as_markdown and body:
        body = html_to_markdown(body)

    return {
        "url": page.url,
        "title": page.title,
        "body": body,
        "created_at": str(getattr(page, "created_at", None)),
        "updated_at": str(getattr(page, "updated_at", None)),
        "published": getattr(page, "published", True),
        "front_page": getattr(page, "front_page", False),
        "editing_roles": getattr(page, "editing_roles", None),
    }


def create_page(
    course_id: str,
    title: str,
    body: str,
    from_markdown: bool = True,
    published: bool = True,
    front_page: bool = False,
    editing_roles: str = "teachers",
    client: Optional[CanvasClient] = None,
    course=None
) -> Dict[str, Any]:
    """
    Create a new wiki page.

    Args:
        course_id: Canvas course ID
        title: Page title
        body: Page body content
        from_markdown: If True, convert body from markdown to HTML
        published: Whether to publish the page
        front_page: Whether to set as front page
        editing_roles: Who can edit ('teachers', 'students', 'members', 'public')
        client: Optional CanvasClient instance
        course: Optional cached course object to avoid redundant API calls

    Returns:
        Created page data
    """
    if course is None:
        canvas = client or get_canvas_client()
        course = canvas.get_course(course_id)

    if from_markdown and body:
        body = markdown_to_html(body)

    page = course.create_page(wiki_page={
        "title": title,
        "body": body,
        "published": published,
        "front_page": front_page,
        "editing_roles": editing_roles,
    })

    logger.info(f"Created page '{title}' in course {course_id}")

    return {
        "url": page.url,
        "title": page.title,
        "body": getattr(page, "body", ""),
        "created_at": str(getattr(page, "created_at", None)),
        "updated_at": str(getattr(page, "updated_at", None)),
        "published": getattr(page, "published", True),
    }


def update_page(
    course_id: str,
    page_url: str,
    title: Optional[str] = None,
    body: Optional[str] = None,
    from_markdown: bool = True,
    published: Optional[bool] = None,
    front_page: Optional[bool] = None,
    client: Optional[CanvasClient] = None,
    course=None
) -> Dict[str, Any]:
    """
    Update an existing wiki page.

    Args:
        course_id: Canvas course ID
        page_url: Page URL slug
        title: New page title (optional)
        body: New page body content (optional)
        from_markdown: If True, convert body from markdown to HTML
        published: Whether to publish the page (optional)
        front_page: Whether to set as front page (optional)
        client: Optional CanvasClient instance
        course: Optional cached course object to avoid redundant API calls

    Returns:
        Updated page data
    """
    if course is None:
        canvas = client or get_canvas_client()
        course = canvas.get_course(course_id)

    try:
        page = course.get_page(page_url)
    except ResourceDoesNotExist:
        raise ResourceNotFoundError("page", page_url)

    update_data = {}
    if title is not None:
        update_data["title"] = title
    if body is not None:
        if from_markdown:
            body = markdown_to_html(body)
        update_data["body"] = body
    if published is not None:
        update_data["published"] = published
    if front_page is not None:
        update_data["front_page"] = front_page

    if update_data:
        page = page.edit(wiki_page=update_data)
        logger.info(f"Updated page '{page_url}' in course {course_id}")

    return {
        "url": page.url,
        "title": page.title,
        "body": getattr(page, "body", ""),
        "created_at": str(getattr(page, "created_at", None)),
        "updated_at": str(getattr(page, "updated_at", None)),
        "published": getattr(page, "published", True),
    }


def delete_page(
    course_id: str,
    page_url: str,
    client: Optional[CanvasClient] = None,
    course=None
) -> bool:
    """
    Delete a wiki page.

    Args:
        course_id: Canvas course ID
        page_url: Page URL slug
        client: Optional CanvasClient instance
        course: Optional cached course object to avoid redundant API calls

    Returns:
        True if deleted successfully
    """
    if course is None:
        canvas = client or get_canvas_client()
        course = canvas.get_course(course_id)

    try:
        page = course.get_page(page_url)
    except ResourceDoesNotExist:
        raise ResourceNotFoundError("page", page_url)

    page.delete()
    logger.info(f"Deleted page '{page_url}' from course {course_id}")
    return True


def bulk_delete_pages(
    course_id: str,
    page_urls: List[str],
    client: Optional[CanvasClient] = None
) -> Dict[str, Any]:
    """
    Delete multiple wiki pages efficiently.

    Args:
        course_id: Canvas course ID
        page_urls: List of page URL slugs to delete
        client: Optional CanvasClient instance

    Returns:
        Dict with 'deleted', 'failed', and 'errors' lists
    """
    canvas = client or get_canvas_client()
    course = canvas.get_course(course_id)

    result = {
        "deleted": [],
        "failed": [],
        "errors": [],
    }

    for page_url in page_urls:
        try:
            page = course.get_page(page_url)
            page.delete()
            result["deleted"].append(page_url)
            logger.info(f"Deleted page '{page_url}' from course {course_id}")
        except ResourceDoesNotExist:
            result["failed"].append(page_url)
            result["errors"].append({
                "page_url": page_url,
                "error": "Page not found"
            })
            logger.warning(f"Page '{page_url}' not found in course {course_id}")
        except Exception as e:
            result["failed"].append(page_url)
            result["errors"].append({
                "page_url": page_url,
                "error": str(e)
            })
            logger.error(f"Error deleting page '{page_url}': {e}")

    logger.info(f"Bulk deletion complete: {len(result['deleted'])} deleted, {len(result['failed'])} failed")
    return result
