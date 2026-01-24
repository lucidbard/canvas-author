"""
Module Sync

Sync Canvas modules with local modules.yaml file.
"""

import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
import yaml

from canvas_common import get_canvas_client, CanvasClient
from .modules import (
    list_modules,
    get_module,
    create_module,
    update_module,
    delete_module,
    add_module_item,
    delete_module_item,
    list_module_items,
)

logger = logging.getLogger("canvas_author.module_sync")

MODULES_FILE = "modules.yaml"


def pull_modules(
    course_id: str,
    directory: str,
    client: Optional[CanvasClient] = None,
    course=None
) -> Dict[str, Any]:
    """
    Pull modules from Canvas and save to modules.yaml.

    Args:
        course_id: Canvas course ID
        directory: Local directory path
        client: Optional CanvasClient instance
        course: Optional cached course object

    Returns:
        Dict with pull results
    """
    if course is None:
        canvas = client or get_canvas_client()
        course = canvas.get_course(course_id)

    dir_path = Path(directory)
    modules_file = dir_path / MODULES_FILE

    # Get all modules with items
    modules = list_modules(course_id, client=client, course=course, include_items=True)

    # For modules without inline items, fetch them separately
    for module in modules:
        if "items" not in module:
            module_detail = get_module(
                course_id, module["id"],
                client=client, course=course, include_items=True
            )
            module["items"] = module_detail.get("items", [])

    # Convert to YAML-friendly format
    yaml_data = _modules_to_yaml(modules)

    # Write to file
    with open(modules_file, "w", encoding="utf-8") as f:
        yaml.dump(yaml_data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    logger.info(f"Pulled {len(modules)} modules to {modules_file}")

    return {
        "modules_count": len(modules),
        "items_count": sum(len(m.get("items", [])) for m in modules),
        "file": str(modules_file),
    }


def push_modules(
    course_id: str,
    directory: str,
    client: Optional[CanvasClient] = None,
    course=None,
    delete_missing: bool = False
) -> Dict[str, Any]:
    """
    Push modules.yaml to Canvas.

    Args:
        course_id: Canvas course ID
        directory: Local directory path
        client: Optional CanvasClient instance
        course: Optional cached course object
        delete_missing: Delete modules in Canvas not in local file

    Returns:
        Dict with push results
    """
    if course is None:
        canvas = client or get_canvas_client()
        course = canvas.get_course(course_id)

    dir_path = Path(directory)
    modules_file = dir_path / MODULES_FILE

    if not modules_file.exists():
        return {"error": f"No {MODULES_FILE} found in {directory}"}

    # Read local modules
    with open(modules_file, encoding="utf-8") as f:
        yaml_data = yaml.safe_load(f) or {}

    local_modules = yaml_data.get("modules", [])

    # Get existing Canvas modules
    canvas_modules = list_modules(course_id, client=client, course=course, include_items=True)
    canvas_modules_by_name = {m["name"]: m for m in canvas_modules}

    created = []
    updated = []
    deleted = []
    errors = []

    # Process each local module
    for position, local_module in enumerate(local_modules, start=1):
        name = local_module.get("name")
        if not name:
            errors.append({"error": "Module missing name", "module": local_module})
            continue

        try:
            if name in canvas_modules_by_name:
                # Update existing module
                canvas_module = canvas_modules_by_name[name]
                module_id = canvas_module["id"]

                # Update module properties
                update_module(
                    course_id, module_id,
                    position=position,
                    published=local_module.get("published", False),
                    client=client, course=course
                )

                # Sync items
                _sync_module_items(
                    course_id, module_id,
                    local_module.get("items", []),
                    canvas_module.get("items", []),
                    client=client, course=course
                )

                updated.append({"name": name, "id": module_id})
                del canvas_modules_by_name[name]  # Mark as processed

            else:
                # Create new module
                result = create_module(
                    course_id, name,
                    position=position,
                    published=local_module.get("published", False),
                    client=client, course=course
                )
                module_id = result["id"]

                # Add items
                for item_pos, item in enumerate(local_module.get("items", []), start=1):
                    _add_item_from_yaml(
                        course_id, module_id, item, item_pos,
                        client=client, course=course
                    )

                created.append({"name": name, "id": module_id})

        except Exception as e:
            errors.append({"name": name, "error": str(e)})

    # Delete modules not in local file
    if delete_missing:
        for name, canvas_module in canvas_modules_by_name.items():
            try:
                delete_module(course_id, canvas_module["id"], client=client, course=course)
                deleted.append({"name": name, "id": canvas_module["id"]})
            except Exception as e:
                errors.append({"name": name, "error": f"Failed to delete: {e}"})

    logger.info(f"Push complete: {len(created)} created, {len(updated)} updated, {len(deleted)} deleted")

    return {
        "created": created,
        "updated": updated,
        "deleted": deleted,
        "errors": errors,
    }


def module_sync_status(
    course_id: str,
    directory: str,
    client: Optional[CanvasClient] = None,
    course=None
) -> Dict[str, Any]:
    """
    Compare local modules.yaml with Canvas modules.

    Args:
        course_id: Canvas course ID
        directory: Local directory path
        client: Optional CanvasClient instance
        course: Optional cached course object

    Returns:
        Dict with sync status
    """
    if course is None:
        canvas = client or get_canvas_client()
        course = canvas.get_course(course_id)

    dir_path = Path(directory)
    modules_file = dir_path / MODULES_FILE

    # Get Canvas modules
    canvas_modules = list_modules(course_id, client=client, course=course)
    canvas_names = {m["name"] for m in canvas_modules}

    # Get local modules
    local_names = set()
    if modules_file.exists():
        with open(modules_file, encoding="utf-8") as f:
            yaml_data = yaml.safe_load(f) or {}
        local_modules = yaml_data.get("modules", [])
        local_names = {m.get("name") for m in local_modules if m.get("name")}

    synced = canvas_names & local_names
    canvas_only = canvas_names - local_names
    local_only = local_names - canvas_names

    return {
        "synced": [{"name": n} for n in sorted(synced)],
        "canvas_only": [{"name": n} for n in sorted(canvas_only)],
        "local_only": [{"name": n} for n in sorted(local_only)],
        "summary": {
            "synced_count": len(synced),
            "canvas_only_count": len(canvas_only),
            "local_only_count": len(local_only),
        }
    }


def _modules_to_yaml(modules: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Convert Canvas modules to YAML-friendly format."""
    yaml_modules = []

    for module in sorted(modules, key=lambda m: m.get("position", 0)):
        yaml_module = {
            "name": module["name"],
            "published": module.get("published", False),
        }

        items = module.get("items", [])
        if items:
            yaml_items = []
            for item in sorted(items, key=lambda i: i.get("position", 0)):
                yaml_item = _item_to_yaml(item)
                if yaml_item:
                    yaml_items.append(yaml_item)
            if yaml_items:
                yaml_module["items"] = yaml_items

        yaml_modules.append(yaml_module)

    return {"modules": yaml_modules}


def _item_to_yaml(item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Convert a module item to YAML format."""
    item_type = item.get("type", "").lower()

    if item_type == "page":
        return {
            "type": "page",
            "page_url": item.get("page_url", ""),
        }
    elif item_type == "assignment":
        return {
            "type": "assignment",
            "content_id": item.get("content_id", ""),
            "title": item.get("title", ""),
        }
    elif item_type == "quiz":
        return {
            "type": "quiz",
            "content_id": item.get("content_id", ""),
            "title": item.get("title", ""),
        }
    elif item_type == "file":
        return {
            "type": "file",
            "content_id": item.get("content_id", ""),
            "title": item.get("title", ""),
        }
    elif item_type == "discussion":
        return {
            "type": "discussion",
            "content_id": item.get("content_id", ""),
            "title": item.get("title", ""),
        }
    elif item_type == "externalurl":
        return {
            "type": "external_url",
            "url": item.get("external_url", ""),
            "title": item.get("title", ""),
        }
    elif item_type == "externaltool":
        return {
            "type": "external_tool",
            "url": item.get("external_url", ""),
            "title": item.get("title", ""),
        }
    elif item_type == "subheader":
        return {
            "type": "subheader",
            "title": item.get("title", ""),
        }
    else:
        logger.warning(f"Unknown module item type: {item_type}")
        return None


def _add_item_from_yaml(
    course_id: str,
    module_id: str,
    item: Dict[str, Any],
    position: int,
    client: Optional[CanvasClient] = None,
    course=None
) -> Dict[str, Any]:
    """Add a module item from YAML data."""
    item_type = item.get("type", "").lower()

    type_map = {
        "page": "Page",
        "assignment": "Assignment",
        "quiz": "Quiz",
        "file": "File",
        "discussion": "Discussion",
        "external_url": "ExternalUrl",
        "external_tool": "ExternalTool",
        "subheader": "SubHeader",
    }

    canvas_type = type_map.get(item_type)
    if not canvas_type:
        raise ValueError(f"Unknown item type: {item_type}")

    kwargs = {
        "course_id": course_id,
        "module_id": module_id,
        "item_type": canvas_type,
        "position": position,
        "indent": item.get("indent", 0),
        "client": client,
        "course": course,
    }

    if item_type == "page":
        kwargs["page_url"] = item.get("page_url")
    elif item_type in ("assignment", "quiz", "file", "discussion"):
        kwargs["content_id"] = item.get("content_id")
    elif item_type in ("external_url", "external_tool"):
        kwargs["external_url"] = item.get("url")
        kwargs["title"] = item.get("title", "Link")
    elif item_type == "subheader":
        kwargs["title"] = item.get("title", "")

    return add_module_item(**kwargs)


def _sync_module_items(
    course_id: str,
    module_id: str,
    local_items: List[Dict[str, Any]],
    canvas_items: List[Dict[str, Any]],
    client: Optional[CanvasClient] = None,
    course=None
):
    """Sync module items between local and Canvas."""
    # Build lookup for Canvas items
    canvas_item_lookup = {}
    for item in canvas_items:
        key = _item_key(item)
        if key:
            canvas_item_lookup[key] = item

    # Track which Canvas items we've seen
    seen_keys = set()

    # Add/update local items
    for position, local_item in enumerate(local_items, start=1):
        key = _item_key(local_item)
        if not key:
            continue

        seen_keys.add(key)

        if key not in canvas_item_lookup:
            # Add new item
            _add_item_from_yaml(
                course_id, module_id, local_item, position,
                client=client, course=course
            )

    # Delete items not in local (items in Canvas but not seen)
    for key, canvas_item in canvas_item_lookup.items():
        if key not in seen_keys:
            try:
                delete_module_item(
                    course_id, module_id, canvas_item["id"],
                    client=client, course=course
                )
            except Exception as e:
                logger.warning(f"Failed to delete module item: {e}")


def _item_key(item: Dict[str, Any]) -> Optional[str]:
    """Generate a unique key for a module item."""
    item_type = item.get("type", "").lower()

    if item_type == "page":
        page_url = item.get("page_url", "")
        return f"page:{page_url}" if page_url else None
    elif item_type in ("assignment", "quiz", "file", "discussion"):
        content_id = item.get("content_id", "")
        return f"{item_type}:{content_id}" if content_id else None
    elif item_type in ("external_url", "externalurl"):
        url = item.get("url") or item.get("external_url", "")
        return f"url:{url}" if url else None
    elif item_type in ("external_tool", "externaltool"):
        url = item.get("url") or item.get("external_url", "")
        return f"tool:{url}" if url else None
    elif item_type == "subheader":
        title = item.get("title", "")
        return f"subheader:{title}" if title else None
    else:
        return None
