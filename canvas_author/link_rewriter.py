"""
Link Rewriting for Canvas Compatibility

Rewrites relative markdown links to absolute Canvas URLs to ensure they work correctly
in Canvas pages and assignments.
"""

import re
import logging
from typing import Tuple, List, Dict

logger = logging.getLogger("canvas_author.link_rewriter")


def rewrite_canvas_links(content: str, course_id: str) -> Tuple[str, List[Dict[str, str]]]:
    """
    Rewrite relative links in markdown to absolute Canvas URLs.

    Canvas requires absolute URLs for cross-linking between pages, assignments,
    quizzes, and discussions. Relative links like (./page-name) or (../assignments/123)
    don't work correctly in Canvas.

    Args:
        content: Markdown content with relative links
        course_id: Canvas course ID

    Returns:
        Tuple of (rewritten_content, list of rewrite records)

    Examples:
        >>> content = "[Quiz](../quizzes/123)"
        >>> rewritten, _ = rewrite_canvas_links(content, "1503378")
        >>> rewritten
        '[Quiz](https://webcourses.ucf.edu/courses/1503378/quizzes/123)'
    """
    rewrites = []

    # Pattern 1: Quiz links - ../quizzes/ID or /quizzes/ID
    def rewrite_quiz(match):
        quiz_id = match.group(2)
        old_link = match.group(0)
        new_link = f"{match.group(1)}(https://webcourses.ucf.edu/courses/{course_id}/quizzes/{quiz_id})"
        rewrites.append({"type": "quiz", "old": old_link, "new": new_link})
        return new_link

    content = re.sub(
        r'(\[[^\]]+\])\(\.\.\/quizzes\/(\d+)\)',
        rewrite_quiz,
        content
    )

    # Pattern 2: Assignment links - ../assignments/ID or /assignments/ID
    def rewrite_assignment(match):
        assignment_id = match.group(2)
        old_link = match.group(0)
        new_link = f"{match.group(1)}(https://webcourses.ucf.edu/courses/{course_id}/assignments/{assignment_id})"
        rewrites.append({"type": "assignment", "old": old_link, "new": new_link})
        return new_link

    content = re.sub(
        r'(\[[^\]]+\])\(\.\.\/assignments\/(\d+)\)',
        rewrite_assignment,
        content
    )

    # Pattern 3: Discussion links - ../discussion_topics/ID
    def rewrite_discussion(match):
        discussion_id = match.group(2)
        old_link = match.group(0)
        new_link = f"{match.group(1)}(https://webcourses.ucf.edu/courses/{course_id}/discussion_topics/{discussion_id})"
        rewrites.append({"type": "discussion", "old": old_link, "new": new_link})
        return new_link

    content = re.sub(
        r'(\[[^\]]+\])\(\.\.\/discussion_topics\/(\d+)\)',
        rewrite_discussion,
        content
    )

    # Pattern 4: Module links - ../modules/ID
    def rewrite_module(match):
        module_id = match.group(2)
        old_link = match.group(0)
        new_link = f"{match.group(1)}(https://webcourses.ucf.edu/courses/{course_id}/modules/{module_id})"
        rewrites.append({"type": "module", "old": old_link, "new": new_link})
        return new_link

    content = re.sub(
        r'(\[[^\]]+\])\(\.\.\/modules\/(\d+)\)',
        rewrite_module,
        content
    )

    # Pattern 5: Page links WITHOUT api-endpoint (bare links that will break)
    # Match: [text](page-name) or [text](./page-name.md)
    # But NOT: [text](...){api-endpoint="..."} (already has Canvas metadata)
    def rewrite_page(match):
        link_text = match.group(1)
        page_name = match.group(2).replace('.md', '').replace('./', '')
        old_link = match.group(0)
        new_link = f"[{link_text}](/courses/{course_id}/pages/{page_name})"
        rewrites.append({"type": "page", "old": old_link, "new": new_link})
        return new_link

    # Only rewrite if NOT followed by {api-endpoint
    content = re.sub(
        r'\[([^\]]+)\]\((\.\/)?([a-z0-9\-]+(?:\.md)?)\)(?!\{api-endpoint)',
        rewrite_page,
        content
    )

    if rewrites:
        logger.info(f"Rewrote {len(rewrites)} links: "
                   f"{sum(1 for r in rewrites if r['type'] == 'quiz')} quizzes, "
                   f"{sum(1 for r in rewrites if r['type'] == 'assignment')} assignments, "
                   f"{sum(1 for r in rewrites if r['type'] == 'discussion')} discussions, "
                   f"{sum(1 for r in rewrites if r['type'] == 'page')} pages")

    return content, rewrites
