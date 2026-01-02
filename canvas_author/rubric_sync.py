"""
Rubric Sync Module

Pull and push operations for syncing rubrics between Canvas and local YAML files.
"""

import logging
import re
from pathlib import Path
from typing import Dict, Any, List, Optional

import yaml

from .client import get_canvas_client, CanvasClient
from .assignments import list_assignments, get_assignment
from .rubrics import get_rubric, update_rubric, sync_rubric_ids

logger = logging.getLogger("canvas_author.rubric_sync")


def _slugify(title: str) -> str:
    """Convert a title to a filesystem-safe slug."""
    slug = title.lower()
    slug = re.sub(r'[^\w\s-]', '', slug)
    slug = re.sub(r'[\s_]+', '-', slug)
    slug = re.sub(r'-+', '-', slug)
    return slug.strip('-')


def _rubric_to_yaml(assignment: Dict, rubric: Dict) -> Dict:
    """Convert Canvas rubric data to YAML-friendly format."""
    criteria = []
    for criterion in rubric.get('data', []):
        crit_data = {
            'id': criterion.get('id'),
            'description': criterion.get('description', ''),
            'long_description': criterion.get('long_description', ''),
            'points': criterion.get('points', 0),
            'ratings': []
        }

        for rating in criterion.get('ratings', []):
            crit_data['ratings'].append({
                'id': rating.get('id'),
                'description': rating.get('description', ''),
                'long_description': rating.get('long_description', ''),
                'points': rating.get('points', 0)
            })

        criteria.append(crit_data)

    return {
        'assignment_id': assignment.get('id'),
        'assignment_name': assignment.get('name', ''),
        'rubric': {
            'id': rubric.get('id'),
            'title': rubric.get('rubric_settings', {}).get('title', ''),
            'points_possible': rubric.get('points_possible', 0),
            'free_form_criterion_comments': rubric.get('free_form_criterion_comments', False),
            'criteria': criteria
        }
    }


def _yaml_to_rubric(yaml_data: Dict) -> tuple:
    """Convert YAML data back to Canvas rubric format.

    Returns:
        Tuple of (rubric_data, rubric_settings)
    """
    rubric_yaml = yaml_data.get('rubric', {})

    rubric_data = []
    for criterion in rubric_yaml.get('criteria', []):
        crit_data = {
            'id': criterion.get('id'),
            'description': criterion.get('description', ''),
            'long_description': criterion.get('long_description', ''),
            'points': criterion.get('points', 0),
            'ratings': []
        }

        for rating in criterion.get('ratings', []):
            crit_data['ratings'].append({
                'id': rating.get('id'),
                'description': rating.get('description', ''),
                'long_description': rating.get('long_description', ''),
                'points': rating.get('points', 0)
            })

        rubric_data.append(crit_data)

    rubric_settings = {
        'id': rubric_yaml.get('id'),
        'title': rubric_yaml.get('title', ''),
        'points_possible': rubric_yaml.get('points_possible', 0),
        'free_form_criterion_comments': rubric_yaml.get('free_form_criterion_comments', False),
    }

    return rubric_data, rubric_settings


def pull_rubrics(
    course_id: str,
    output_dir: str,
    overwrite: bool = False,
    client: Optional[CanvasClient] = None
) -> Dict[str, Any]:
    """
    Pull all rubrics from Canvas assignments to local YAML files.

    Args:
        course_id: Canvas course ID
        output_dir: Directory to write rubric files
        overwrite: Whether to overwrite existing files
        client: Optional CanvasClient instance

    Returns:
        Dict with 'pulled', 'skipped', and 'errors' lists
    """
    canvas = client or get_canvas_client()
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    result = {
        "pulled": [],
        "skipped": [],
        "errors": [],
        "no_rubric": [],
    }

    assignments = list_assignments(course_id, client=canvas)
    logger.info(f"Found {len(assignments)} assignments in course {course_id}")

    for assignment in assignments:
        assignment_id = assignment["id"]
        name = assignment.get("name", f"assignment-{assignment_id}")
        slug = _slugify(name)
        filename = f"{slug}.rubric.yaml"
        file_path = output_path / filename

        try:
            # Get rubric for this assignment
            rubric = get_rubric(course_id, assignment_id, client=canvas)

            if not rubric:
                result["no_rubric"].append({
                    "assignment_id": assignment_id,
                    "name": name,
                })
                continue

            # Check if file exists and skip if not overwriting
            if file_path.exists() and not overwrite:
                result["skipped"].append({
                    "assignment_id": assignment_id,
                    "name": name,
                    "file": filename,
                    "reason": "file exists",
                })
                continue

            # Convert to YAML format
            yaml_data = _rubric_to_yaml(assignment, rubric)

            # Write YAML file
            with open(file_path, 'w', encoding='utf-8') as f:
                yaml.dump(yaml_data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

            criteria_count = len(rubric.get('data', []))
            result["pulled"].append({
                "assignment_id": assignment_id,
                "name": name,
                "file": filename,
                "criteria_count": criteria_count,
            })
            logger.info(f"Pulled rubric for '{name}' to {filename}")

        except Exception as e:
            logger.error(f"Error pulling rubric for assignment {assignment_id}: {e}")
            result["errors"].append({
                "assignment_id": assignment_id,
                "name": name,
                "error": str(e),
            })

    return result


def push_rubrics(
    course_id: str,
    input_dir: str,
    create_only: bool = False,
    client: Optional[CanvasClient] = None
) -> Dict[str, Any]:
    """
    Push local YAML rubric files to Canvas.

    Args:
        course_id: Canvas course ID
        input_dir: Directory containing rubric YAML files
        create_only: Only create new rubrics, don't update existing
        client: Optional CanvasClient instance

    Returns:
        Dict with 'created', 'updated', 'skipped', and 'errors' lists
    """
    import asyncio

    canvas = client or get_canvas_client()
    input_path = Path(input_dir)

    result = {
        "created": [],
        "updated": [],
        "skipped": [],
        "errors": [],
    }

    # Find all rubric YAML files
    rubric_files = list(input_path.glob("*.rubric.yaml"))
    logger.info(f"Found {len(rubric_files)} rubric files in {input_dir}")

    for file_path in rubric_files:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                yaml_data = yaml.safe_load(f)

            assignment_id = str(yaml_data.get('assignment_id'))
            name = yaml_data.get('assignment_name', file_path.stem)

            if not assignment_id:
                result["errors"].append({
                    "file": file_path.name,
                    "error": "No assignment_id in YAML file",
                })
                continue

            # Check if assignment has existing rubric
            existing_rubric = get_rubric(course_id, assignment_id, client=canvas)

            if existing_rubric and create_only:
                result["skipped"].append({
                    "file": file_path.name,
                    "assignment_id": assignment_id,
                    "name": name,
                    "reason": "rubric exists, create_only is True",
                })
                continue

            # Convert YAML to Canvas format
            rubric_data, rubric_settings = _yaml_to_rubric(yaml_data)

            # Push to Canvas (update_rubric is async)
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                success, response = loop.run_until_complete(
                    update_rubric(course_id, assignment_id, rubric_data, rubric_settings, client=canvas)
                )
            finally:
                loop.close()

            if success:
                # Sync IDs back to local file
                if isinstance(response, dict):
                    local_rubric = {'data': rubric_data}
                    sync_success, sync_msg, id_mapping = sync_rubric_ids(local_rubric, response)

                    if sync_success and id_mapping:
                        # Update the YAML file with new IDs
                        yaml_data['rubric']['id'] = response.get('id')
                        for i, crit in enumerate(yaml_data['rubric'].get('criteria', [])):
                            if i < len(local_rubric['data']):
                                crit['id'] = local_rubric['data'][i].get('id')
                                for j, rating in enumerate(crit.get('ratings', [])):
                                    if j < len(local_rubric['data'][i].get('ratings', [])):
                                        rating['id'] = local_rubric['data'][i]['ratings'][j].get('id')

                        with open(file_path, 'w', encoding='utf-8') as f:
                            yaml.dump(yaml_data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

                action = "created" if not existing_rubric else "updated"
                result[action].append({
                    "file": file_path.name,
                    "assignment_id": assignment_id,
                    "name": name,
                    "criteria_count": len(rubric_data),
                })
                logger.info(f"{action.capitalize()} rubric for '{name}' from {file_path.name}")
            else:
                result["errors"].append({
                    "file": file_path.name,
                    "assignment_id": assignment_id,
                    "name": name,
                    "error": str(response),
                })

        except Exception as e:
            logger.error(f"Error pushing {file_path.name}: {e}")
            result["errors"].append({
                "file": file_path.name,
                "error": str(e),
            })

    return result


def rubric_sync_status(
    course_id: str,
    local_dir: str,
    client: Optional[CanvasClient] = None
) -> Dict[str, Any]:
    """
    Check sync status between local rubric files and Canvas.

    Args:
        course_id: Canvas course ID
        local_dir: Directory containing local rubric files
        client: Optional CanvasClient instance

    Returns:
        Dict with 'canvas_only', 'local_only', 'synced', and 'summary'
    """
    canvas = client or get_canvas_client()
    local_path = Path(local_dir)

    # Get Canvas assignments with rubrics
    canvas_rubrics = {}
    assignments = list_assignments(course_id, client=canvas)

    for assignment in assignments:
        assignment_id = assignment["id"]
        rubric = get_rubric(course_id, assignment_id, client=canvas)
        if rubric:
            canvas_rubrics[assignment_id] = {
                "assignment_id": assignment_id,
                "name": assignment.get("name", ""),
                "rubric_id": rubric.get("id"),
                "criteria_count": len(rubric.get("data", [])),
            }

    # Get local rubric files
    local_rubrics = {}
    for file_path in local_path.glob("*.rubric.yaml"):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                yaml_data = yaml.safe_load(f)

            assignment_id = str(yaml_data.get('assignment_id'))
            if assignment_id:
                local_rubrics[assignment_id] = {
                    "file": file_path.name,
                    "assignment_id": assignment_id,
                    "name": yaml_data.get('assignment_name', ''),
                    "criteria_count": len(yaml_data.get('rubric', {}).get('criteria', [])),
                }
            else:
                # No assignment_id - local only
                local_rubrics[f"local:{file_path.name}"] = {
                    "file": file_path.name,
                    "assignment_id": None,
                    "name": yaml_data.get('assignment_name', file_path.stem),
                }
        except Exception as e:
            logger.warning(f"Error reading {file_path.name}: {e}")

    # Compute differences
    canvas_ids = set(canvas_rubrics.keys())
    local_ids = {k for k in local_rubrics.keys() if not k.startswith("local:")}
    local_only_files = [v for k, v in local_rubrics.items() if k.startswith("local:")]

    canvas_only = [canvas_rubrics[aid] for aid in canvas_ids - local_ids]
    synced = []

    for aid in canvas_ids & local_ids:
        synced.append({
            **local_rubrics[aid],
            "canvas_criteria_count": canvas_rubrics[aid]["criteria_count"],
            "synced": local_rubrics[aid]["criteria_count"] == canvas_rubrics[aid]["criteria_count"],
        })

    return {
        "canvas_only": canvas_only,
        "local_only": local_only_files,
        "synced": synced,
        "summary": {
            "canvas_count": len(canvas_rubrics),
            "local_count": len(local_rubrics),
            "canvas_only_count": len(canvas_only),
            "local_only_count": len(local_only_files),
            "synced_count": len(synced),
        },
    }
