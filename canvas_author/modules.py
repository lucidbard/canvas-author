"""
Modules Module

CRUD operations for Canvas course modules and module items.
"""

import logging
from typing import List, Dict, Any, Optional
from canvasapi.exceptions import ResourceDoesNotExist

from canvas_common import get_canvas_client, CanvasClient
from canvas_common import ResourceNotFoundError

logger = logging.getLogger("canvas_author.modules")


def list_modules(
    course_id: str,
    client: Optional[CanvasClient] = None,
    course=None,
    include_items: bool = False
) -> List[Dict[str, Any]]:
    """
    List all modules in a course.

    Args:
        course_id: Canvas course ID
        client: Optional CanvasClient instance
        course: Optional cached course object
        include_items: Whether to include module items in response

    Returns:
        List of module dicts with keys: id, name, position, published, items_count
    """
    if course is None:
        canvas = client or get_canvas_client()
        course = canvas.get_course(course_id)

    include = ["items"] if include_items else []
    modules = course.get_modules(include=include)

    result = []
    for module in modules:
        module_data = {
            "id": str(module.id),
            "name": module.name,
            "position": getattr(module, "position", 0),
            "published": getattr(module, "published", False),
            "items_count": getattr(module, "items_count", 0),
            "unlock_at": str(getattr(module, "unlock_at", None)),
            "require_sequential_progress": getattr(module, "require_sequential_progress", False),
        }

        if include_items and hasattr(module, "items"):
            module_data["items"] = [
                _format_module_item(item) for item in module.items
            ]

        result.append(module_data)

    logger.info(f"Listed {len(result)} modules for course {course_id}")
    return result


def get_module(
    course_id: str,
    module_id: str,
    client: Optional[CanvasClient] = None,
    course=None,
    include_items: bool = True
) -> Dict[str, Any]:
    """
    Get a specific module by ID.

    Args:
        course_id: Canvas course ID
        module_id: Canvas module ID
        client: Optional CanvasClient instance
        course: Optional cached course object
        include_items: Whether to include module items

    Returns:
        Module data dict
    """
    if course is None:
        canvas = client or get_canvas_client()
        course = canvas.get_course(course_id)

    try:
        include = ["items"] if include_items else []
        module = course.get_module(module_id, include=include)
    except ResourceDoesNotExist:
        raise ResourceNotFoundError("module", module_id)

    result = {
        "id": str(module.id),
        "name": module.name,
        "position": getattr(module, "position", 0),
        "published": getattr(module, "published", False),
        "items_count": getattr(module, "items_count", 0),
        "unlock_at": str(getattr(module, "unlock_at", None)),
        "require_sequential_progress": getattr(module, "require_sequential_progress", False),
    }

    if include_items:
        items = list(module.get_module_items())
        result["items"] = [_format_module_item(item) for item in items]

    logger.info(f"Retrieved module {module_id} from course {course_id}")
    return result


def create_module(
    course_id: str,
    name: str,
    position: Optional[int] = None,
    published: bool = False,
    unlock_at: Optional[str] = None,
    require_sequential_progress: bool = False,
    client: Optional[CanvasClient] = None,
    course=None
) -> Dict[str, Any]:
    """
    Create a new module.

    Args:
        course_id: Canvas course ID
        name: Module name
        position: Position in module list (optional)
        published: Whether to publish the module
        unlock_at: Date to unlock module (ISO 8601 format)
        require_sequential_progress: Require items completed in order
        client: Optional CanvasClient instance
        course: Optional cached course object

    Returns:
        Created module data
    """
    if course is None:
        canvas = client or get_canvas_client()
        course = canvas.get_course(course_id)

    module_data = {
        "name": name,
        "published": published,
        "require_sequential_progress": require_sequential_progress,
    }

    if position is not None:
        module_data["position"] = position
    if unlock_at is not None:
        module_data["unlock_at"] = unlock_at

    module = course.create_module(module=module_data)

    logger.info(f"Created module '{name}' in course {course_id}")

    return {
        "id": str(module.id),
        "name": module.name,
        "position": getattr(module, "position", 0),
        "published": getattr(module, "published", False),
    }


def update_module(
    course_id: str,
    module_id: str,
    name: Optional[str] = None,
    position: Optional[int] = None,
    published: Optional[bool] = None,
    unlock_at: Optional[str] = None,
    require_sequential_progress: Optional[bool] = None,
    client: Optional[CanvasClient] = None,
    course=None
) -> Dict[str, Any]:
    """
    Update an existing module.

    Args:
        course_id: Canvas course ID
        module_id: Canvas module ID
        name: New module name
        position: New position
        published: Whether to publish
        unlock_at: Date to unlock (ISO 8601)
        require_sequential_progress: Require sequential progress
        client: Optional CanvasClient instance
        course: Optional cached course object

    Returns:
        Updated module data
    """
    if course is None:
        canvas = client or get_canvas_client()
        course = canvas.get_course(course_id)

    try:
        module = course.get_module(module_id)
    except ResourceDoesNotExist:
        raise ResourceNotFoundError("module", module_id)

    update_data = {}
    if name is not None:
        update_data["name"] = name
    if position is not None:
        update_data["position"] = position
    if published is not None:
        update_data["published"] = published
    if unlock_at is not None:
        update_data["unlock_at"] = unlock_at
    if require_sequential_progress is not None:
        update_data["require_sequential_progress"] = require_sequential_progress

    if update_data:
        module = module.edit(module=update_data)
        logger.info(f"Updated module {module_id} in course {course_id}")

    return {
        "id": str(module.id),
        "name": module.name,
        "position": getattr(module, "position", 0),
        "published": getattr(module, "published", False),
    }


def delete_module(
    course_id: str,
    module_id: str,
    client: Optional[CanvasClient] = None,
    course=None
) -> bool:
    """
    Delete a module.

    Args:
        course_id: Canvas course ID
        module_id: Canvas module ID
        client: Optional CanvasClient instance
        course: Optional cached course object

    Returns:
        True if deleted successfully
    """
    if course is None:
        canvas = client or get_canvas_client()
        course = canvas.get_course(course_id)

    try:
        module = course.get_module(module_id)
    except ResourceDoesNotExist:
        raise ResourceNotFoundError("module", module_id)

    module.delete()
    logger.info(f"Deleted module {module_id} from course {course_id}")
    return True


# ============== Module Items ==============


def list_module_items(
    course_id: str,
    module_id: str,
    client: Optional[CanvasClient] = None,
    course=None
) -> List[Dict[str, Any]]:
    """
    List all items in a module.

    Args:
        course_id: Canvas course ID
        module_id: Canvas module ID
        client: Optional CanvasClient instance
        course: Optional cached course object

    Returns:
        List of module item dicts
    """
    if course is None:
        canvas = client or get_canvas_client()
        course = canvas.get_course(course_id)

    try:
        module = course.get_module(module_id)
    except ResourceDoesNotExist:
        raise ResourceNotFoundError("module", module_id)

    items = list(module.get_module_items())
    result = [_format_module_item(item) for item in items]

    logger.info(f"Listed {len(result)} items in module {module_id}")
    return result


def add_module_item(
    course_id: str,
    module_id: str,
    item_type: str,
    content_id: Optional[str] = None,
    page_url: Optional[str] = None,
    external_url: Optional[str] = None,
    title: Optional[str] = None,
    position: Optional[int] = None,
    indent: int = 0,
    client: Optional[CanvasClient] = None,
    course=None
) -> Dict[str, Any]:
    """
    Add an item to a module.

    Args:
        course_id: Canvas course ID
        module_id: Canvas module ID
        item_type: Type of item ('Page', 'Assignment', 'Quiz', 'File',
                   'Discussion', 'SubHeader', 'ExternalUrl', 'ExternalTool')
        content_id: ID of content (for Assignment, Quiz, File, Discussion)
        page_url: Page URL slug (for Page type)
        external_url: URL (for ExternalUrl type)
        title: Display title (required for SubHeader, ExternalUrl)
        position: Position within module
        indent: Indentation level (0-5)
        client: Optional CanvasClient instance
        course: Optional cached course object

    Returns:
        Created module item data
    """
    if course is None:
        canvas = client or get_canvas_client()
        course = canvas.get_course(course_id)

    try:
        module = course.get_module(module_id)
    except ResourceDoesNotExist:
        raise ResourceNotFoundError("module", module_id)

    item_data = {
        "type": item_type,
        "indent": indent,
    }

    if content_id is not None:
        item_data["content_id"] = content_id
    if page_url is not None:
        item_data["page_url"] = page_url
    if external_url is not None:
        item_data["external_url"] = external_url
    if title is not None:
        item_data["title"] = title
    if position is not None:
        item_data["position"] = position

    item = module.create_module_item(module_item=item_data)

    logger.info(f"Added {item_type} item to module {module_id}")
    return _format_module_item(item)


def update_module_item(
    course_id: str,
    module_id: str,
    item_id: str,
    title: Optional[str] = None,
    position: Optional[int] = None,
    indent: Optional[int] = None,
    external_url: Optional[str] = None,
    published: Optional[bool] = None,
    client: Optional[CanvasClient] = None,
    course=None
) -> Dict[str, Any]:
    """
    Update a module item.

    Args:
        course_id: Canvas course ID
        module_id: Canvas module ID
        item_id: Module item ID
        title: New title
        position: New position
        indent: New indentation level
        external_url: New URL (for ExternalUrl items)
        published: Publish state
        client: Optional CanvasClient instance
        course: Optional cached course object

    Returns:
        Updated module item data
    """
    if course is None:
        canvas = client or get_canvas_client()
        course = canvas.get_course(course_id)

    try:
        module = course.get_module(module_id)
        item = module.get_module_item(item_id)
    except ResourceDoesNotExist:
        raise ResourceNotFoundError("module_item", item_id)

    update_data = {}
    if title is not None:
        update_data["title"] = title
    if position is not None:
        update_data["position"] = position
    if indent is not None:
        update_data["indent"] = indent
    if external_url is not None:
        update_data["external_url"] = external_url
    if published is not None:
        update_data["published"] = published

    if update_data:
        item = item.edit(module_item=update_data)
        logger.info(f"Updated item {item_id} in module {module_id}")

    return _format_module_item(item)


def delete_module_item(
    course_id: str,
    module_id: str,
    item_id: str,
    client: Optional[CanvasClient] = None,
    course=None
) -> bool:
    """
    Delete a module item.

    Args:
        course_id: Canvas course ID
        module_id: Canvas module ID
        item_id: Module item ID
        client: Optional CanvasClient instance
        course: Optional cached course object

    Returns:
        True if deleted successfully
    """
    if course is None:
        canvas = client or get_canvas_client()
        course = canvas.get_course(course_id)

    try:
        module = course.get_module(module_id)
        item = module.get_module_item(item_id)
    except ResourceDoesNotExist:
        raise ResourceNotFoundError("module_item", item_id)

    item.delete()
    logger.info(f"Deleted item {item_id} from module {module_id}")
    return True


def _format_module_item(item) -> Dict[str, Any]:
    """Format a module item object or dict into a dict."""
    # Handle both dict (from inline items) and object (from get_module_items)
    if isinstance(item, dict):
        result = {
            "id": str(item.get("id", "")),
            "title": item.get("title", ""),
            "type": item.get("type", ""),
            "position": item.get("position", 0),
            "indent": item.get("indent", 0),
            "published": item.get("published", False),
        }
        item_type = result["type"]
        if item_type == "Page":
            result["page_url"] = item.get("page_url", "")
        elif item_type in ("Assignment", "Quiz", "File", "Discussion"):
            result["content_id"] = str(item.get("content_id", ""))
        elif item_type == "ExternalUrl":
            result["external_url"] = item.get("external_url", "")
        elif item_type == "ExternalTool":
            result["external_url"] = item.get("external_url", "")
            result["content_id"] = str(item.get("content_id", ""))
        if "html_url" in item:
            result["html_url"] = item["html_url"]
        return result

    # Object form
    result = {
        "id": str(item.id),
        "title": getattr(item, "title", ""),
        "type": getattr(item, "type", ""),
        "position": getattr(item, "position", 0),
        "indent": getattr(item, "indent", 0),
        "published": getattr(item, "published", False),
    }

    # Include type-specific fields
    item_type = result["type"]

    if item_type == "Page":
        result["page_url"] = getattr(item, "page_url", "")
    elif item_type in ("Assignment", "Quiz", "File", "Discussion"):
        result["content_id"] = str(getattr(item, "content_id", ""))
    elif item_type == "ExternalUrl":
        result["external_url"] = getattr(item, "external_url", "")
    elif item_type == "ExternalTool":
        result["external_url"] = getattr(item, "external_url", "")
        result["content_id"] = str(getattr(item, "content_id", ""))

    # Include HTML URL if available
    if hasattr(item, "html_url"):
        result["html_url"] = item.html_url

    return result
