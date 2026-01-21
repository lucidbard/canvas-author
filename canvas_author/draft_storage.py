"""
Draft Grade Storage Module

Local file-based storage for draft grades with versioning support.
Supports multiple draft runs per student for AI regeneration.
"""

import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime

logger = logging.getLogger("canvas_author.draft_storage")

# Default storage location (can be overridden)
DEFAULT_STORAGE_PATH = Path.home() / "canvas" / "data"


def get_draft_path(
    assignment_id: str,
    user_id: str,
    storage_path: Optional[Path] = None
) -> Path:
    """
    Get the path to a draft grade file.

    Args:
        assignment_id: Canvas assignment ID
        user_id: Canvas user ID
        storage_path: Optional custom storage path

    Returns:
        Path to draft file
    """
    base_path = storage_path or DEFAULT_STORAGE_PATH
    draft_dir = base_path / assignment_id / "drafts"
    draft_dir.mkdir(parents=True, exist_ok=True)
    return draft_dir / f"draft_grades_{user_id}.json"


def load_draft_grade(
    assignment_id: str,
    user_id: str,
    storage_path: Optional[Path] = None
) -> Optional[Dict[str, Any]]:
    """
    Load a draft grade from local storage.

    Args:
        assignment_id: Canvas assignment ID
        user_id: Canvas user ID
        storage_path: Optional custom storage path

    Returns:
        Draft grade data dict or None if not found
    """
    draft_path = get_draft_path(assignment_id, user_id, storage_path)

    if not draft_path.exists():
        logger.info(f"No draft found for user {user_id} in assignment {assignment_id}")
        return None

    try:
        with open(draft_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        logger.info(f"Loaded draft for user {user_id} in assignment {assignment_id}")
        return data
    except Exception as e:
        logger.error(f"Error loading draft: {e}")
        return None


def save_draft_grade(
    assignment_id: str,
    user_id: str,
    draft_data: Dict[str, Any],
    storage_path: Optional[Path] = None
) -> bool:
    """
    Save a draft grade to local storage.

    Args:
        assignment_id: Canvas assignment ID
        user_id: Canvas user ID
        draft_data: Draft grade data (must have 'runs' and 'current_run')
        storage_path: Optional custom storage path

    Returns:
        True if successful, False otherwise
    """
    draft_path = get_draft_path(assignment_id, user_id, storage_path)

    try:
        # Ensure draft data has required structure
        if 'runs' not in draft_data:
            draft_data['runs'] = []
        if 'current_run' not in draft_data:
            draft_data['current_run'] = None

        with open(draft_path, 'w', encoding='utf-8') as f:
            json.dump(draft_data, f, indent=2)

        logger.info(f"Saved draft for user {user_id} in assignment {assignment_id}")
        return True
    except Exception as e:
        logger.error(f"Error saving draft: {e}")
        return False


def add_draft_run(
    assignment_id: str,
    user_id: str,
    run_data: Dict[str, Any],
    set_as_current: bool = True,
    storage_path: Optional[Path] = None
) -> Optional[str]:
    """
    Add a new draft run to an existing draft grade.

    Args:
        assignment_id: Canvas assignment ID
        user_id: Canvas user ID
        run_data: Run data (rubric_assessment, comments, etc.)
        set_as_current: Whether to set this as the current run
        storage_path: Optional custom storage path

    Returns:
        Run ID if successful, None otherwise
    """
    # Load existing draft or create new one
    draft = load_draft_grade(assignment_id, user_id, storage_path) or {
        'runs': [],
        'current_run': None
    }

    # Generate run ID if not provided
    if 'run_id' not in run_data:
        run_data['run_id'] = int(datetime.now().timestamp())

    run_id = str(run_data['run_id'])

    # Ensure required fields
    if 'rubric_assessment' not in run_data:
        run_data['rubric_assessment'] = {}
    if 'instructor_modified' not in run_data:
        run_data['instructor_modified'] = False

    # Add the run
    draft['runs'].append(run_data)

    # Set as current if requested
    if set_as_current:
        draft['current_run'] = run_id

    # Save
    if save_draft_grade(assignment_id, user_id, draft, storage_path):
        logger.info(f"Added draft run {run_id} for user {user_id} in assignment {assignment_id}")
        return run_id

    return None


def get_current_run(
    assignment_id: str,
    user_id: str,
    storage_path: Optional[Path] = None
) -> Optional[Dict[str, Any]]:
    """
    Get the current draft run for a student.

    Args:
        assignment_id: Canvas assignment ID
        user_id: Canvas user ID
        storage_path: Optional custom storage path

    Returns:
        Current run data or None
    """
    draft = load_draft_grade(assignment_id, user_id, storage_path)
    if not draft or not draft.get('current_run'):
        return None

    current_run_id = str(draft['current_run'])
    for run in draft.get('runs', []):
        if str(run.get('run_id')) == current_run_id:
            return run

    return None


def set_current_run(
    assignment_id: str,
    user_id: str,
    run_id: str,
    storage_path: Optional[Path] = None
) -> bool:
    """
    Set a specific run as the current run.

    Args:
        assignment_id: Canvas assignment ID
        user_id: Canvas user ID
        run_id: Run ID to set as current
        storage_path: Optional custom storage path

    Returns:
        True if successful, False otherwise
    """
    draft = load_draft_grade(assignment_id, user_id, storage_path)
    if not draft:
        return False

    # Verify run exists
    run_exists = any(str(r.get('run_id')) == str(run_id) for r in draft.get('runs', []))
    if not run_exists:
        logger.error(f"Run {run_id} not found in draft for user {user_id}")
        return False

    draft['current_run'] = str(run_id)
    return save_draft_grade(assignment_id, user_id, draft, storage_path)


def list_draft_grades(
    assignment_id: str,
    storage_path: Optional[Path] = None
) -> List[Dict[str, Any]]:
    """
    List all draft grades for an assignment.

    Args:
        assignment_id: Canvas assignment ID
        storage_path: Optional custom storage path

    Returns:
        List of dicts with user_id and draft summary
    """
    base_path = storage_path or DEFAULT_STORAGE_PATH
    draft_dir = base_path / assignment_id / "drafts"

    if not draft_dir.exists():
        return []

    results = []
    for draft_file in draft_dir.glob("draft_grades_*.json"):
        # Extract user_id from filename
        user_id = draft_file.stem.replace("draft_grades_", "")

        try:
            with open(draft_file, 'r', encoding='utf-8') as f:
                draft = json.load(f)

            results.append({
                'user_id': user_id,
                'has_draft': True,
                'num_runs': len(draft.get('runs', [])),
                'current_run': draft.get('current_run'),
                'has_official': 'official_rubric' in draft
            })
        except Exception as e:
            logger.error(f"Error reading draft for user {user_id}: {e}")
            results.append({
                'user_id': user_id,
                'has_draft': False,
                'error': str(e)
            })

    return results


def delete_draft_grade(
    assignment_id: str,
    user_id: str,
    storage_path: Optional[Path] = None
) -> bool:
    """
    Delete a draft grade file.

    Args:
        assignment_id: Canvas assignment ID
        user_id: Canvas user ID
        storage_path: Optional custom storage path

    Returns:
        True if successful, False otherwise
    """
    draft_path = get_draft_path(assignment_id, user_id, storage_path)

    if not draft_path.exists():
        logger.info(f"No draft to delete for user {user_id} in assignment {assignment_id}")
        return True

    try:
        draft_path.unlink()
        logger.info(f"Deleted draft for user {user_id} in assignment {assignment_id}")
        return True
    except Exception as e:
        logger.error(f"Error deleting draft: {e}")
        return False


def update_run(
    assignment_id: str,
    user_id: str,
    run_id: str,
    updates: Dict[str, Any],
    storage_path: Optional[Path] = None
) -> bool:
    """
    Update an existing draft run.

    Args:
        assignment_id: Canvas assignment ID
        user_id: Canvas user ID
        run_id: Run ID to update
        updates: Dict of fields to update
        storage_path: Optional custom storage path

    Returns:
        True if successful, False otherwise
    """
    draft = load_draft_grade(assignment_id, user_id, storage_path)
    if not draft:
        return False

    # Find and update the run
    for run in draft.get('runs', []):
        if str(run.get('run_id')) == str(run_id):
            run.update(updates)
            # Mark as instructor modified if rubric_assessment was changed
            if 'rubric_assessment' in updates:
                run['instructor_modified'] = True
            return save_draft_grade(assignment_id, user_id, draft, storage_path)

    logger.error(f"Run {run_id} not found in draft for user {user_id}")
    return False


def set_official_rubric(
    assignment_id: str,
    user_id: str,
    rubric_data: Dict[str, Any],
    storage_path: Optional[Path] = None
) -> bool:
    """
    Set the official rubric (formatted for Canvas API submission).

    Args:
        assignment_id: Canvas assignment ID
        user_id: Canvas user ID
        rubric_data: Rubric data formatted for Canvas API
        storage_path: Optional custom storage path

    Returns:
        True if successful, False otherwise
    """
    draft = load_draft_grade(assignment_id, user_id, storage_path) or {
        'runs': [],
        'current_run': None
    }

    draft['official_rubric'] = rubric_data
    return save_draft_grade(assignment_id, user_id, draft, storage_path)
