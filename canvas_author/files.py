"""
Files Module

Handles downloading and uploading files to Canvas,
with automatic URL rewriting for local/remote references.

Large files (>2MB by default) create placeholder files and can be downloaded on demand.
"""

import re
import logging
import hashlib
import json
import mimetypes
import requests
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, List
from urllib.parse import urlparse, unquote

from .client import get_canvas_client, CanvasClient

logger = logging.getLogger("canvas_author.files")

# Default size threshold for automatic download (2MB)
DEFAULT_SIZE_THRESHOLD = 2 * 1024 * 1024  # 2MB in bytes

# Pattern to match Canvas file URLs in content
# Matches: /courses/123/files/456/download, /files/456/download, etc.
CANVAS_FILE_URL_PATTERN = re.compile(
    r'/courses/\d+/files/(\d+)(?:/[^"\s)]*)?|'
    r'/files/(\d+)(?:/[^"\s)]*)?',
    re.IGNORECASE
)

# Pattern to match image tags in HTML
HTML_IMG_PATTERN = re.compile(
    r'<img[^>]+src=["\']([^"\']+)["\'][^>]*>',
    re.IGNORECASE
)

# Pattern to match markdown images
MD_IMG_PATTERN = re.compile(
    r'!\[([^\]]*)\]\(([^)]+)\)'
)

# Files directory name
FILES_DIR = "files"

# Placeholder file extension for large files not yet downloaded
PLACEHOLDER_EXT = ".canvas-pending"


def get_file_id_from_url(url: str) -> Optional[str]:
    """Extract Canvas file ID from a URL."""
    match = CANVAS_FILE_URL_PATTERN.search(url)
    if match:
        return match.group(1) or match.group(2)
    return None


def get_file_info(
    file_id: str,
    course_id: str,
    client: Optional[CanvasClient] = None
) -> Optional[Dict[str, Any]]:
    """
    Get file metadata from Canvas without downloading.

    Args:
        file_id: Canvas file ID
        course_id: Canvas course ID
        client: Optional CanvasClient instance

    Returns:
        Dict with file info or None if not found
    """
    canvas = client or get_canvas_client()
    course = canvas.get_course(course_id)

    try:
        file_obj = course.get_file(file_id)
        return {
            "id": file_obj.id,
            "display_name": file_obj.display_name,
            "filename": file_obj.filename,
            "size": file_obj.size,
            "content_type": getattr(file_obj, "content-type", None) or getattr(file_obj, "content_type", None),
            "url": file_obj.url,
            "created_at": str(getattr(file_obj, "created_at", None)),
            "updated_at": str(getattr(file_obj, "updated_at", None)),
        }
    except Exception as e:
        logger.error(f"Failed to get file info for {file_id}: {e}")
        return None


def create_placeholder_file(
    file_info: Dict[str, Any],
    output_path: Path
) -> Path:
    """
    Create a placeholder file for a large file not yet downloaded.

    The placeholder contains metadata needed to download the file later.
    """
    placeholder_path = output_path.with_suffix(output_path.suffix + PLACEHOLDER_EXT)
    placeholder_data = {
        "file_id": file_info["id"],
        "display_name": file_info["display_name"],
        "size": file_info["size"],
        "content_type": file_info.get("content_type"),
        "canvas_url": file_info.get("url"),
        "status": "pending",
        "reason": f"File size ({file_info['size']:,} bytes) exceeds threshold",
    }
    placeholder_path.write_text(json.dumps(placeholder_data, indent=2))
    logger.info(f"Created placeholder for large file: {placeholder_path}")
    return placeholder_path


def download_file(
    file_id: str,
    course_id: str,
    output_dir: Path,
    client: Optional[CanvasClient] = None,
    preserve_name: bool = True,
    size_threshold: Optional[int] = None,
    force: bool = False
) -> Optional[Path]:
    """
    Download a file from Canvas to local directory.

    Args:
        file_id: Canvas file ID
        course_id: Canvas course ID
        output_dir: Directory to save file (usually course_dir/files)
        client: Optional CanvasClient instance
        preserve_name: If True, use original filename; otherwise use file_id
        size_threshold: Max file size to auto-download (None = no limit, use DEFAULT_SIZE_THRESHOLD for default)
        force: If True, download even if exceeds threshold

    Returns:
        Path to downloaded file, or placeholder path if too large, or None if failed
    """
    canvas = client or get_canvas_client()
    course = canvas.get_course(course_id)

    try:
        file_obj = course.get_file(file_id)
        filename = file_obj.display_name if preserve_name else f"{file_id}"
        
        # Ensure unique filename using file_id prefix to avoid collisions
        # Format: {file_id}-{original_name}
        safe_filename = f"{file_id}-{filename}"
        
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / safe_filename

        # Check if already downloaded
        if output_path.exists():
            logger.debug(f"File already exists: {output_path}")
            return output_path

        # Check if placeholder exists
        placeholder_path = output_path.with_suffix(output_path.suffix + PLACEHOLDER_EXT)
        
        # Check file size against threshold
        file_size = getattr(file_obj, 'size', 0) or 0
        if size_threshold is not None and file_size > size_threshold and not force:
            # Create placeholder instead of downloading
            file_info = {
                "id": file_obj.id,
                "display_name": file_obj.display_name,
                "size": file_size,
                "content_type": getattr(file_obj, "content-type", None) or getattr(file_obj, "content_type", None),
                "url": file_obj.url,
            }
            return create_placeholder_file(file_info, output_path)

        # Remove placeholder if exists (we're downloading now)
        if placeholder_path.exists():
            placeholder_path.unlink()

        # Download the file
        download_url = file_obj.url
        response = requests.get(download_url, stream=True, timeout=60)
        response.raise_for_status()

        with open(output_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        logger.info(f"Downloaded file {file_id} to {output_path}")
        return output_path

    except Exception as e:
        logger.error(f"Failed to download file {file_id}: {e}")
        return None


def upload_file(
    local_path: Path,
    course_id: str,
    folder: str = "Uploaded Media",
    client: Optional[CanvasClient] = None
) -> Optional[Dict[str, Any]]:
    """
    Upload a local file to Canvas.

    Args:
        local_path: Path to local file
        course_id: Canvas course ID
        folder: Canvas folder name to upload to
        client: Optional CanvasClient instance

    Returns:
        Dict with file info including 'id' and 'url', or None if failed
    """
    canvas = client or get_canvas_client()
    course = canvas.get_course(course_id)

    if not local_path.exists():
        logger.error(f"File not found: {local_path}")
        return None

    try:
        # Upload to Canvas
        # The canvasapi library handles the multi-step upload process
        result = course.upload(
            str(local_path),
            parent_folder_path=folder
        )

        if result[0]:  # Success
            file_info = result[1]
            logger.info(f"Uploaded {local_path.name} to Canvas as file {file_info.get('id')}")
            return {
                "id": file_info.get("id"),
                "url": file_info.get("url"),
                "display_name": file_info.get("display_name"),
                "preview_url": file_info.get("preview_url"),
            }
        else:
            logger.error(f"Upload failed for {local_path}")
            return None

    except Exception as e:
        logger.error(f"Failed to upload file {local_path}: {e}")
        return None


def extract_image_urls_from_html(html: str) -> List[str]:
    """Extract all image URLs from HTML content."""
    urls = []
    for match in HTML_IMG_PATTERN.finditer(html):
        urls.append(match.group(1))
    return urls


def extract_image_urls_from_markdown(markdown: str) -> List[Tuple[str, str]]:
    """
    Extract all image references from markdown content.

    Returns:
        List of (alt_text, url) tuples
    """
    images = []
    for match in MD_IMG_PATTERN.finditer(markdown):
        images.append((match.group(1), match.group(2)))
    return images


def download_images_from_content(
    content: str,
    course_id: str,
    output_dir: Path,
    domain: str,
    client: Optional[CanvasClient] = None,
    is_html: bool = True
) -> Tuple[str, Dict[str, Path]]:
    """
    Download all Canvas images from content and return rewritten content.

    Args:
        content: HTML or markdown content
        course_id: Canvas course ID
        output_dir: Base course directory
        domain: Canvas domain
        client: Optional CanvasClient instance
        is_html: Whether content is HTML (True) or markdown (False)

    Returns:
        Tuple of (rewritten_content, {original_url: local_path})
    """
    files_dir = output_dir / FILES_DIR
    downloaded = {}

    def replace_url(url: str) -> str:
        """Download file and return relative path."""
        # Skip external URLs
        if url.startswith('http') and domain not in url:
            return url
        
        # Skip data URIs
        if url.startswith('data:'):
            return url

        # Skip already-local paths
        if url.startswith('./') or url.startswith(f'./{FILES_DIR}/'):
            return url

        file_id = get_file_id_from_url(url)
        if not file_id:
            # Try to get file_id from full URL
            if f'/courses/{course_id}/files/' in url:
                match = re.search(r'/files/(\d+)', url)
                if match:
                    file_id = match.group(1)

        if file_id:
            local_path = download_file(file_id, course_id, files_dir, client)
            if local_path:
                rel_path = f"./{FILES_DIR}/{local_path.name}"
                downloaded[url] = local_path
                return rel_path

        return url

    if is_html:
        # Replace in HTML img tags
        def replace_html_img(match):
            full_tag = match.group(0)
            url = match.group(1)
            new_url = replace_url(url)
            return full_tag.replace(url, new_url)

        content = HTML_IMG_PATTERN.sub(replace_html_img, content)
    else:
        # Replace in markdown
        def replace_md_img(match):
            alt_text = match.group(1)
            url = match.group(2)
            new_url = replace_url(url)
            return f"![{alt_text}]({new_url})"

        content = MD_IMG_PATTERN.sub(replace_md_img, content)

    return content, downloaded


def upload_images_from_content(
    content: str,
    course_id: str,
    base_dir: Path,
    client: Optional[CanvasClient] = None,
    is_markdown: bool = True
) -> Tuple[str, Dict[str, str]]:
    """
    Upload local images from content and return rewritten content with Canvas URLs.

    Args:
        content: Markdown or HTML content
        course_id: Canvas course ID
        base_dir: Base directory for resolving relative paths
        client: Optional CanvasClient instance
        is_markdown: Whether content is markdown (True) or HTML (False)

    Returns:
        Tuple of (rewritten_content, {local_path: canvas_url})
    """
    uploaded = {}
    upload_cache: Dict[str, str] = {}  # Cache by file hash to avoid re-uploading

    def get_file_hash(path: Path) -> str:
        """Get MD5 hash of file for deduplication."""
        hasher = hashlib.md5()
        with open(path, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                hasher.update(chunk)
        return hasher.hexdigest()

    def upload_and_get_url(local_ref: str) -> str:
        """Upload file and return Canvas URL."""
        # Skip external URLs
        if local_ref.startswith('http'):
            return local_ref
        
        # Skip data URIs
        if local_ref.startswith('data:'):
            return local_ref

        # Resolve relative path
        if local_ref.startswith('./'):
            local_path = base_dir / local_ref[2:]
        else:
            local_path = base_dir / local_ref

        if not local_path.exists():
            logger.warning(f"Image not found: {local_path}")
            return local_ref

        # Check cache by hash
        file_hash = get_file_hash(local_path)
        if file_hash in upload_cache:
            return upload_cache[file_hash]

        # Upload to Canvas
        result = upload_file(local_path, course_id, "Uploaded Media", client)
        if result:
            # Construct the proper Canvas URL for embedding
            canvas_url = f"/courses/{course_id}/files/{result['id']}/preview"
            uploaded[str(local_path)] = canvas_url
            upload_cache[file_hash] = canvas_url
            return canvas_url

        return local_ref

    if is_markdown:
        # Replace in markdown images
        def replace_md_img(match):
            alt_text = match.group(1)
            url = match.group(2)
            new_url = upload_and_get_url(url)
            return f"![{alt_text}]({new_url})"

        content = MD_IMG_PATTERN.sub(replace_md_img, content)
    else:
        # Replace in HTML img tags
        def replace_html_img(match):
            full_tag = match.group(0)
            url = match.group(1)
            new_url = upload_and_get_url(url)
            return full_tag.replace(url, new_url)

        content = HTML_IMG_PATTERN.sub(replace_html_img, content)

    return content, uploaded


def list_course_files(
    course_id: str,
    folder: Optional[str] = None,
    client: Optional[CanvasClient] = None
) -> List[Dict[str, Any]]:
    """
    List files in a Canvas course.

    Args:
        course_id: Canvas course ID
        folder: Optional folder path to filter
        client: Optional CanvasClient instance

    Returns:
        List of file metadata dicts
    """
    canvas = client or get_canvas_client()
    course = canvas.get_course(course_id)

    files = course.get_files()
    result = []

    for f in files:
        file_info = {
            "id": f.id,
            "display_name": f.display_name,
            "filename": f.filename,
            "size": f.size,
            "content_type": getattr(f, "content-type", None) or getattr(f, "content_type", None),
            "url": f.url,
            "folder_id": f.folder_id,
            "created_at": str(getattr(f, "created_at", None)),
            "updated_at": str(getattr(f, "updated_at", None)),
        }
        result.append(file_info)

    return result


def pull_course_files(
    course_id: str,
    output_dir: str,
    size_threshold: int = DEFAULT_SIZE_THRESHOLD,
    overwrite: bool = False,
    client: Optional[CanvasClient] = None
) -> Dict[str, Any]:
    """
    Pull all files from a Canvas course to local directory.

    Large files (exceeding size_threshold) create placeholder files instead of
    downloading. Use download_pending_files() to download them later.

    Args:
        course_id: Canvas course ID
        output_dir: Directory to save files
        size_threshold: Max file size in bytes to auto-download (default: 2MB)
        overwrite: Overwrite existing files
        client: Optional CanvasClient instance

    Returns:
        Dict with results: downloaded, skipped, pending (large files), errors
    """
    canvas = client or get_canvas_client()
    output_path = Path(output_dir)
    files_dir = output_path / FILES_DIR
    files_dir.mkdir(parents=True, exist_ok=True)

    result = {
        "downloaded": [],
        "skipped": [],
        "pending": [],  # Large files with placeholders
        "errors": [],
        "total_size_downloaded": 0,
        "total_size_pending": 0,
    }

    course_files = list_course_files(course_id, client=canvas)
    logger.info(f"Found {len(course_files)} files in course {course_id}")

    for file_info in course_files:
        file_id = str(file_info["id"])
        filename = file_info["display_name"]
        size = file_info.get("size", 0) or 0
        safe_filename = f"{file_id}-{filename}"
        file_path = files_dir / safe_filename
        placeholder_path = file_path.with_suffix(file_path.suffix + PLACEHOLDER_EXT)

        try:
            # Check if already exists
            if file_path.exists() and not overwrite:
                result["skipped"].append({
                    "file_id": file_id,
                    "filename": filename,
                    "reason": "already downloaded",
                })
                continue

            # Check if placeholder exists and we're not overwriting
            if placeholder_path.exists() and not overwrite:
                result["skipped"].append({
                    "file_id": file_id,
                    "filename": filename,
                    "reason": "placeholder exists",
                })
                continue

            # Download or create placeholder
            downloaded_path = download_file(
                file_id, course_id, files_dir, canvas,
                size_threshold=size_threshold,
                force=False
            )

            if downloaded_path:
                if str(downloaded_path).endswith(PLACEHOLDER_EXT):
                    result["pending"].append({
                        "file_id": file_id,
                        "filename": filename,
                        "size": size,
                        "placeholder": str(downloaded_path),
                    })
                    result["total_size_pending"] += size
                else:
                    result["downloaded"].append({
                        "file_id": file_id,
                        "filename": filename,
                        "size": size,
                        "path": str(downloaded_path),
                    })
                    result["total_size_downloaded"] += size

        except Exception as e:
            logger.error(f"Error downloading file {file_id}: {e}")
            result["errors"].append({
                "file_id": file_id,
                "filename": filename,
                "error": str(e),
            })

    logger.info(
        f"Pull complete: {len(result['downloaded'])} downloaded, "
        f"{len(result['pending'])} pending, {len(result['skipped'])} skipped"
    )
    return result


def download_pending_files(
    course_id: str,
    files_dir: str,
    file_ids: Optional[List[str]] = None,
    client: Optional[CanvasClient] = None
) -> Dict[str, Any]:
    """
    Download files that were previously skipped due to size.

    Args:
        course_id: Canvas course ID
        files_dir: Directory containing placeholder files
        file_ids: Optional list of specific file IDs to download (None = all pending)
        client: Optional CanvasClient instance

    Returns:
        Dict with results: downloaded, errors
    """
    canvas = client or get_canvas_client()
    files_path = Path(files_dir) / FILES_DIR
    
    result = {
        "downloaded": [],
        "errors": [],
    }

    # Find all placeholder files
    placeholders = list(files_path.glob(f"*{PLACEHOLDER_EXT}"))
    
    for placeholder_path in placeholders:
        try:
            # Read placeholder data
            placeholder_data = json.loads(placeholder_path.read_text())
            file_id = str(placeholder_data.get("file_id"))
            
            # Skip if not in requested list
            if file_ids and file_id not in file_ids:
                continue

            # Download the file (force=True to bypass size threshold)
            actual_path = placeholder_path.with_suffix('')  # Remove .canvas-pending
            downloaded_path = download_file(
                file_id, course_id, files_path, canvas,
                force=True
            )

            if downloaded_path and not str(downloaded_path).endswith(PLACEHOLDER_EXT):
                result["downloaded"].append({
                    "file_id": file_id,
                    "filename": placeholder_data.get("display_name"),
                    "size": placeholder_data.get("size"),
                    "path": str(downloaded_path),
                })
            else:
                result["errors"].append({
                    "file_id": file_id,
                    "error": "Download failed",
                })

        except Exception as e:
            logger.error(f"Error downloading pending file: {e}")
            result["errors"].append({
                "placeholder": str(placeholder_path),
                "error": str(e),
            })

    logger.info(f"Downloaded {len(result['downloaded'])} pending files")
    return result


def list_pending_files(files_dir: str) -> List[Dict[str, Any]]:
    """
    List all pending (not yet downloaded) files in a directory.

    Args:
        files_dir: Directory to check for placeholder files

    Returns:
        List of pending file info dicts
    """
    files_path = Path(files_dir) / FILES_DIR
    pending = []

    if not files_path.exists():
        return pending

    for placeholder_path in files_path.glob(f"*{PLACEHOLDER_EXT}"):
        try:
            data = json.loads(placeholder_path.read_text())
            data["placeholder_path"] = str(placeholder_path)
            pending.append(data)
        except Exception as e:
            logger.warning(f"Could not read placeholder {placeholder_path}: {e}")

    return pending
