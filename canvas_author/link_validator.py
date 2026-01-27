"""
Link Validation for Canvas Content

Validates that:
1. External links return HTTP 200
2. Published pages don't link to unpublished content
3. Internal Canvas links point to existing resources
"""

import re
import logging
import requests
from typing import Dict, List, Tuple, Optional, Set
from pathlib import Path
from urllib.parse import urlparse

from canvas_common import get_canvas_client, CanvasClient, parse_frontmatter

logger = logging.getLogger("canvas_author.link_validator")


def extract_links(content: str) -> List[Dict[str, str]]:
    """
    Extract all markdown links from content.

    Returns list of dicts with 'text', 'url', 'type' keys.
    """
    links = []

    # Pattern: [text](url) with optional {api-endpoint=...}
    pattern = r'\[([^\]]+)\]\(([^)]+)\)(?:\{[^}]+\})?'

    for match in re.finditer(pattern, content):
        link_text = match.group(1)
        url = match.group(2)

        # Classify link type
        if url.startswith('http://') or url.startswith('https://'):
            if 'webcourses.ucf.edu' in url or 'instructure.com' in url:
                link_type = 'internal_canvas'
            else:
                link_type = 'external'
        elif url.startswith('#'):
            link_type = 'anchor'
        elif url.startswith('/courses/'):
            link_type = 'internal_canvas'
        elif url.startswith('./') or '/' not in url:
            link_type = 'internal_page'
        else:
            link_type = 'unknown'

        links.append({
            'text': link_text,
            'url': url,
            'type': link_type
        })

    return links


def check_external_link(url: str, timeout: int = 10) -> Tuple[bool, Optional[int], Optional[str]]:
    """
    Check if an external URL returns HTTP 200.

    Returns:
        (is_valid, status_code, error_message)
    """
    try:
        # Use HEAD request first (faster)
        response = requests.head(url, timeout=timeout, allow_redirects=True)

        # Some servers don't support HEAD, fall back to GET
        if response.status_code == 405:
            response = requests.get(url, timeout=timeout, allow_redirects=True)

        if response.status_code == 200:
            return True, response.status_code, None
        else:
            return False, response.status_code, f"HTTP {response.status_code}"

    except requests.exceptions.Timeout:
        return False, None, "Timeout"
    except requests.exceptions.ConnectionError:
        return False, None, "Connection failed"
    except requests.exceptions.RequestException as e:
        return False, None, str(e)


def check_internal_canvas_link(url: str, course_id: str, client: Optional[CanvasClient] = None) -> Tuple[bool, Optional[str]]:
    """
    Check if an internal Canvas link points to an existing resource.

    Returns:
        (is_valid, error_message)
    """
    canvas = client or get_canvas_client()

    # Parse Canvas URL to extract resource type and ID
    # Examples:
    # /courses/123/pages/page-name
    # https://webcourses.ucf.edu/courses/123/quizzes/456

    parsed = urlparse(url)
    path = parsed.path if parsed.path else url

    # Match patterns
    page_match = re.search(r'/courses/\d+/pages/([a-z0-9\-]+)', path)
    quiz_match = re.search(r'/courses/\d+/quizzes/(\d+)', path)
    assignment_match = re.search(r'/courses/\d+/assignments/(\d+)', path)
    discussion_match = re.search(r'/courses/\d+/discussion_topics/(\d+)', path)

    try:
        if page_match:
            page_url = page_match.group(1)
            from .pages import get_page
            page = get_page(course_id, page_url, as_markdown=False, client=canvas)
            return True, None

        elif quiz_match:
            quiz_id = quiz_match.group(1)
            from .quizzes import get_quiz
            quiz = get_quiz(course_id, quiz_id, client=canvas)
            return True, None

        elif assignment_match:
            assignment_id = assignment_match.group(1)
            from .assignments import get_assignment
            assignment = get_assignment(course_id, assignment_id, client=canvas)
            return True, None

        elif discussion_match:
            discussion_id = discussion_match.group(1)
            from .discussions import get_discussion
            discussion = get_discussion(course_id, discussion_id, client=canvas)
            return True, None
        else:
            return False, "Unrecognized Canvas URL format"

    except Exception as e:
        return False, str(e)


def get_published_pages(input_dir: str) -> Set[str]:
    """
    Get set of published page URLs from local markdown files.

    Returns:
        Set of page URLs that are published
    """
    published = set()
    input_path = Path(input_dir)

    for file_path in input_path.glob("*.md"):
        try:
            content = file_path.read_text(encoding="utf-8")
            metadata, _ = parse_frontmatter(content)

            if metadata.get("published", False):
                url = metadata.get("canvas_url") or metadata.get("url") or file_path.stem
                published.add(url)
        except Exception as e:
            logger.warning(f"Error reading {file_path}: {e}")

    return published


def validate_links(
    course_id: str,
    input_dir: str,
    check_external: bool = True,
    check_unpublished: bool = True,
    external_timeout: int = 10,
    client: Optional[CanvasClient] = None
) -> Dict[str, any]:
    """
    Validate all links in markdown files.

    Args:
        course_id: Canvas course ID
        input_dir: Directory containing markdown files
        check_external: If True, validate external URLs return 200
        check_unpublished: If True, check published pages don't link to unpublished
        external_timeout: Timeout for external link checks in seconds
        client: Optional CanvasClient instance

    Returns:
        Dict with validation results:
        {
            "files_checked": int,
            "total_links": int,
            "errors": [
                {
                    "file": str,
                    "line": int (if available),
                    "link_text": str,
                    "link_url": str,
                    "error_type": "external_failed" | "unpublished_reference" | "broken_canvas_link",
                    "error_message": str
                }
            ],
            "warnings": [...],
            "external_checked": int,
            "external_failed": int,
            "unpublished_references": int
        }
    """
    results = {
        "files_checked": 0,
        "total_links": 0,
        "errors": [],
        "warnings": [],
        "external_checked": 0,
        "external_failed": 0,
        "unpublished_references": 0
    }

    input_path = Path(input_dir)

    # Get set of published pages for unpublished reference checking
    published_pages = get_published_pages(input_dir) if check_unpublished else set()

    logger.info(f"Validating links in {input_path}")
    if check_unpublished:
        logger.info(f"Found {len(published_pages)} published pages")

    for file_path in input_path.glob("*.md"):
        try:
            content = file_path.read_text(encoding="utf-8")
            metadata, body = parse_frontmatter(content)

            # Get page info
            page_url = metadata.get("canvas_url") or metadata.get("url") or file_path.stem
            is_published = metadata.get("published", False)

            # Extract links
            links = extract_links(body)
            results["files_checked"] += 1
            results["total_links"] += len(links)

            logger.debug(f"Checking {len(links)} links in {file_path.name}")

            for link in links:
                # Check external links
                if link['type'] == 'external' and check_external:
                    results["external_checked"] += 1
                    is_valid, status_code, error = check_external_link(link['url'], timeout=external_timeout)

                    if not is_valid:
                        results["external_failed"] += 1
                        results["errors"].append({
                            "file": str(file_path),
                            "link_text": link['text'],
                            "link_url": link['url'],
                            "error_type": "external_failed",
                            "error_message": f"External link failed: {error}",
                            "status_code": status_code
                        })
                        logger.warning(f"External link failed in {file_path.name}: {link['url']} - {error}")

                # Check internal Canvas links
                elif link['type'] == 'internal_canvas':
                    is_valid, error = check_internal_canvas_link(link['url'], course_id, client)

                    if not is_valid:
                        results["errors"].append({
                            "file": str(file_path),
                            "link_text": link['text'],
                            "link_url": link['url'],
                            "error_type": "broken_canvas_link",
                            "error_message": f"Canvas resource not found: {error}"
                        })
                        logger.warning(f"Broken Canvas link in {file_path.name}: {link['url']} - {error}")

                # Check unpublished references (only for published pages)
                elif link['type'] == 'internal_page' and is_published and check_unpublished:
                    # Extract page name from link
                    target_page = link['url'].replace('./', '').replace('.md', '')
                    target_page = target_page.split('/')[-1]  # Get just the page name

                    if target_page not in published_pages:
                        results["unpublished_references"] += 1
                        results["errors"].append({
                            "file": str(file_path),
                            "link_text": link['text'],
                            "link_url": link['url'],
                            "error_type": "unpublished_reference",
                            "error_message": f"Published page '{page_url}' links to unpublished page '{target_page}'"
                        })
                        logger.warning(f"Unpublished reference in {file_path.name}: {page_url} -> {target_page}")

                # Check for hash placeholders
                elif link['type'] == 'anchor' and link['url'] == '#':
                    results["warnings"].append({
                        "file": str(file_path),
                        "link_text": link['text'],
                        "link_url": link['url'],
                        "warning_type": "placeholder_link",
                        "warning_message": "Link uses '#' placeholder - needs real URL"
                    })

        except Exception as e:
            logger.error(f"Error processing {file_path}: {e}")
            results["errors"].append({
                "file": str(file_path),
                "error_type": "file_processing_error",
                "error_message": str(e)
            })

    # Summary
    logger.info(f"Validation complete: {results['files_checked']} files, {results['total_links']} links")
    logger.info(f"Errors: {len(results['errors'])}, Warnings: {len(results['warnings'])}")

    if check_external:
        logger.info(f"External links: {results['external_checked']} checked, {results['external_failed']} failed")

    if check_unpublished:
        logger.info(f"Unpublished references: {results['unpublished_references']}")

    return results


def format_validation_report(results: Dict[str, any]) -> str:
    """
    Format validation results as a readable report.
    """
    lines = []
    lines.append("=" * 70)
    lines.append("LINK VALIDATION REPORT")
    lines.append("=" * 70)
    lines.append(f"Files checked: {results['files_checked']}")
    lines.append(f"Total links: {results['total_links']}")
    lines.append(f"Errors: {len(results['errors'])}")
    lines.append(f"Warnings: {len(results['warnings'])}")
    lines.append("")

    if results.get('external_checked'):
        lines.append(f"External links checked: {results['external_checked']}")
        lines.append(f"External links failed: {results['external_failed']}")
        lines.append("")

    if results.get('unpublished_references'):
        lines.append(f"Unpublished references found: {results['unpublished_references']}")
        lines.append("")

    if results['errors']:
        lines.append("ERRORS:")
        lines.append("-" * 70)

        # Group by error type
        by_type = {}
        for error in results['errors']:
            error_type = error.get('error_type', 'unknown')
            if error_type not in by_type:
                by_type[error_type] = []
            by_type[error_type].append(error)

        for error_type, errors in by_type.items():
            lines.append(f"\n{error_type.upper().replace('_', ' ')} ({len(errors)}):")
            for error in errors[:10]:  # Limit to first 10 per type
                file_name = Path(error.get('file', 'unknown')).name
                lines.append(f"  [{file_name}] {error.get('link_text', 'N/A')}")
                lines.append(f"    URL: {error.get('link_url', 'N/A')}")
                lines.append(f"    Error: {error.get('error_message', 'N/A')}")

            if len(errors) > 10:
                lines.append(f"  ... and {len(errors) - 10} more")

    if results['warnings']:
        lines.append("\nWARNINGS:")
        lines.append("-" * 70)
        for warning in results['warnings'][:20]:  # Limit to first 20
            file_name = Path(warning.get('file', 'unknown')).name
            lines.append(f"  [{file_name}] {warning.get('link_text', 'N/A')}")
            lines.append(f"    {warning.get('warning_message', 'N/A')}")

        if len(results['warnings']) > 20:
            lines.append(f"  ... and {len(results['warnings']) - 20} more")

    lines.append("=" * 70)

    return "\n".join(lines)
