"""
Rubrics Module

Operations for Canvas rubrics including get, update, and publish.
"""

import logging
import requests
from typing import Dict, Any, Optional, Tuple, List
from canvasapi.exceptions import ResourceDoesNotExist, CanvasException

from .client import get_canvas_client, CanvasClient
from .exceptions import ResourceNotFoundError, APIError

logger = logging.getLogger("canvas_author.rubrics")


def get_rubric(
    course_id: str,
    assignment_id: str,
    client: Optional[CanvasClient] = None
) -> Optional[Dict[str, Any]]:
    """
    Get the rubric for an assignment.

    Args:
        course_id: Canvas course ID
        assignment_id: Canvas assignment ID
        client: Optional CanvasClient instance

    Returns:
        Rubric data dict or None if no rubric
    """
    canvas = client or get_canvas_client()
    course = canvas.get_course(course_id)

    try:
        assignment = course.get_assignment(assignment_id)
    except ResourceDoesNotExist:
        raise ResourceNotFoundError("assignment", assignment_id)

    # Check if assignment has a rubric
    if not hasattr(assignment, 'rubric_settings') or not assignment.rubric_settings:
        logger.info(f"Assignment {assignment_id} does not have a rubric")
        return None

    # Format the rubric data
    rubric = {
        "id": assignment.rubric_settings.get('id'),
        "title": assignment.rubric_settings.get('title', ''),
        "context_id": course_id,
        "context_type": "Course",
        "points_possible": assignment.rubric_settings.get('points_possible', 0),
        "free_form_criterion_comments": assignment.rubric_settings.get('free_form_criterion_comments', False),
        "data": [],
        "rubric_settings": assignment.rubric_settings,
    }

    # Process each criterion
    for criterion in getattr(assignment, 'rubric', []):
        criterion_data = {
            "id": criterion.get('id'),
            "description": criterion.get('description', ''),
            "long_description": criterion.get('long_description', ''),
            "points": criterion.get('points', 0),
            "criterion_use_range": criterion.get('criterion_use_range', False),
            "ratings": []
        }

        # Process ratings
        for rating in criterion.get('ratings', []):
            criterion_data['ratings'].append({
                "id": rating.get('id'),
                "description": rating.get('description', ''),
                "long_description": rating.get('long_description', ''),
                "points": rating.get('points', 0)
            })

        rubric['data'].append(criterion_data)

    logger.info(f"Retrieved rubric for assignment {assignment_id}")
    return rubric


async def update_rubric(
    course_id: str,
    assignment_id: str,
    rubric_data: Optional[List[Dict]] = None,
    rubric_settings: Optional[Dict] = None,
    client: Optional[CanvasClient] = None
) -> Tuple[bool, Any]:
    """
    Update an assignment's rubric on Canvas.

    Args:
        course_id: Canvas course ID
        assignment_id: Canvas assignment ID
        rubric_data: List of criterion dicts (optional, uses existing if not provided)
        rubric_settings: Rubric settings dict (optional)
        client: Optional CanvasClient instance

    Returns:
        Tuple of (success, result/error)
    """
    canvas = client or get_canvas_client()

    try:
        # Get current rubric if data not provided
        if rubric_data is None or rubric_settings is None:
            current_rubric = get_rubric(course_id, assignment_id, client)
            if current_rubric:
                if rubric_data is None:
                    rubric_data = current_rubric.get('data', [])
                if rubric_settings is None:
                    rubric_settings = current_rubric.get('rubric_settings', {})
            else:
                if rubric_data is None:
                    return False, "No rubric data provided and no existing rubric found"
                if rubric_settings is None:
                    rubric_settings = {}

        # Prepare the rubric data for Canvas API
        api_data = {}

        # Add rubric title and settings
        api_data["rubric[title]"] = rubric_settings.get('title', f"Rubric for assignment {assignment_id}")
        api_data["rubric[free_form_criterion_comments]"] = "1" if rubric_settings.get('free_form_criterion_comments', False) else "0"
        api_data["rubric_association[use_for_grading]"] = "1" if rubric_settings.get('use_for_grading', True) else "0"
        api_data["rubric_association[hide_score_total]"] = "0"
        api_data["rubric_association[purpose]"] = "grading"

        # Add association info
        api_data["rubric_association[association_id]"] = assignment_id
        api_data["rubric_association[association_type]"] = "Assignment"

        # Add rubric criteria
        for idx, criterion in enumerate(rubric_data):
            criterion_id = criterion.get('id')
            description = criterion.get('description', '')
            long_description = criterion.get('long_description', '')
            points = criterion.get('points', 0)

            api_data[f"rubric[criteria][{idx}][description]"] = description
            api_data[f"rubric[criteria][{idx}][long_description]"] = long_description
            api_data[f"rubric[criteria][{idx}][points]"] = points

            if criterion_id and criterion_id != "null":
                api_data[f"rubric[criteria][{idx}][id]"] = criterion_id

            # Add ratings
            for rating_idx, rating in enumerate(criterion.get('ratings', [])):
                rating_id = rating.get('id')
                api_data[f"rubric[criteria][{idx}][ratings][{rating_idx}][description]"] = rating.get('description', '')
                api_data[f"rubric[criteria][{idx}][ratings][{rating_idx}][long_description]"] = rating.get('long_description', '')
                api_data[f"rubric[criteria][{idx}][ratings][{rating_idx}][points]"] = rating.get('points', 0)

                if rating_id and rating_id != "null":
                    api_data[f"rubric[criteria][{idx}][ratings][{rating_idx}][id]"] = rating_id

        # Make the API call
        headers = {'Authorization': f'Bearer {canvas.token}'}
        url = f'https://{canvas.domain}/api/v1/courses/{course_id}/rubrics'

        logger.debug(f"Sending rubric update to Canvas")
        response = requests.post(url, headers=headers, data=api_data)

        if 200 <= response.status_code < 300:
            logger.info(f"Successfully updated rubric for assignment {assignment_id}")

            # Refresh and return the updated rubric
            updated_rubric = get_rubric(course_id, assignment_id, client)
            return True, updated_rubric
        else:
            logger.error(f"Error updating rubric: {response.status_code}, {response.text}")
            return False, f"Error: {response.status_code}, {response.text}"

    except Exception as e:
        logger.error(f"Unexpected error updating rubric: {str(e)}", exc_info=True)
        return False, str(e)


def sync_rubric_ids(
    local_rubric: Dict[str, Any],
    canvas_rubric: Dict[str, Any]
) -> Tuple[bool, str, Dict[str, str]]:
    """
    Sync Canvas-assigned IDs to local rubric data.

    Args:
        local_rubric: Local rubric data (will be modified in place)
        canvas_rubric: Canvas rubric with assigned IDs

    Returns:
        Tuple of (success, message, id_mapping)
    """
    try:
        canvas_criteria = canvas_rubric.get('data', [])
        local_criteria = local_rubric.get('data', [])

        if len(canvas_criteria) != len(local_criteria):
            return False, f"Criteria count mismatch: Canvas has {len(canvas_criteria)}, local has {len(local_criteria)}", {}

        id_mapping = {}

        for idx, (local_crit, canvas_crit) in enumerate(zip(local_criteria, canvas_criteria)):
            old_id = local_crit.get('id')
            new_id = canvas_crit.get('id')

            if new_id:
                local_crit['id'] = new_id
                if old_id:
                    id_mapping[old_id] = new_id
                logger.debug(f"Criterion {idx}: {old_id} → {new_id}")

            # Update rating IDs
            local_ratings = local_crit.get('ratings', [])
            canvas_ratings = canvas_crit.get('ratings', [])

            for rating_idx, (local_rating, canvas_rating) in enumerate(zip(local_ratings, canvas_ratings)):
                old_rating_id = local_rating.get('id')
                new_rating_id = canvas_rating.get('id')

                if new_rating_id:
                    local_rating['id'] = new_rating_id
                    if old_rating_id:
                        id_mapping[old_rating_id] = new_rating_id
                    logger.debug(f"  Rating {rating_idx}: {old_rating_id} → {new_rating_id}")

        logger.info(f"Synced {len(id_mapping)} IDs from Canvas to local rubric")
        return True, f"Synced {len(id_mapping)} IDs successfully", id_mapping

    except Exception as e:
        logger.error(f"Error syncing IDs: {e}", exc_info=True)
        return False, str(e), {}


def check_rubric_sync_status(
    course_id: str,
    assignment_id: str,
    local_rubric: Dict[str, Any],
    client: Optional[CanvasClient] = None
) -> Dict[str, Any]:
    """
    Check if local rubric is synced with Canvas.

    Args:
        course_id: Canvas course ID
        assignment_id: Canvas assignment ID
        local_rubric: Local rubric data
        client: Optional CanvasClient instance

    Returns:
        Dict with status info
    """
    local_criteria = local_rubric.get('data', [])

    try:
        canvas_rubric = get_rubric(course_id, assignment_id, client)

        if not canvas_rubric:
            return {
                "synced": False,
                "status": "no_canvas_rubric",
                "message": "No rubric found in Canvas. Ready to publish.",
                "local_criteria_count": len(local_criteria),
                "canvas_criteria_count": 0
            }

        canvas_criteria = canvas_rubric.get('data', [])

        if len(local_criteria) != len(canvas_criteria):
            return {
                "synced": False,
                "status": "count_mismatch",
                "message": f"Criteria count mismatch: Local has {len(local_criteria)}, Canvas has {len(canvas_criteria)}",
                "local_criteria_count": len(local_criteria),
                "canvas_criteria_count": len(canvas_criteria)
            }

        # Check if IDs match
        id_mismatches = 0
        for local_crit, canvas_crit in zip(local_criteria, canvas_criteria):
            if local_crit.get('id') != canvas_crit.get('id'):
                id_mismatches += 1

        if id_mismatches > 0:
            return {
                "synced": False,
                "status": "id_mismatch",
                "message": f"{id_mismatches} criteria have mismatched IDs. Re-sync recommended.",
                "local_criteria_count": len(local_criteria),
                "canvas_criteria_count": len(canvas_criteria),
                "mismatches": id_mismatches
            }

        return {
            "synced": True,
            "status": "synced",
            "message": "Local rubric is synced with Canvas",
            "local_criteria_count": len(local_criteria),
            "canvas_criteria_count": len(canvas_criteria)
        }

    except Exception as e:
        logger.error(f"Error checking sync status: {e}")
        return {
            "synced": False,
            "status": "error",
            "message": str(e),
            "local_criteria_count": len(local_criteria),
            "canvas_criteria_count": 0
        }
