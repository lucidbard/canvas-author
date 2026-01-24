"""
Link Validation Module

Validates internal links in markdown files before pushing to Canvas.
"""

import re
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import logging

from .frontmatter import parse_frontmatter

logger = logging.getLogger("canvas_author.validation")


def extract_internal_links(content: str) -> List[Tuple[str, str, int]]:
    """
    Extract all internal Canvas links (not http/https).

    Args:
        content: Markdown content to scan

    Returns:
        List of (link_text, url, line_number) tuples
    """
    # Match markdown links: [text](url)
    pattern = r'\[([^\]]+)\]\(([^)]+)\)'
    links = []

    for match in re.finditer(pattern, content):
        url = match.group(2)
        # Skip external links
        if not url.startswith('http://') and not url.startswith('https://'):
            line_number = content[:match.start()].count('\n') + 1
            links.append((match.group(1), url, line_number))

    return links


def validate_links(input_dir: str) -> Dict[str, List[Dict[str, any]]]:
    """
    Validate all internal links in markdown files.

    Args:
        input_dir: Directory containing markdown files

    Returns:
        Dict with validation results:
        {
            "valid": List of valid links,
            "issues": List of issue dicts with file, line, url, reason,
            "stats": Summary statistics
        }
    """
    input_path = Path(input_dir)
    if not input_path.exists():
        raise ValueError(f"Input directory does not exist: {input_dir}")

    # Build set of valid page URLs (canvas_url from frontmatter)
    valid_urls = set()
    valid_files = {}

    for file_path in input_path.glob("*.md"):
        try:
            content = file_path.read_text(encoding="utf-8")
            metadata, _ = parse_frontmatter(content)
            url = metadata.get("canvas_url") or metadata.get("url") or file_path.stem
            valid_urls.add(url)
            valid_files[url] = str(file_path)
        except Exception as e:
            logger.warning(f"Could not parse {file_path}: {e}")

    # Check all links
    issues = []
    valid = []

    for file_path in input_path.glob("*.md"):
        try:
            content = file_path.read_text(encoding="utf-8")
            metadata, _ = parse_frontmatter(content)
            file_url = metadata.get("canvas_url") or metadata.get("url") or file_path.stem

            links = extract_internal_links(content)

            for link_text, url, line_number in links:
                # Skip assignment/quiz/discussion Canvas URLs (start with ../)
                if url.startswith('../'):
                    continue

                # Clean URL (remove .md extension, anchors)
                clean_url = url
                if '#' in clean_url:
                    clean_url = clean_url.split('#')[0]
                if clean_url.endswith('.md'):
                    clean_url = clean_url[:-3]

                # Check if target exists
                if clean_url in valid_urls:
                    valid.append({
                        "file": str(file_path),
                        "line": line_number,
                        "url": url,
                        "target": clean_url
                    })
                else:
                    # Check for common mistakes
                    reason = "Target page does not exist"

                    # Check if it's a filename vs canvas_url mismatch
                    for valid_url in valid_urls:
                        if clean_url.replace('-', '') == valid_url.replace('-', ''):
                            reason = f"Possible mismatch - did you mean: {valid_url}"
                            break

                    issues.append({
                        "file": str(file_path),
                        "line": line_number,
                        "url": url,
                        "clean_url": clean_url,
                        "reason": reason,
                        "link_text": link_text
                    })

        except Exception as e:
            logger.error(f"Error validating {file_path}: {e}")

    stats = {
        "total_pages": len(valid_files),
        "total_links": len(valid) + len(issues),
        "valid_links": len(valid),
        "broken_links": len(issues)
    }

    return {
        "valid": valid,
        "issues": issues,
        "stats": stats,
        "valid_urls": list(valid_urls)
    }


def format_validation_report(validation_result: Dict) -> str:
    """
    Format validation results as human-readable text.

    Args:
        validation_result: Result from validate_links()

    Returns:
        Formatted report string
    """
    stats = validation_result["stats"]
    issues = validation_result["issues"]

    lines = []
    lines.append(f"✓ Validating {stats['total_pages']} pages...")
    lines.append(f"✓ Found {stats['total_links']} internal links")
    lines.append("")

    if issues:
        lines.append("ISSUES FOUND:")
        lines.append("")

        for issue in issues:
            lines.append(f"[BROKEN LINK] {Path(issue['file']).name} line {issue['line']}")
            lines.append(f"  Links to: {issue['clean_url']}")
            lines.append(f"  {issue['reason']}")
            lines.append("")

        lines.append(f"Total: {len(issues)} issue(s) found")
    else:
        lines.append("✅ All links validated successfully!")
        lines.append(f"Total: {stats['valid_links']} valid link(s)")

    return "\n".join(lines)
