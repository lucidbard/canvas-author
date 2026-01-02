"""
Sync Module

Two-way sync between Canvas wiki pages and local markdown files.
Includes automatic image download/upload with relative path rewriting.
"""

import re
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional

from .client import get_canvas_client, CanvasClient
from .pages import list_pages, get_page, create_page, update_page
from .frontmatter import parse_frontmatter, create_page_frontmatter
from .files import download_images_from_content, upload_images_from_content

logger = logging.getLogger("canvas_author.sync")


def sanitize_filename(title: str) -> str:
    """Convert a page title to a safe filename."""
    # Replace spaces and special chars with hyphens
    safe = re.sub(r'[^\w\s-]', '', title.lower())
    safe = re.sub(r'[-\s]+', '-', safe).strip('-')
    return safe


def pull_pages(
    course_id: str,
    output_dir: str,
    include_frontmatter: bool = True,
    overwrite: bool = False,
    download_images: bool = True,
    client: Optional[CanvasClient] = None
) -> Dict[str, Any]:
    """
    Pull all wiki pages from Canvas and save as markdown files.

    Args:
        course_id: Canvas course ID
        output_dir: Directory to save markdown files
        include_frontmatter: Include YAML frontmatter with metadata
        overwrite: Overwrite existing files
        download_images: Download embedded images to files/ directory
        client: Optional CanvasClient instance

    Returns:
        Dict with results: pulled, skipped, errors, images_downloaded
    """
    canvas = client or get_canvas_client()
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    pages = list_pages(course_id, canvas)
    results = {"pulled": [], "skipped": [], "errors": [], "images_downloaded": 0}

    # Get domain for URL matching
    domain = canvas.api_url.replace("https://", "").replace("http://", "").rstrip("/")

    for page_meta in pages:
        try:
            url = page_meta["url"]
            filename = f"{url}.md"
            file_path = output_path / filename

            # Skip if exists and not overwriting
            if file_path.exists() and not overwrite:
                results["skipped"].append({"url": url, "reason": "file exists"})
                continue

            # Get full page content (as markdown)
            page = get_page(course_id, url, as_markdown=True, client=canvas)
            body = page["body"]

            # Download images and rewrite URLs to relative paths
            if download_images and body:
                body, downloaded = download_images_from_content(
                    body, course_id, output_path, domain, canvas, is_html=False
                )
                results["images_downloaded"] += len(downloaded)

            # Build content
            if include_frontmatter:
                content = create_page_frontmatter(
                    title=page["title"],
                    url=url,
                    course_id=course_id,
                    published=page.get("published", True),
                    front_page=page.get("front_page", False),
                    updated_at=page.get("updated_at"),
                )
                content += body
            else:
                content = body

            # Write file
            file_path.write_text(content, encoding="utf-8")
            results["pulled"].append({"url": url, "file": str(file_path)})
            logger.info(f"Pulled page '{url}' to {file_path}")

        except Exception as e:
            results["errors"].append({"url": page_meta.get("url", "unknown"), "error": str(e)})
            logger.error(f"Error pulling page: {e}")

    logger.info(f"Pull complete: {len(results['pulled'])} pulled, {len(results['skipped'])} skipped, {len(results['errors'])} errors")
    return results


def push_pages(
    course_id: str,
    input_dir: str,
    create_missing: bool = True,
    update_existing: bool = True,
    upload_images: bool = True,
    client: Optional[CanvasClient] = None
) -> Dict[str, Any]:
    """
    Push local markdown files to Canvas as wiki pages.

    Args:
        course_id: Canvas course ID
        input_dir: Directory containing markdown files
        create_missing: Create pages that don't exist on Canvas
        update_existing: Update pages that already exist
        upload_images: Upload local images to Canvas
        client: Optional CanvasClient instance

    Returns:
        Dict with results: created, updated, skipped, errors, images_uploaded
    """
    canvas = client or get_canvas_client()
    input_path = Path(input_dir)
    if not input_path.exists():
        raise ValueError(f"Input directory does not exist: {input_dir}")

    # Get existing pages
    existing_pages = {p["url"]: p for p in list_pages(course_id, canvas)}

    results = {"created": [], "updated": [], "skipped": [], "errors": [], "images_uploaded": 0}

    for file_path in input_path.glob("*.md"):
        try:
            content = file_path.read_text(encoding="utf-8")
            metadata, body = parse_frontmatter(content)

            # Determine page URL
            url = metadata.get("url") or file_path.stem
            title = metadata.get("title") or file_path.stem.replace("-", " ").title()
            published = metadata.get("published", True)

            # Upload images and rewrite URLs to Canvas paths
            if upload_images and body:
                body, uploaded = upload_images_from_content(
                    body, course_id, input_path, canvas, is_markdown=True
                )
                results["images_uploaded"] += len(uploaded)

            if url in existing_pages:
                if update_existing:
                    update_page(
                        course_id=course_id,
                        page_url=url,
                        title=title,
                        body=body,
                        from_markdown=True,
                        published=published if isinstance(published, bool) else True,
                        client=canvas,
                    )
                    results["updated"].append({"url": url, "file": str(file_path)})
                    logger.info(f"Updated page '{url}' from {file_path}")
                else:
                    results["skipped"].append({"url": url, "reason": "exists, update disabled"})
            else:
                if create_missing:
                    create_page(
                        course_id=course_id,
                        title=title,
                        body=body,
                        from_markdown=True,
                        published=published if isinstance(published, bool) else True,
                        client=canvas,
                    )
                    results["created"].append({"url": url, "file": str(file_path)})
                    logger.info(f"Created page '{url}' from {file_path}")
                else:
                    results["skipped"].append({"url": url, "reason": "not on Canvas, create disabled"})

        except Exception as e:
            results["errors"].append({"file": str(file_path), "error": str(e)})
            logger.error(f"Error pushing {file_path}: {e}")

    logger.info(f"Push complete: {len(results['created'])} created, {len(results['updated'])} updated, {len(results['skipped'])} skipped, {len(results['errors'])} errors")
    return results


def sync_status(
    course_id: str,
    local_dir: str,
    client: Optional[CanvasClient] = None
) -> Dict[str, Any]:
    """
    Check sync status between Canvas and local files.

    Args:
        course_id: Canvas course ID
        local_dir: Directory containing local markdown files
        client: Optional CanvasClient instance

    Returns:
        Dict with status for each page
    """
    local_path = Path(local_dir)

    # Get Canvas pages
    canvas_pages = {p["url"]: p for p in list_pages(course_id, client)}

    # Get local files
    local_files = {}
    if local_path.exists():
        for file_path in local_path.glob("*.md"):
            content = file_path.read_text(encoding="utf-8")
            metadata, body = parse_frontmatter(content)
            url = metadata.get("url") or file_path.stem
            local_files[url] = {
                "file": str(file_path),
                "metadata": metadata,
                "has_content": bool(body.strip()),
            }

    # Build status
    all_urls = set(canvas_pages.keys()) | set(local_files.keys())

    status = {
        "canvas_only": [],
        "local_only": [],
        "both": [],
        "summary": {
            "total_canvas": len(canvas_pages),
            "total_local": len(local_files),
            "in_sync": 0,
            "canvas_only": 0,
            "local_only": 0,
        }
    }

    for url in all_urls:
        in_canvas = url in canvas_pages
        in_local = url in local_files

        if in_canvas and in_local:
            status["both"].append({
                "url": url,
                "canvas_updated": canvas_pages[url].get("updated_at"),
                "local_file": local_files[url]["file"],
            })
            status["summary"]["in_sync"] += 1
        elif in_canvas:
            status["canvas_only"].append({
                "url": url,
                "title": canvas_pages[url].get("title"),
            })
            status["summary"]["canvas_only"] += 1
        else:
            status["local_only"].append({
                "url": url,
                "file": local_files[url]["file"],
            })
            status["summary"]["local_only"] += 1

    return status
