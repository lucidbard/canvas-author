"""
Submission Sync Module

Pull operations for downloading student submissions from Canvas.
Supports anonymization for blind grading.
"""

import logging
import re
import requests
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime

import yaml

from canvas_common import get_canvas_client, CanvasClient, slugify
from .assignments import list_assignments, get_assignment, list_submissions

logger = logging.getLogger("canvas_author.submission_sync")


def _download_attachment(url: str, output_path: Path, client: CanvasClient) -> bool:
    """Download an attachment file from Canvas."""
    try:
        headers = {'Authorization': f'Bearer {client.token}'}
        response = requests.get(url, headers=headers, stream=True)
        response.raise_for_status()

        with open(output_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        return True
    except Exception as e:
        logger.error(f"Failed to download attachment: {e}")
        return False


def _anonymize_submissions(
    submissions: List[Dict],
    assignment_name: str
) -> tuple:
    """
    Anonymize submission data by replacing user IDs with sequential numbers.

    Args:
        submissions: List of submission dicts
        assignment_name: Name of the assignment (for directory naming)

    Returns:
        Tuple of (anonymized_submissions, id_mapping)
    """
    id_mapping = {}
    counter = 1

    anonymized = []
    for sub in submissions:
        user_id = str(sub.get('user_id'))

        # Create mapping if not exists
        if user_id not in id_mapping:
            id_mapping[user_id] = counter
            counter += 1

        # Create anonymized copy
        anon_sub = {
            'student_number': id_mapping[user_id],
            'submission_id': sub.get('id'),
            'submitted_at': sub.get('submitted_at'),
            'score': sub.get('score'),
            'grade': sub.get('grade'),
            'workflow_state': sub.get('workflow_state'),
            'late': sub.get('late'),
            'missing': sub.get('missing'),
            'attempt': sub.get('attempt'),
        }

        # Copy attachments without user info
        if 'attachments' in sub:
            anon_sub['attachments'] = [
                {
                    'filename': att.get('filename'),
                    'content_type': att.get('content_type'),
                }
                for att in sub['attachments']
            ]

        # Copy rubric assessment without user info
        if 'rubric_assessment' in sub:
            anon_sub['rubric_assessment'] = sub['rubric_assessment']

        anonymized.append(anon_sub)

    return anonymized, id_mapping


def pull_submissions(
    course_id: str,
    assignment_id: str,
    output_dir: str,
    include_attachments: bool = True,
    anonymize: bool = False,
    client: Optional[CanvasClient] = None
) -> Dict[str, Any]:
    """
    Pull all submissions for an assignment from Canvas.

    Args:
        course_id: Canvas course ID
        assignment_id: Canvas assignment ID
        output_dir: Directory to save submissions
        include_attachments: Download attachment files (default: True)
        anonymize: Anonymize student identities (default: False)
        client: Optional CanvasClient instance

    Returns:
        Dict with 'pulled', 'skipped', and 'errors' counts
    """
    canvas = client or get_canvas_client()

    # Get assignment info
    assignment = get_assignment(course_id, assignment_id, client=canvas)
    assignment_name = assignment.get('name', f'assignment-{assignment_id}')
    slug = slugify(assignment_name)

    # Create output directory
    if anonymize:
        dir_name = f"{slug}-anonymous"
    else:
        dir_name = slug

    output_path = Path(output_dir) / dir_name
    output_path.mkdir(parents=True, exist_ok=True)

    # Get submissions
    submissions = list_submissions(
        course_id, assignment_id,
        include_user=not anonymize,
        include_rubric=True,
        client=canvas
    )

    result = {
        "pulled": 0,
        "skipped": 0,
        "errors": 0,
        "attachments_downloaded": 0,
        "directory": str(output_path),
    }

    # Build submission data
    submission_data = {
        'assignment_id': assignment_id,
        'assignment_name': assignment_name,
        'downloaded_at': datetime.now().isoformat(),
        'anonymized': anonymize,
        'submissions': [],
    }

    if anonymize:
        submissions_processed, id_mapping = _anonymize_submissions(submissions, assignment_name)
        # Store mapping separately (not in the exported file)
        mapping_path = output_path / '.id_mapping.yaml'
        with open(mapping_path, 'w', encoding='utf-8') as f:
            yaml.dump({'mapping': id_mapping}, f, default_flow_style=False)
        logger.info(f"ID mapping saved to {mapping_path} (keep private!)")
    else:
        submissions_processed = submissions
        id_mapping = None

    # Create attachments directory
    if include_attachments:
        attachments_dir = output_path / 'attachments'
        attachments_dir.mkdir(exist_ok=True)

    for i, sub in enumerate(submissions_processed):
        try:
            # Determine student identifier
            if anonymize:
                student_id = f"student-{sub['student_number']}"
            else:
                user = sub.get('user', {})
                user_name = user.get('sortable_name', user.get('name', f"user-{sub['user_id']}"))
                user_name = slugify(user_name)
                student_id = f"{user_name}_{sub['user_id']}"

            # Build submission entry for YAML
            entry = {
                'submitted_at': sub.get('submitted_at'),
                'score': sub.get('score'),
                'grade': sub.get('grade'),
                'workflow_state': sub.get('workflow_state'),
                'late': sub.get('late', False),
                'missing': sub.get('missing', False),
            }

            if not anonymize:
                entry['user_id'] = sub.get('user_id')
                entry['user_name'] = sub.get('user', {}).get('name', '')
                entry['submission_id'] = sub.get('id')
            else:
                entry['student_number'] = sub.get('student_number')

            # Handle attachments
            original_sub = submissions[i]  # Use original for attachment URLs
            if include_attachments and 'attachments' in original_sub:
                entry['attachments'] = []
                student_attach_dir = attachments_dir / student_id
                student_attach_dir.mkdir(exist_ok=True)

                for att in original_sub.get('attachments', []):
                    filename = att.get('filename', 'unknown')
                    url = att.get('url')

                    if url:
                        local_path = student_attach_dir / filename
                        if _download_attachment(url, local_path, canvas):
                            result["attachments_downloaded"] += 1
                            entry['attachments'].append({
                                'filename': filename,
                                'local_path': str(local_path.relative_to(output_path)),
                                'content_type': att.get('content_type', ''),
                            })
                        else:
                            entry['attachments'].append({
                                'filename': filename,
                                'download_failed': True,
                            })
                            result["errors"] += 1

            # Add rubric assessment if available
            if 'rubric_assessment' in original_sub:
                entry['rubric_assessment'] = original_sub['rubric_assessment']

            submission_data['submissions'].append(entry)
            result["pulled"] += 1

        except Exception as e:
            logger.error(f"Error processing submission: {e}")
            result["errors"] += 1

    # Write submissions.yaml
    yaml_path = output_path / 'submissions.yaml'
    with open(yaml_path, 'w', encoding='utf-8') as f:
        yaml.dump(submission_data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    result["file"] = str(yaml_path)

    return result


def submission_status(
    course_id: str,
    assignment_id: str,
    local_dir: Optional[str] = None,
    client: Optional[CanvasClient] = None
) -> Dict[str, Any]:
    """
    Get submission status for an assignment.

    Args:
        course_id: Canvas course ID
        assignment_id: Canvas assignment ID
        local_dir: Optional local directory to check for downloaded submissions
        client: Optional CanvasClient instance

    Returns:
        Dict with submission counts and status
    """
    canvas = client or get_canvas_client()

    # Get assignment info
    assignment = get_assignment(course_id, assignment_id, client=canvas)

    # Get submissions
    submissions = list_submissions(
        course_id, assignment_id,
        include_user=True,
        include_rubric=False,
        client=canvas
    )

    # Count by status
    total = len(submissions)
    submitted = sum(1 for s in submissions if s.get('submitted_at'))
    # A submission is graded if it has a score or grade, OR if workflow_state is 'graded'
    # This handles auto-graded quizzes where workflow_state may not be 'graded'
    graded = sum(1 for s in submissions if (s.get('score') is not None or s.get('grade') is not None or s.get('workflow_state') == 'graded'))
    pending = sum(1 for s in submissions if s.get('workflow_state') == 'pending_review')
    late = sum(1 for s in submissions if s.get('late'))
    missing = sum(1 for s in submissions if s.get('missing'))

    result = {
        'assignment_id': assignment_id,
        'assignment_name': assignment.get('name', ''),
        'total_students': total,
        'submitted': submitted,
        'not_submitted': total - submitted,
        'graded': graded,
        'pending_review': pending,
        'needs_grading': submitted - graded,
        'late': late,
        'missing': missing,
    }

    # Check if locally downloaded
    if local_dir:
        local_path = Path(local_dir)
        assignment_slug = slugify(assignment.get('name', ''))

        # Check for regular or anonymous downloads
        regular_dir = local_path / assignment_slug
        anon_dir = local_path / f"{assignment_slug}-anonymous"

        if regular_dir.exists():
            result['local_download'] = str(regular_dir)
            result['local_anonymized'] = False
        elif anon_dir.exists():
            result['local_download'] = str(anon_dir)
            result['local_anonymized'] = True
        else:
            result['local_download'] = None

    return result


def list_assignments_with_submissions(
    course_id: str,
    client: Optional[CanvasClient] = None
) -> List[Dict[str, Any]]:
    """
    List all assignments with their submission status.

    Args:
        course_id: Canvas course ID
        client: Optional CanvasClient instance

    Returns:
        List of assignments with submission counts
    """
    canvas = client or get_canvas_client()

    assignments = list_assignments(course_id, client=canvas)

    result = []
    for assignment in assignments:
        assignment_id = assignment['id']

        # Get basic submission info
        try:
            status = submission_status(course_id, assignment_id, client=canvas)
            assignment['submission_status'] = {
                'submitted': status['submitted'],
                'graded': status['graded'],
                'needs_grading': status['needs_grading'],
            }
        except Exception as e:
            logger.warning(f"Could not get submission status for {assignment_id}: {e}")
            assignment['submission_status'] = None

        result.append(assignment)

    return result


def get_all_submissions_hierarchical(
    course_id: str,
    include_user: bool = True,
    include_rubric: bool = False,
    client: Optional[CanvasClient] = None
) -> List[Dict[str, Any]]:
    """
    Get all submissions organized hierarchically by assignment.

    Perfect for UI views that want to show:
    - Assignment 1
      - Student A submission
      - Student B submission
    - Assignment 2
      - Student A submission
      - Student B submission

    Args:
        course_id: Canvas course ID
        include_user: Include user/student info in submissions
        include_rubric: Include rubric assessment data
        client: Optional CanvasClient instance

    Returns:
        List of assignment dicts, each containing:
        - id, name, due_at, points_possible (assignment metadata)
        - submissions: List of submission dicts with student info
        - submission_counts: Summary counts (submitted, graded, etc)

    Example:
        [
          {
            "id": "9397844",
            "name": "Week 1 Exercise",
            "due_at": "2026-01-17T04:59:59Z",
            "points_possible": 30,
            "submission_counts": {
              "total": 25,
              "submitted": 20,
              "graded": 15,
              "needs_grading": 5
            },
            "submissions": [
              {
                "id": "123",
                "user_id": "456",
                "user_name": "John Doe",
                "submitted_at": "2026-01-16T23:30:00Z",
                "score": 28,
                "grade": "28",
                "workflow_state": "graded",
                "late": false
              },
              ...
            ]
          },
          ...
        ]
    """
    canvas = client or get_canvas_client()

    # Get all assignments
    assignments = list_assignments(course_id, client=canvas)

    result = []
    for assignment in assignments:
        assignment_id = assignment['id']
        assignment_name = assignment.get('name', 'Untitled')

        logger.info(f"Fetching submissions for assignment: {assignment_name} ({assignment_id})")

        try:
            # Get all submissions for this assignment
            all_submissions = list_submissions(
                course_id,
                assignment_id,
                include_user=include_user,
                include_rubric=include_rubric,
                client=canvas
            )

            # Filter to only include actual submissions (exclude unsubmitted placeholder records)
            # A submission is "real" ONLY if it has been submitted (has submitted_at timestamp)
            # We don't rely on workflow_state as it can be misleading
            submissions = [
                s for s in all_submissions
                if (s.get('submitted_at') and s.get('submitted_at') != 'None')
            ]

            # Calculate counts (using all_submissions for total enrolled students)
            total_enrolled = len(all_submissions)
            submitted = sum(1 for s in submissions if s.get('submitted_at') and s.get('submitted_at') != 'None')
            # A submission is graded if it has a score or grade, OR if workflow_state is 'graded'
            # This handles auto-graded quizzes where workflow_state may not be 'graded'
            graded = sum(1 for s in submissions if (s.get('score') is not None or s.get('grade') is not None or s.get('workflow_state') == 'graded'))
            pending = sum(1 for s in submissions if s.get('workflow_state') == 'pending_review')
            late = sum(1 for s in submissions if s.get('late'))
            missing = sum(1 for s in submissions if s.get('missing'))

            # Build hierarchical structure
            assignment_with_subs = {
                'id': assignment_id,
                'name': assignment_name,
                'due_at': assignment.get('due_at'),
                'unlock_at': assignment.get('unlock_at'),
                'lock_at': assignment.get('lock_at'),
                'points_possible': assignment.get('points_possible', 0),
                'grading_type': assignment.get('grading_type', 'points'),
                'published': assignment.get('published', False),
                'html_url': assignment.get('html_url', ''),
                'submission_counts': {
                    'total': total_enrolled,
                    'submitted': submitted,
                    'not_submitted': total_enrolled - submitted,
                    'graded': graded,
                    'pending_review': pending,
                    'needs_grading': submitted - graded,
                    'late': late,
                    'missing': missing,
                },
                'submissions': submissions,  # Only actual submissions, not placeholder records
            }

            result.append(assignment_with_subs)

        except Exception as e:
            logger.error(f"Error fetching submissions for assignment {assignment_id}: {e}")
            # Include assignment even if submissions fail
            result.append({
                'id': assignment_id,
                'name': assignment_name,
                'due_at': assignment.get('due_at'),
                'points_possible': assignment.get('points_possible', 0),
                'published': assignment.get('published', False),
                'error': str(e),
                'submissions': [],
                'submission_counts': None,
            })

    logger.info(f"Retrieved submissions for {len(result)} assignments")
    return result
