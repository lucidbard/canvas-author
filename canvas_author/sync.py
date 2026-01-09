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
from .frontmatter import parse_frontmatter, create_page_frontmatter, update_frontmatter
from .files import download_images_from_content, upload_images_from_content
from .exceptions import URLMismatchError

logger = logging.getLogger("canvas_author.sync")


def predict_canvas_url(title: str) -> str:
    """
    Predict what URL Canvas will generate from a page title.

    Canvas converts titles to URLs by:
    - Converting to lowercase
    - Replacing spaces and special chars with hyphens
    - Removing consecutive hyphens
    - Stripping leading/trailing hyphens

    Args:
        title: The page title

    Returns:
        The predicted Canvas-generated URL slug

    Examples:
        >>> predict_canvas_url("Notes for Week 4, Day 1")
        'notes-for-week-4-day-1'
        >>> predict_canvas_url("Hello World!")
        'hello-world'
    """
    # Canvas URL generation: lowercase, replace non-alphanumeric with hyphens
    url = re.sub(r'[^\w\s-]', '', title.lower())
    url = re.sub(r'[-\s]+', '-', url).strip('-')
    return url


def update_internal_links(
    directory: Path,
    old_url: str,
    new_url: str,
    exclude_file: Optional[Path] = None
) -> List[str]:
    """
    Update internal links in markdown files when a page URL changes.

    Args:
        directory: Directory containing markdown files
        old_url: The old URL/slug being replaced
        new_url: The new Canvas-generated URL
        exclude_file: Optional file to exclude from updates (usually the renamed file itself)

    Returns:
        List of files that were updated
    """
    updated_files = []

    # Patterns to match links to the old URL
    # Matches: [text](old_url) or [text](old_url.md) or [text](./old_url.md)
    patterns = [
        (re.compile(rf'\]\((?:\./)?{re.escape(old_url)}(?:\.md)?\)'), f']({new_url}.md)'),
        (re.compile(rf'\]\((?:\./)?{re.escape(old_url)}(?:\.md)?#'), f']({new_url}.md#'),
    ]

    for file_path in directory.glob("*.md"):
        if exclude_file and file_path.resolve() == exclude_file.resolve():
            continue

        try:
            content = file_path.read_text(encoding="utf-8")
            original_content = content

            for pattern, replacement in patterns:
                content = pattern.sub(replacement, content)

            if content != original_content:
                file_path.write_text(content, encoding="utf-8")
                updated_files.append(str(file_path))
                logger.info(f"Updated links in {file_path}: {old_url} -> {new_url}")

        except Exception as e:
            logger.warning(f"Failed to update links in {file_path}: {e}")

    return updated_files


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
    force_rename: bool = False,
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
        force_rename: If True, allow pushing even when local URL won't match
                      Canvas-generated URL (will auto-rename local files)
        client: Optional CanvasClient instance

    Returns:
        Dict with results: created, updated, skipped, errors, images_uploaded, files_renamed

    Raises:
        URLMismatchError: When local URL won't match Canvas URL and force_rename=False
    """
    canvas = client or get_canvas_client()
    input_path = Path(input_dir)
    if not input_path.exists():
        raise ValueError(f"Input directory does not exist: {input_dir}")

    # Get existing pages
    existing_pages = {p["url"]: p for p in list_pages(course_id, canvas)}

    results = {"created": [], "updated": [], "skipped": [], "errors": [], "images_uploaded": 0, "files_renamed": []}

    for file_path in input_path.glob("*.md"):
        try:
            content = file_path.read_text(encoding="utf-8")
            metadata, body = parse_frontmatter(content)

            # Determine page URL - prefer canvas_url (Canvas-generated), fall back to url, then filename
            url = metadata.get("canvas_url") or metadata.get("url") or file_path.stem
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
                    # Check if local URL will match Canvas-generated URL
                    predicted_url = predict_canvas_url(title)
                    local_url = url

                    if predicted_url != local_url and not force_rename:
                        # Raise error - user must explicitly allow rename
                        raise URLMismatchError(
                            local_url=local_url,
                            predicted_url=predicted_url,
                            title=title,
                            file_path=str(file_path)
                        )

                    # Create the page and get Canvas-generated URL
                    created = create_page(
                        course_id=course_id,
                        title=title,
                        body=body,
                        from_markdown=True,
                        published=published if isinstance(published, bool) else True,
                        client=canvas,
                    )

                    # Canvas generates the URL from the title - it may differ from our local URL
                    canvas_url = created["url"]
                    new_file_path = file_path

                    if canvas_url != local_url:
                        logger.info(f"Canvas generated URL '{canvas_url}' differs from local '{local_url}'")

                        # Update the local file's frontmatter with Canvas-generated URL
                        updated_content = update_frontmatter(content, {
                            "canvas_url": canvas_url,
                            "updated_at": created.get("updated_at"),
                        })

                        # Remove the old 'url' field if it exists (replace with canvas_url)
                        metadata_updated, body_updated = parse_frontmatter(updated_content)
                        if "url" in metadata_updated:
                            del metadata_updated["url"]
                            from .frontmatter import generate_frontmatter
                            updated_content = generate_frontmatter(metadata_updated) + body_updated

                        file_path.write_text(updated_content, encoding="utf-8")

                        # Rename the local file to match Canvas URL
                        new_file_path = input_path / f"{canvas_url}.md"
                        if new_file_path != file_path and not new_file_path.exists():
                            file_path.rename(new_file_path)
                            logger.info(f"Renamed {file_path.name} -> {new_file_path.name}")

                            # Update links in other files that referenced the old URL
                            updated_links = update_internal_links(
                                input_path, local_url, canvas_url, exclude_file=new_file_path
                            )
                            if updated_links:
                                logger.info(f"Updated links in {len(updated_links)} files")

                    results["created"].append({
                        "url": canvas_url,
                        "file": str(new_file_path),
                        "original_file": str(file_path) if canvas_url != local_url else None,
                        "renamed": canvas_url != local_url,
                    })
                    logger.info(f"Created page '{canvas_url}' from {file_path}")
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
            url = metadata.get("canvas_url") or metadata.get("url") or file_path.stem
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
