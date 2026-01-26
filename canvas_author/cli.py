#!/usr/bin/env python3
"""
Canvas MCP CLI

Non-agentic command-line interface for syncing Canvas wiki pages with local markdown files.

Usage:
    canvas-mcp init COURSE_ID [--dir DIR]     # Initialize a directory for a course
    canvas-mcp pull [--dir DIR]                # Pull pages from Canvas
    canvas-mcp push [--dir DIR]                # Push pages to Canvas
    canvas-mcp status [--dir DIR]              # Show sync status
    canvas-mcp list-courses                    # List available courses

Directory structure:
    course-dir/
    ├── .canvas.json          # Course config (course_id, name)
    ├── syllabus.md           # Wiki page with frontmatter
    ├── week-1-notes.md
    └── resources.md

Markdown frontmatter:
    ---
    title: Page Title
    page_id: canvas_page_id
    url: page-url-slug
    published: true
    updated_at: 2024-01-15T10:30:00Z
    ---
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional

from dotenv import load_dotenv

# Load environment variables from multiple possible locations
def _load_env():
    """Load .env from current dir, parent dirs, script dir, or home dir."""
    from pathlib import Path

    locations = [
        Path.cwd() / ".env",  # Current directory
    ]

    # Search up directory tree for .env
    current = Path.cwd()
    for _ in range(10):  # Limit to 10 levels up
        parent = current.parent
        if parent == current:
            break
        locations.append(parent / ".env")
        current = parent

    locations.extend([
        Path(__file__).parent.parent / ".env",  # Package root
        Path.home() / ".canvas-mcp.env",  # Home directory
    ])

    for env_file in locations:
        if env_file.exists():
            load_dotenv(env_file, override=True)
            return

_load_env()

from canvas_common import get_canvas_client
from .pages import list_pages, get_page, create_page, update_page
from .pandoc import is_pandoc_available
from .assignments import list_courses
from canvas_common import parse_frontmatter, generate_frontmatter
from .sync import predict_canvas_url, update_internal_links
from canvas_common import URLMismatchError
from . import quiz_sync, quizzes, module_sync, course_sync, rubric_sync, submission_sync, discussion_sync, announcement_sync

# Config filename
CONFIG_FILE = ".canvas.json"


def load_course_config(directory: Path) -> Optional[Dict[str, Any]]:
    """Load course config from .canvas.json in directory."""
    config_path = directory / CONFIG_FILE
    if config_path.exists():
        with open(config_path) as f:
            return json.load(f)
    return None


def save_course_config(directory: Path, config: Dict[str, Any]) -> None:
    """Save course config to .canvas.json."""
    config_path = directory / CONFIG_FILE
    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)
        f.write("\n")


def cmd_init(args: argparse.Namespace) -> int:
    """Initialize a directory for a Canvas course."""
    directory = Path(args.dir).resolve()
    course_id = args.course_id

    # Create directory if needed
    directory.mkdir(parents=True, exist_ok=True)

    # Check if already initialized
    existing_config = load_course_config(directory)
    if existing_config and not args.force:
        print(f"Error: Directory already initialized for course {existing_config.get('course_id')}")
        print("Use --force to reinitialize")
        return 1

    # Get course info from Canvas
    try:
        client = get_canvas_client()
        course = client.get_course(course_id)
        course_name = getattr(course, 'name', f'Course {course_id}')
        course_code = getattr(course, 'course_code', '')
    except Exception as e:
        print(f"Error fetching course info: {e}")
        print("Initializing with course ID only...")
        course_name = f"Course {course_id}"
        course_code = ""

    # Create config
    config = {
        "course_id": str(course_id),
        "course_name": course_name,
        "course_code": course_code,
        "initialized_at": datetime.now().isoformat(),
    }
    save_course_config(directory, config)

    print(f"Initialized {directory} for course: {course_name}")
    print(f"Course ID: {course_id}")
    print(f"\nRun 'canvas-mcp pull' to download existing pages")
    return 0


def cmd_pull(args: argparse.Namespace) -> int:
    """Pull wiki pages from Canvas to local markdown files."""
    base_directory = Path(args.dir).resolve()

    # Load config
    config = load_course_config(base_directory)
    if not config:
        print(f"Error: Directory not initialized. Run 'canvas-mcp init COURSE_ID --dir {base_directory}' first")
        return 1

    course_id = config["course_id"]

    # Use pages_directory from config if available, otherwise use base directory
    pages_subdir = config.get("pages_directory")
    if pages_subdir:
        directory = (base_directory / pages_subdir).resolve()
        if not directory.exists():
            print(f"Error: Configured pages_directory '{pages_subdir}' does not exist")
            return 1
        print(f"Using pages directory from config: {directory}")
    else:
        directory = base_directory

    # Check pandoc
    if not is_pandoc_available():
        print("Warning: pandoc not installed. HTML will not be converted to markdown.")
        print("Install with: apt install pandoc (Linux) or brew install pandoc (macOS)")

    try:
        client = get_canvas_client()
        course = client.get_course(course_id)  # Fetch once and reuse
        pages = list_pages(course_id, client, course=course)
    except Exception as e:
        print(f"Error fetching pages: {e}")
        return 1

    print(f"Found {len(pages)} pages in course {config.get('course_name', course_id)}")

    pulled = 0
    skipped = 0
    errors = 0

    for page_meta in pages:
        url = page_meta["url"]
        filename = f"{url}.md"
        file_path = directory / filename

        try:
            # Get full page content
            page = get_page(course_id, url, as_markdown=True, client=client, course=course)

            # Check if local file exists and has same page_id
            if file_path.exists() and not args.force:
                existing_content = file_path.read_text(encoding="utf-8")
                existing_meta, _ = parse_frontmatter(existing_content)

                # Skip if same page and not forcing
                if existing_meta.get("page_id") == str(page_meta.get("page_id", url)):
                    if not args.all:
                        skipped += 1
                        continue

            # Build frontmatter
            metadata = {
                "title": page["title"],
                "page_id": str(page_meta.get("page_id", url)),
                "url": url,
                "published": page.get("published", True),
                "updated_at": page.get("updated_at", ""),
            }

            # Transform Canvas links to local markdown links
            body = page["body"]
            body = course_sync.transform_links_to_local(body, course_id, client.domain)

            content = generate_frontmatter(metadata) + body

            # Write file
            file_path.write_text(content, encoding="utf-8")
            print(f"  ✓ {filename}")
            pulled += 1

        except Exception as e:
            print(f"  ✗ {filename}: {e}")
            errors += 1

    print(f"\nPulled: {pulled}, Skipped: {skipped}, Errors: {errors}")
    return 0 if errors == 0 else 1


def cmd_push(args: argparse.Namespace) -> int:
    """Push local markdown files to Canvas wiki pages."""
    base_directory = Path(args.dir).resolve()

    # Load config from base directory
    config = load_course_config(base_directory)
    if not config:
        print(f"Error: Directory not initialized. Run 'canvas-mcp init COURSE_ID --dir {base_directory}' first")
        return 1

    course_id = config["course_id"]

    # Use pages_directory from config if available, otherwise use base directory
    pages_subdir = config.get("pages_directory")
    if pages_subdir:
        directory = (base_directory / pages_subdir).resolve()
        if not directory.exists():
            print(f"Error: Configured pages_directory '{pages_subdir}' does not exist")
            return 1
        print(f"Using pages directory from config: {directory}")
    else:
        directory = base_directory

    # Check pandoc
    if not is_pandoc_available():
        print("Error: pandoc is required for push. Install with: apt install pandoc")
        return 1

    # Get existing Canvas pages
    try:
        client = get_canvas_client()
        course = client.get_course(course_id)  # Fetch once and reuse
        canvas_pages = {p["url"]: p for p in list_pages(course_id, client, course=course)}
    except Exception as e:
        print(f"Error fetching Canvas pages: {e}")
        return 1

    # Find local markdown files (recursive)
    md_files = list(directory.rglob("*.md"))
    # Exclude modules.yaml-related files and hidden directories
    md_files = [f for f in md_files if not any(p.startswith('.') for p in f.relative_to(directory).parts)]
    if not md_files:
        print("No markdown files found in directory")
        return 0

    print(f"Found {len(md_files)} markdown files")

    created = 0
    updated = 0
    skipped = 0
    errors = 0

    for file_path in sorted(md_files):
        relative_path = file_path.relative_to(directory)
        try:
            content = file_path.read_text(encoding="utf-8")
            metadata, body = parse_frontmatter(content)

            if not body.strip():
                print(f"  - {relative_path}: empty, skipping")
                skipped += 1
                continue

            # Determine page URL and title
            # Prefer canvas_url (Canvas-generated) over url (legacy) over filename
            url = metadata.get("canvas_url") or metadata.get("url") or file_path.stem
            title = metadata.get("title") or file_path.stem.replace("-", " ").title()
            published = metadata.get("published", True)
            if isinstance(published, str):
                published = published.lower() == "true"

            # Transform local links to Canvas links
            body_for_canvas = course_sync.transform_links_to_canvas(body, course_id, client.domain)

            if url in canvas_pages:
                # Update existing page
                if not args.create_only:
                    update_page(
                        course_id=course_id,
                        page_url=url,
                        title=title,
                        body=body_for_canvas,
                        from_markdown=True,
                        published=published,
                        client=client,
                        course=course,
                    )
                    print(f"  ↑ {relative_path} (updated)")
                    updated += 1

                    # Update local frontmatter with latest info
                    if not args.no_update_meta:
                        page = get_page(course_id, url, as_markdown=False, client=client, course=course)
                        metadata["updated_at"] = page.get("updated_at", "")
                        new_content = generate_frontmatter(metadata) + body
                        file_path.write_text(new_content, encoding="utf-8")
                else:
                    skipped += 1
            else:
                # Create new page
                if not args.update_only:
                    # Check if local URL will match Canvas-generated URL
                    predicted_url = predict_canvas_url(title)
                    if predicted_url != url and not args.force_rename:
                        print(f"  ✗ {relative_path}: URL mismatch!")
                        print(f"      Local URL: '{url}'")
                        print(f"      Canvas will generate: '{predicted_url}' (from title '{title}')")
                        print(f"      Use --force-rename to push anyway and auto-rename local files")
                        errors += 1
                        continue

                    result = create_page(
                        course_id=course_id,
                        title=title,
                        body=body_for_canvas,
                        from_markdown=True,
                        published=published,
                        client=client,
                        course=course,
                    )

                    canvas_url = result.get("url", url)
                    print(f"  + {relative_path} (created)")
                    created += 1

                    # Update local frontmatter with canvas_url (Canvas-generated)
                    metadata["page_id"] = canvas_url
                    metadata["canvas_url"] = canvas_url  # Canvas-generated URL
                    if "url" in metadata:
                        del metadata["url"]  # Remove old 'url' field
                    metadata["updated_at"] = result.get("updated_at", "")
                    new_content = generate_frontmatter(metadata) + body
                    file_path.write_text(new_content, encoding="utf-8")

                    # If URL differs, rename the file and update links in other files
                    if canvas_url != url:
                        new_file_path = file_path.parent / f"{canvas_url}.md"
                        if not new_file_path.exists():
                            file_path.rename(new_file_path)
                            print(f"      Renamed: {file_path.name} → {new_file_path.name}")
                            
                            # Update links in other markdown files
                            updated_files = update_internal_links(
                                directory, url, canvas_url, exclude_file=new_file_path
                            )
                            if updated_files:
                                print(f"      Updated links in {len(updated_files)} file(s)")
                else:
                    print(f"  - {relative_path}: not on Canvas, skipping (--update-only)")
                    skipped += 1

        except Exception as e:
            print(f"  ✗ {relative_path}: {e}")
            errors += 1

    print(f"\nCreated: {created}, Updated: {updated}, Skipped: {skipped}, Errors: {errors}")
    return 0 if errors == 0 else 1


def cmd_create_page(args: argparse.Namespace) -> int:
    """Create a new page on Canvas and generate a local markdown file.
    
    This command creates a page on Canvas first, then creates a local markdown
    file named after the Canvas-generated URL. This ensures the local filename
    always matches the Canvas URL, avoiding sync issues.
    """
    directory = Path(args.dir).resolve()

    # Load config
    config = load_course_config(directory)
    if not config:
        print(f"Error: Directory not initialized. Run 'canvas-mcp init COURSE_ID --dir {directory}' first")
        return 1

    course_id = config["course_id"]
    title = args.title
    published = not args.draft

    # Show what URL Canvas will generate
    predicted_url = predict_canvas_url(title)
    local_file = directory / f"{predicted_url}.md"

    # Check if local file already exists
    if local_file.exists() and not args.force:
        print(f"Error: File already exists: {local_file.name}")
        print("Use --force to overwrite")
        return 1

    # Check pandoc
    if not is_pandoc_available():
        print("Warning: pandoc not installed. Content conversion may not work correctly.")

    try:
        client = get_canvas_client()
        course = client.get_course(course_id)

        # Create initial body content
        body = args.body if args.body else f"# {title}\n\n"

        # Create the page on Canvas
        print(f"Creating page on Canvas...")
        result = create_page(
            course_id=course_id,
            title=title,
            body=body,
            from_markdown=True,
            published=published,
            client=client,
            course=course,
        )

        canvas_url = result["url"]
        print(f"  ✓ Created on Canvas: /pages/{canvas_url}")

        # Create local markdown file with Canvas-generated URL as filename
        local_file = directory / f"{canvas_url}.md"
        
        metadata = {
            "title": title,
            "canvas_url": canvas_url,
            "page_id": canvas_url,
            "published": published,
            "updated_at": result.get("updated_at", ""),
        }

        content = generate_frontmatter(metadata) + body
        local_file.write_text(content, encoding="utf-8")
        print(f"  ✓ Created local file: {local_file.name}")

        if canvas_url != predicted_url:
            print(f"  Note: Canvas generated '{canvas_url}' (predicted '{predicted_url}')")

        return 0

    except Exception as e:
        print(f"Error creating page: {e}")
        return 1


def cmd_status(args: argparse.Namespace) -> int:
    """Show sync status between local files and Canvas."""
    directory = Path(args.dir).resolve()

    # Load config
    config = load_course_config(directory)
    if not config:
        print(f"Error: Directory not initialized. Run 'canvas-mcp init COURSE_ID --dir {directory}' first")
        return 1

    course_id = config["course_id"]
    print(f"Course: {config.get('course_name', course_id)} ({course_id})")
    print(f"Directory: {directory}\n")

    # Get Canvas pages
    try:
        client = get_canvas_client()
        canvas_pages = {p["url"]: p for p in list_pages(course_id, client)}
    except Exception as e:
        print(f"Error fetching Canvas pages: {e}")
        return 1

    # Get local files
    local_files = {}
    for file_path in directory.glob("*.md"):
        content = file_path.read_text(encoding="utf-8")
        metadata, body = parse_frontmatter(content)
        url = metadata.get("url") or file_path.stem
        local_files[url] = {
            "file": file_path.name,
            "title": metadata.get("title", ""),
            "updated_at": metadata.get("updated_at", ""),
        }

    # Compare
    all_urls = set(canvas_pages.keys()) | set(local_files.keys())

    canvas_only = []
    local_only = []
    synced = []

    for url in sorted(all_urls):
        in_canvas = url in canvas_pages
        in_local = url in local_files

        if in_canvas and in_local:
            synced.append(url)
        elif in_canvas:
            canvas_only.append(url)
        else:
            local_only.append(url)

    print(f"Synced ({len(synced)}):")
    for url in synced:
        print(f"  ✓ {url}.md")

    if canvas_only:
        print(f"\nCanvas only ({len(canvas_only)}) - run 'pull' to download:")
        for url in canvas_only:
            print(f"  ↓ {url}")

    if local_only:
        print(f"\nLocal only ({len(local_only)}) - run 'push' to upload:")
        for url in local_only:
            print(f"  ↑ {local_files[url]['file']}")

    print(f"\nSummary: {len(synced)} synced, {len(canvas_only)} canvas-only, {len(local_only)} local-only")
    return 0


def cmd_list_courses(args: argparse.Namespace) -> int:
    """List available Canvas courses."""
    try:
        courses = list_courses(enrollment_state=args.state)
    except Exception as e:
        print(f"Error: {e}")
        return 1

    if not courses:
        print("No courses found")
        return 0

    print(f"Found {len(courses)} courses:\n")
    for course in courses:
        print(f"  {course['id']:>10}  {course['name']}")
        if course.get('course_code'):
            print(f"             ({course['course_code']})")

    return 0


def cmd_pull_quizzes(args: argparse.Namespace) -> int:
    """Pull quizzes from Canvas to local markdown files."""
    directory = Path(args.dir).resolve()

    # Load config
    config = load_course_config(directory)
    if not config:
        print(f"Error: Directory not initialized. Run 'canvas-mcp init COURSE_ID --dir {directory}' first")
        return 1

    course_id = config["course_id"]

    # Create quizzes subdirectory
    quiz_dir = directory / "quizzes"
    quiz_dir.mkdir(exist_ok=True)

    print(f"Pulling quizzes from course: {config.get('course_name', course_id)}")

    try:
        result = quiz_sync.pull_quizzes(course_id, str(quiz_dir), overwrite=args.force)
    except Exception as e:
        print(f"Error: {e}")
        return 1

    for item in result.get("pulled", []):
        print(f"  ✓ {item['file']} ({item['question_count']} questions)")

    for item in result.get("skipped", []):
        print(f"  - {item['file']}: skipped ({item.get('reason', 'exists')})")

    for item in result.get("errors", []):
        print(f"  ✗ {item.get('title', 'unknown')}: {item['error']}")

    pulled = len(result.get("pulled", []))
    skipped = len(result.get("skipped", []))
    errors = len(result.get("errors", []))

    print(f"\nPulled: {pulled}, Skipped: {skipped}, Errors: {errors}")
    return 0 if errors == 0 else 1


def cmd_push_quizzes(args: argparse.Namespace) -> int:
    """Push local quiz markdown files to Canvas."""
    directory = Path(args.dir).resolve()

    # Load config
    config = load_course_config(directory)
    if not config:
        print(f"Error: Directory not initialized. Run 'canvas-mcp init COURSE_ID --dir {directory}' first")
        return 1

    course_id = config["course_id"]

    # Use quizzes subdirectory
    quiz_dir = directory / "quizzes"
    if not quiz_dir.exists():
        print(f"Error: No quizzes directory found at {quiz_dir}")
        return 1

    print(f"Pushing quizzes to course: {config.get('course_name', course_id)}")

    try:
        result = quiz_sync.push_quizzes(
            course_id,
            str(quiz_dir),
            create_missing=not args.update_only,
            update_existing=not args.create_only,
        )
    except Exception as e:
        print(f"Error: {e}")
        return 1

    for item in result.get("created", []):
        print(f"  + {item['file']} (created, id={item['quiz_id']})")

    for item in result.get("updated", []):
        print(f"  ↑ {item['file']} (updated)")

    for item in result.get("skipped", []):
        print(f"  - {item['file']}: skipped ({item.get('reason', '')})")

    for item in result.get("errors", []):
        print(f"  ✗ {item['file']}: {item['error']}")

    created = len(result.get("created", []))
    updated = len(result.get("updated", []))
    skipped = len(result.get("skipped", []))
    errors = len(result.get("errors", []))

    print(f"\nCreated: {created}, Updated: {updated}, Skipped: {skipped}, Errors: {errors}")
    return 0 if errors == 0 else 1


def cmd_quiz_status(args: argparse.Namespace) -> int:
    """Show sync status for quizzes."""
    directory = Path(args.dir).resolve()

    # Load config
    config = load_course_config(directory)
    if not config:
        print(f"Error: Directory not initialized. Run 'canvas-mcp init COURSE_ID --dir {directory}' first")
        return 1

    course_id = config["course_id"]
    quiz_dir = directory / "quizzes"

    print(f"Course: {config.get('course_name', course_id)} ({course_id})")
    print(f"Quiz directory: {quiz_dir}\n")

    if not quiz_dir.exists():
        print("No local quizzes directory found")
        quiz_dir.mkdir(exist_ok=True)

    try:
        status = quiz_sync.quiz_sync_status(course_id, str(quiz_dir))
    except Exception as e:
        print(f"Error: {e}")
        return 1

    synced = status.get("synced", [])
    canvas_only = status.get("canvas_only", [])
    local_only = status.get("local_only", [])

    print(f"Synced ({len(synced)}):")
    for item in synced:
        print(f"  ✓ {item['file']}")

    if canvas_only:
        print(f"\nCanvas only ({len(canvas_only)}) - run 'pull-quizzes' to download:")
        for item in canvas_only:
            print(f"  ↓ {item['title']}")

    if local_only:
        print(f"\nLocal only ({len(local_only)}) - run 'push-quizzes' to upload:")
        for item in local_only:
            print(f"  ↑ {item['file']}")

    summary = status.get("summary", {})
    print(f"\nSummary: {summary.get('synced_count', 0)} synced, "
          f"{summary.get('canvas_only_count', 0)} canvas-only, "
          f"{summary.get('local_only_count', 0)} local-only")
    return 0


def cmd_list_quizzes(args: argparse.Namespace) -> int:
    """List quizzes in a course."""
    directory = Path(args.dir).resolve()

    # Load config
    config = load_course_config(directory)
    if not config:
        print(f"Error: Directory not initialized. Run 'canvas-mcp init COURSE_ID --dir {directory}' first")
        return 1

    course_id = config["course_id"]

    try:
        quiz_list = quizzes.list_quizzes(course_id)
    except Exception as e:
        print(f"Error: {e}")
        return 1

    print(f"Quizzes in course: {config.get('course_name', course_id)}\n")

    if not quiz_list:
        print("No quizzes found")
        return 0

    for q in quiz_list:
        status = "✓" if q.get("published") else "○"
        points = q.get("points_possible") or 0
        questions = q.get("question_count", 0)
        print(f"  {status} [{q['id']:>8}] {q['title']}")
        print(f"              {questions} questions, {points} pts")

    return 0


def cmd_pull_modules(args: argparse.Namespace) -> int:
    """Pull modules from Canvas to modules.yaml."""
    directory = Path(args.dir).resolve()

    # Load config
    config = load_course_config(directory)
    if not config:
        print(f"Error: Directory not initialized. Run 'canvas-mcp init COURSE_ID --dir {directory}' first")
        return 1

    course_id = config["course_id"]

    print(f"Pulling modules from course: {config.get('course_name', course_id)}")

    try:
        result = module_sync.pull_modules(course_id, str(directory))
    except Exception as e:
        print(f"Error: {e}")
        return 1

    print(f"  ✓ Pulled {result['modules_count']} modules ({result['items_count']} items)")
    print(f"  → Saved to {result['file']}")

    return 0


def cmd_push_modules(args: argparse.Namespace) -> int:
    """Push modules.yaml to Canvas."""
    directory = Path(args.dir).resolve()

    # Load config
    config = load_course_config(directory)
    if not config:
        print(f"Error: Directory not initialized. Run 'canvas-mcp init COURSE_ID --dir {directory}' first")
        return 1

    course_id = config["course_id"]

    print(f"Pushing modules to course: {config.get('course_name', course_id)}")

    try:
        result = module_sync.push_modules(
            course_id, str(directory),
            delete_missing=args.delete_missing
        )
    except Exception as e:
        print(f"Error: {e}")
        return 1

    if "error" in result:
        print(f"Error: {result['error']}")
        return 1

    for item in result.get("created", []):
        print(f"  + {item['name']} (created)")

    for item in result.get("updated", []):
        print(f"  ↑ {item['name']} (updated)")

    for item in result.get("deleted", []):
        print(f"  - {item['name']} (deleted)")

    for item in result.get("errors", []):
        print(f"  ✗ {item.get('name', 'unknown')}: {item['error']}")

    created = len(result.get("created", []))
    updated = len(result.get("updated", []))
    deleted = len(result.get("deleted", []))
    errors = len(result.get("errors", []))

    print(f"\nCreated: {created}, Updated: {updated}, Deleted: {deleted}, Errors: {errors}")
    return 0 if errors == 0 else 1


def cmd_pull_course(args: argparse.Namespace) -> int:
    """Pull course settings from Canvas to course.yaml."""
    directory = Path(args.dir).resolve()

    # Load config to get course_id
    config = load_course_config(directory)
    if not config:
        print(f"Error: Directory not initialized. Run 'canvas-mcp init COURSE_ID --dir {directory}' first")
        return 1

    course_id = config["course_id"]

    print(f"Pulling course settings from: {config.get('course_name', course_id)}")

    try:
        result = course_sync.pull_course(course_id, str(directory))
    except Exception as e:
        print(f"Error: {e}")
        return 1

    print(f"  ✓ Pulled {result['settings_count']} settings to {result['file']}")

    conflicts = result.get("conflicts", [])
    if conflicts:
        print(f"\n⚠ {len(conflicts)} conflicts detected (Canvas values used):")
        for c in conflicts:
            print(f"  {c['field']}:")
            print(f"    Local:  {c['local']}")
            print(f"    Canvas: {c['canvas']}")

    return 0


def cmd_push_course(args: argparse.Namespace) -> int:
    """Push course.yaml settings to Canvas."""
    directory = Path(args.dir).resolve()

    print(f"Pushing course settings from {directory}")

    try:
        # First do a dry run to show what would change
        if not args.yes:
            result = course_sync.push_course(str(directory), dry_run=True)

            if "error" in result:
                print(f"Error: {result['error']}")
                return 1

            changes = result.get("changes", [])
            if not changes:
                print("No changes to push")
                return 0

            print(f"Changes to be pushed ({len(changes)}):")
            for c in changes:
                print(f"  {c['field']}: {c['from']} → {c['to']}")

            response = input("\nProceed? [y/N] ")
            if response.lower() != 'y':
                print("Aborted")
                return 0

        # Actually push
        result = course_sync.push_course(str(directory), dry_run=False)
    except Exception as e:
        print(f"Error: {e}")
        return 1

    if "error" in result:
        print(f"Error: {result['error']}")
        return 1

    changes = result.get("changes", [])
    errors = result.get("errors", [])

    for c in changes:
        print(f"  ✓ {c['field']}: {c['from']} → {c['to']}")

    for e in errors:
        print(f"  ✗ {e}")

    print(f"\nPushed {len(changes)} changes" + (f", {len(errors)} errors" if errors else ""))
    return 0 if not errors else 1


def cmd_course_status(args: argparse.Namespace) -> int:
    """Show course settings sync status."""
    directory = Path(args.dir).resolve()

    print(f"Course settings status for {directory}\n")

    try:
        result = course_sync.course_status(str(directory))
    except Exception as e:
        print(f"Error: {e}")
        return 1

    if "error" in result:
        print(f"Error: {result['error']}")
        return 1

    synced = result.get("synced", [])
    differs = result.get("differs", [])
    canvas_only = result.get("canvas_only", [])

    if synced:
        print(f"Synced ({len(synced)}):")
        for s in synced[:10]:  # Limit display
            print(f"  ✓ {s['field']}")
        if len(synced) > 10:
            print(f"  ... and {len(synced) - 10} more")

    if differs:
        print(f"\nDiffers ({len(differs)}) - local vs Canvas:")
        for d in differs:
            print(f"  ≠ {d['field']}:")
            print(f"      local:  {d['local']}")
            print(f"      Canvas: {d['canvas']}")

    if canvas_only:
        print(f"\nCanvas only ({len(canvas_only)}):")
        for c in canvas_only[:5]:
            print(f"  ↓ {c['field']}: {c['value']}")

    summary = result.get("summary", {})
    print(f"\nSummary: {summary.get('synced_count', 0)} synced, "
          f"{summary.get('differs_count', 0)} differ, "
          f"{summary.get('canvas_only_count', 0)} canvas-only")

    return 0


def cmd_module_status(args: argparse.Namespace) -> int:
    """Show module sync status."""
    directory = Path(args.dir).resolve()

    # Load config
    config = load_course_config(directory)
    if not config:
        print(f"Error: Directory not initialized. Run 'canvas-mcp init COURSE_ID --dir {directory}' first")
        return 1

    course_id = config["course_id"]

    print(f"Course: {config.get('course_name', course_id)} ({course_id})")
    print(f"Directory: {directory}\n")

    try:
        status = module_sync.module_sync_status(course_id, str(directory))
    except Exception as e:
        print(f"Error: {e}")
        return 1

    synced = status.get("synced", [])
    canvas_only = status.get("canvas_only", [])
    local_only = status.get("local_only", [])

    print(f"Synced ({len(synced)}):")
    for item in synced:
        print(f"  ✓ {item['name']}")

    if canvas_only:
        print(f"\nCanvas only ({len(canvas_only)}) - run 'pull-modules' to download:")
        for item in canvas_only:
            print(f"  ↓ {item['name']}")

    if local_only:
        print(f"\nLocal only ({len(local_only)}) - run 'push-modules' to upload:")
        for item in local_only:
            print(f"  ↑ {item['name']}")

    summary = status.get("summary", {})
    print(f"\nSummary: {summary.get('synced_count', 0)} synced, "
          f"{summary.get('canvas_only_count', 0)} canvas-only, "
          f"{summary.get('local_only_count', 0)} local-only")
    return 0


def cmd_pull_submissions(args: argparse.Namespace) -> int:
    """Pull submissions from Canvas for an assignment."""
    directory = Path(args.dir).resolve()

    # Load config
    config = load_course_config(directory)
    if not config:
        print(f"Error: Directory not initialized. Run 'canvas-mcp init COURSE_ID --dir {directory}' first")
        return 1

    course_id = config["course_id"]

    # Create submissions subdirectory
    submissions_dir = directory / "submissions"
    submissions_dir.mkdir(exist_ok=True)

    print(f"Pulling submissions from course: {config.get('course_name', course_id)}")
    print(f"Assignment ID: {args.assignment}")
    if args.anonymize:
        print("Mode: ANONYMOUS (student identities will be hidden)")

    try:
        result = submission_sync.pull_submissions(
            course_id,
            args.assignment,
            str(submissions_dir),
            include_attachments=not args.no_attachments,
            anonymize=args.anonymize,
        )
    except Exception as e:
        print(f"Error: {e}")
        return 1

    print(f"\n  ✓ Pulled {result['pulled']} submissions")
    if result.get('attachments_downloaded', 0) > 0:
        print(f"  ✓ Downloaded {result['attachments_downloaded']} attachments")
    if result.get('errors', 0) > 0:
        print(f"  ✗ {result['errors']} errors")

    print(f"\n  → Saved to {result.get('directory', submissions_dir)}")
    print(f"  → Index: {result.get('file', 'submissions.yaml')}")

    if args.anonymize:
        print("\n  ⚠ ID mapping saved to .id_mapping.yaml (keep private!)")

    return 0 if result.get('errors', 0) == 0 else 1


def cmd_submission_status(args: argparse.Namespace) -> int:
    """Show submission status for an assignment."""
    directory = Path(args.dir).resolve()

    # Load config
    config = load_course_config(directory)
    if not config:
        print(f"Error: Directory not initialized. Run 'canvas-mcp init COURSE_ID --dir {directory}' first")
        return 1

    course_id = config["course_id"]
    submissions_dir = directory / "submissions"

    print(f"Course: {config.get('course_name', course_id)} ({course_id})")
    print(f"Assignment ID: {args.assignment}\n")

    try:
        status = submission_sync.submission_status(
            course_id,
            args.assignment,
            local_dir=str(submissions_dir) if submissions_dir.exists() else None,
        )
    except Exception as e:
        print(f"Error: {e}")
        return 1

    print(f"Assignment: {status.get('assignment_name', 'Unknown')}")
    print(f"\nSubmission Status:")
    print(f"  Total students:  {status.get('total_students', 0)}")
    print(f"  Submitted:       {status.get('submitted', 0)}")
    print(f"  Not submitted:   {status.get('not_submitted', 0)}")
    print(f"  Late:            {status.get('late', 0)}")
    print(f"  Missing:         {status.get('missing', 0)}")

    print(f"\nGrading Status:")
    print(f"  Graded:          {status.get('graded', 0)}")
    print(f"  Needs grading:   {status.get('needs_grading', 0)}")
    print(f"  Pending review:  {status.get('pending_review', 0)}")

    if status.get('local_download'):
        anon_text = " (anonymous)" if status.get('local_anonymized') else ""
        print(f"\nLocal download: {status.get('local_download')}{anon_text}")
    else:
        print(f"\nNo local download found. Run 'pull-submissions' to download.")

    return 0


def cmd_pull_rubrics(args: argparse.Namespace) -> int:
    """Pull rubrics from Canvas to local YAML files."""
    directory = Path(args.dir).resolve()

    # Load config
    config = load_course_config(directory)
    if not config:
        print(f"Error: Directory not initialized. Run 'canvas-mcp init COURSE_ID --dir {directory}' first")
        return 1

    course_id = config["course_id"]

    # Create rubrics subdirectory
    rubric_dir = directory / "rubrics"
    rubric_dir.mkdir(exist_ok=True)

    print(f"Pulling rubrics from course: {config.get('course_name', course_id)}")

    try:
        result = rubric_sync.pull_rubrics(course_id, str(rubric_dir), overwrite=args.force)
    except Exception as e:
        print(f"Error: {e}")
        return 1

    for item in result.get("pulled", []):
        print(f"  ✓ {item['file']} ({item['criteria_count']} criteria)")

    for item in result.get("skipped", []):
        print(f"  - {item['file']}: skipped ({item.get('reason', 'exists')})")

    for item in result.get("no_rubric", []):
        print(f"  · {item['name']}: no rubric")

    for item in result.get("errors", []):
        print(f"  ✗ {item.get('name', 'unknown')}: {item['error']}")

    pulled = len(result.get("pulled", []))
    skipped = len(result.get("skipped", []))
    no_rubric = len(result.get("no_rubric", []))
    errors = len(result.get("errors", []))

    print(f"\nPulled: {pulled}, Skipped: {skipped}, No rubric: {no_rubric}, Errors: {errors}")
    return 0 if errors == 0 else 1


def cmd_push_rubrics(args: argparse.Namespace) -> int:
    """Push local YAML rubric files to Canvas."""
    directory = Path(args.dir).resolve()

    # Load config
    config = load_course_config(directory)
    if not config:
        print(f"Error: Directory not initialized. Run 'canvas-mcp init COURSE_ID --dir {directory}' first")
        return 1

    course_id = config["course_id"]

    # Use rubrics subdirectory
    rubric_dir = directory / "rubrics"
    if not rubric_dir.exists():
        print(f"Error: No rubrics directory found at {rubric_dir}")
        return 1

    print(f"Pushing rubrics to course: {config.get('course_name', course_id)}")

    try:
        result = asyncio.run(rubric_sync.push_rubrics(
            course_id,
            str(rubric_dir),
            create_only=args.create_only,
        ))
    except Exception as e:
        print(f"Error: {e}")
        return 1

    for item in result.get("created", []):
        print(f"  + {item['file']} (created, {item['criteria_count']} criteria)")

    for item in result.get("updated", []):
        print(f"  ↑ {item['file']} (updated)")

    for item in result.get("skipped", []):
        print(f"  - {item['file']}: skipped ({item.get('reason', '')})")

    for item in result.get("errors", []):
        print(f"  ✗ {item['file']}: {item['error']}")

    created = len(result.get("created", []))
    updated = len(result.get("updated", []))
    skipped = len(result.get("skipped", []))
    errors = len(result.get("errors", []))

    print(f"\nCreated: {created}, Updated: {updated}, Skipped: {skipped}, Errors: {errors}")
    return 0 if errors == 0 else 1


def cmd_rubric_status(args: argparse.Namespace) -> int:
    """Show sync status for rubrics."""
    directory = Path(args.dir).resolve()

    # Load config
    config = load_course_config(directory)
    if not config:
        print(f"Error: Directory not initialized. Run 'canvas-mcp init COURSE_ID --dir {directory}' first")
        return 1

    course_id = config["course_id"]
    rubric_dir = directory / "rubrics"

    print(f"Course: {config.get('course_name', course_id)} ({course_id})")
    print(f"Rubric directory: {rubric_dir}\n")

    if not rubric_dir.exists():
        print("No local rubrics directory found")
        rubric_dir.mkdir(exist_ok=True)

    try:
        status = rubric_sync.rubric_sync_status(course_id, str(rubric_dir))
    except Exception as e:
        print(f"Error: {e}")
        return 1

    synced = status.get("synced", [])
    canvas_only = status.get("canvas_only", [])
    local_only = status.get("local_only", [])

    print(f"Synced ({len(synced)}):")
    for item in synced:
        sync_mark = "✓" if item.get("synced", True) else "≠"
        print(f"  {sync_mark} {item['file']} ({item['criteria_count']} criteria)")

    if canvas_only:
        print(f"\nCanvas only ({len(canvas_only)}) - run 'pull-rubrics' to download:")
        for item in canvas_only:
            print(f"  ↓ {item['name']} ({item['criteria_count']} criteria)")

    if local_only:
        print(f"\nLocal only ({len(local_only)}) - run 'push-rubrics' to upload:")
        for item in local_only:
            print(f"  ↑ {item['file']}")

    summary = status.get("summary", {})
    print(f"\nSummary: {summary.get('synced_count', 0)} synced, "
          f"{summary.get('canvas_only_count', 0)} canvas-only, "
          f"{summary.get('local_only_count', 0)} local-only")
    return 0


def cmd_pull_discussions(args: argparse.Namespace) -> int:
    """Pull discussions from Canvas."""
    directory = Path(args.dir).resolve()
    config = load_course_config(directory)
    if not config:
        print(f"Error: Directory not initialized. Run 'canvas-author init COURSE_ID --dir {directory}' first")
        return 1

    course_id = config["course_id"]
    course_name = config.get("course_name", course_id)

    print(f"Pulling discussions from course: {course_name}")

    try:
        results = discussion_sync.pull_discussions(
            course_id,
            str(directory),
            overwrite=args.force,
            only_announcements=False
        )

        print(f"\nPulled: {len(results['pulled'])}, Skipped: {len(results['skipped'])}, Errors: {len(results['errors'])}")

        if results['errors']:
            print("\nErrors:")
            for error in results['errors']:
                print(f"  - {error['title']}: {error['error']}")
            return 1

        return 0
    except Exception as e:
        print(f"Error pulling discussions: {e}")
        return 1


def cmd_push_discussions(args: argparse.Namespace) -> int:
    """Push discussions to Canvas."""
    directory = Path(args.dir).resolve()
    config = load_course_config(directory)
    if not config:
        print(f"Error: Directory not initialized. Run 'canvas-author init COURSE_ID --dir {directory}' first")
        return 1

    course_id = config["course_id"]
    course_name = config.get("course_name", course_id)

    print(f"Pushing discussions to course: {course_name}")

    create_missing = not args.update_only
    update_existing = not args.create_only

    try:
        results = discussion_sync.push_discussions(
            course_id,
            str(directory),
            create_missing=create_missing,
            update_existing=update_existing,
            is_announcements=False
        )

        print(f"\nCreated: {len(results['created'])}, Updated: {len(results['updated'])}, "
              f"Skipped: {len(results['skipped'])}, Errors: {len(results['errors'])}")

        if results['errors']:
            print("\nErrors:")
            for error in results['errors']:
                print(f"  - {error.get('file', 'unknown')}: {error['error']}")
            return 1

        return 0
    except Exception as e:
        print(f"Error pushing discussions: {e}")
        return 1


def cmd_pull_announcements(args: argparse.Namespace) -> int:
    """Pull announcements from Canvas."""
    directory = Path(args.dir).resolve()
    config = load_course_config(directory)
    if not config:
        print(f"Error: Directory not initialized. Run 'canvas-author init COURSE_ID --dir {directory}' first")
        return 1

    course_id = config["course_id"]
    course_name = config.get("course_name", course_id)

    print(f"Pulling announcements from course: {course_name}")

    try:
        results = announcement_sync.pull_announcements(
            course_id,
            str(directory),
            overwrite=args.force,
            limit=args.limit if hasattr(args, 'limit') else 50
        )

        print(f"\nPulled: {len(results['pulled'])}, Skipped: {len(results['skipped'])}, Errors: {len(results['errors'])}")

        if results['errors']:
            print("\nErrors:")
            for error in results['errors']:
                print(f"  - {error['title']}: {error['error']}")
            return 1

        return 0
    except Exception as e:
        print(f"Error pulling announcements: {e}")
        return 1


def cmd_push_announcements(args: argparse.Namespace) -> int:
    """Push announcements to Canvas."""
    directory = Path(args.dir).resolve()
    config = load_course_config(directory)
    if not config:
        print(f"Error: Directory not initialized. Run 'canvas-author init COURSE_ID --dir {directory}' first")
        return 1

    course_id = config["course_id"]
    course_name = config.get("course_name", course_id)

    print(f"Pushing announcements to course: {course_name}")

    create_missing = not args.update_only
    update_existing = not args.create_only

    try:
        results = announcement_sync.push_announcements(
            course_id,
            str(directory),
            create_missing=create_missing,
            update_existing=update_existing
        )

        print(f"\nCreated: {len(results['created'])}, Updated: {len(results['updated'])}, "
              f"Skipped: {len(results['skipped'])}, Errors: {len(results['errors'])}")

        if results['errors']:
            print("\nErrors:")
            for error in results['errors']:
                print(f"  - {error.get('file', 'unknown')}: {error['error']}")
            return 1

        return 0
    except Exception as e:
        print(f"Error pushing announcements: {e}")
        return 1


def cmd_delete_page(args: argparse.Namespace) -> int:
    """Delete a single page from Canvas by URL."""
    directory = Path(args.dir).resolve()
    
    config = load_course_config(directory)
    if not config:
        print(f"Error: Directory not initialized")
        return 1
    
    course_id = config["course_id"]
    page_url = args.page_url
    
    try:
        client = get_canvas_client()
        course = client.get_course(course_id)
        
        # Delete the page
        url = f"{client.base_url}/courses/{course_id}/pages/{page_url}"
        response = client.session.delete(url)
        
        if response.status_code == 200:
            print(f"✓ Deleted page: {page_url}")
            return 0
        else:
            print(f"✗ Failed to delete {page_url}: {response.status_code}")
            print(f"  Response: {response.text}")
            return 1
    except Exception as e:
        print(f"Error deleting page: {e}")
        return 1


def cmd_delete_orphaned_pages(args: argparse.Namespace) -> int:
    """Delete pages that exist on Canvas but not locally."""
    base_directory = Path(args.dir).resolve()
    
    config = load_course_config(base_directory)
    if not config:
        print(f"Error: Directory not initialized")
        return 1
    
    course_id = config["course_id"]
    
    # Get pages directory from config
    pages_subdir = config.get("pages_directory")
    if pages_subdir:
        pages_directory = (base_directory / pages_subdir).resolve()
    else:
        pages_directory = base_directory
    
    if not pages_directory.exists():
        print(f"Error: Pages directory does not exist: {pages_directory}")
        return 1
    
    try:
        client = get_canvas_client()
        course = client.get_course(course_id)
        
        # Get all Canvas pages
        canvas_pages = list_pages(course_id, client, course=course)
        
        # Get local page URLs
        local_pages = set()
        for file in pages_directory.glob("*.md"):
            page_url = file.stem
            local_pages.add(page_url)
        
        # Find orphaned pages
        orphaned = [p for p in canvas_pages if p["url"] not in local_pages]
        
        if not orphaned:
            print("No orphaned pages found on Canvas")
            return 0
        
        print(f"Found {len(orphaned)} orphaned pages on Canvas:")
        for i, page in enumerate(orphaned[:20], 1):
            published = "✓" if page.get("published") else "-"
            print(f"  {published} {page['url']} ({page['title']})")
        
        if len(orphaned) > 20:
            print(f"  ... and {len(orphaned) - 20} more")
        
        # Confirm deletion
        if not args.yes:
            response = input(f"\nDelete {len(orphaned)} orphaned pages? (yes/no): ")
            if response.lower() != "yes":
                print("Cancelled")
                return 0
        
        # Delete pages
        deleted = 0
        failed = 0
        for page in orphaned:
            page_url = page["url"]
            url = f"{client.base_url}/courses/{course_id}/pages/{page_url}"
            response = client.session.delete(url)
            
            if response.status_code == 200:
                deleted += 1
                if args.verbose:
                    print(f"✓ Deleted: {page_url}")
            else:
                failed += 1
                print(f"✗ Failed: {page_url} ({response.status_code})")
        
        print(f"\nDeleted: {deleted}, Failed: {failed}")
        return 0 if failed == 0 else 1
        
    except Exception as e:
        print(f"Error: {e}")
        return 1


def cmd_pull_assignments(args: argparse.Namespace) -> int:
    """Pull assignments from Canvas."""
    from . import assignment_sync

    directory = Path(args.dir).resolve()
    config = load_course_config(directory)
    if not config:
        print(f"Error: Directory not initialized")
        return 1

    course_id = config["course_id"]

    # Use assignments_directory from config if available
    assignments_subdir = config.get("assignments_directory", "assignments")
    assignments_directory = (directory / assignments_subdir).resolve()

    if not assignments_directory.exists():
        print(f"Creating assignments directory: {assignments_directory}")
        assignments_directory.mkdir(parents=True)

    result = assignment_sync.pull_assignments(
        course_id=course_id,
        output_dir=str(assignments_directory),
        overwrite=args.force
    )

    print(f"\nPulled: {result['pulled']}, Skipped: {result['skipped']}, Errors: {result['errors']}")
    return 0 if result['errors'] == 0 else 1


def cmd_push_assignments(args: argparse.Namespace) -> int:
    """Push assignments to Canvas."""
    from . import assignment_sync

    directory = Path(args.dir).resolve()
    config = load_course_config(directory)
    if not config:
        print(f"Error: Directory not initialized")
        return 1

    course_id = config["course_id"]

    # Use assignments_directory from config if available
    assignments_subdir = config.get("assignments_directory", "assignments")
    assignments_directory = (directory / assignments_subdir).resolve()

    if not assignments_directory.exists():
        print(f"Error: Assignments directory does not exist: {assignments_directory}")
        return 1

    # Map CLI flags to function parameters
    create_missing = not args.update_only
    update_existing = not args.create_only

    result = assignment_sync.push_assignments(
        course_id=course_id,
        input_dir=str(assignments_directory),
        create_missing=create_missing,
        update_existing=update_existing
    )

    print(f"\nCreated: {result['created']}, Updated: {result['updated']}, Skipped: {result['skipped']}, Errors: {result['errors']}")
    return 0 if result['errors'] == 0 else 1


def cmd_assignment_status(args: argparse.Namespace) -> int:
    """Show assignment sync status."""
    from . import assignment_sync

    directory = Path(args.dir).resolve()
    config = load_course_config(directory)
    if not config:
        print(f"Error: Directory not initialized")
        return 1

    course_id = config["course_id"]

    # Use assignments_directory from config if available
    assignments_subdir = config.get("assignments_directory", "assignments")
    assignments_directory = (directory / assignments_subdir).resolve()

    if not assignments_directory.exists():
        print(f"Error: Assignments directory does not exist: {assignments_directory}")
        return 1

    result = assignment_sync.assignment_sync_status(
        course_id=course_id,
        local_dir=str(assignments_directory)
    )

    print(f"\nTotal: {result['total']}")
    print(f"  Up to date: {result['up_to_date']}")
    print(f"  Local changes: {result['local_changes']}")
    print(f"  Canvas changes: {result['canvas_changes']}")
    print(f"  Only local: {result['only_local']}")
    print(f"  Only canvas: {result['only_canvas']}")

    return 0


def main() -> int:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Canvas MCP - Sync Canvas wiki pages with local markdown files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # init command
    init_parser = subparsers.add_parser("init", help="Initialize directory for a course")
    init_parser.add_argument("course_id", help="Canvas course ID")
    init_parser.add_argument("--dir", "-d", default=".", help="Directory to initialize (default: current)")
    init_parser.add_argument("--force", "-f", action="store_true", help="Reinitialize even if exists")

    # pull command
    pull_parser = subparsers.add_parser("pull", help="Pull pages from Canvas")
    pull_parser.add_argument("--dir", "-d", default=".", help="Directory to pull into (default: current)")
    pull_parser.add_argument("--force", "-f", action="store_true", help="Overwrite existing files")
    pull_parser.add_argument("--all", "-a", action="store_true", help="Pull all pages, even unchanged")

    # push command
    push_parser = subparsers.add_parser("push", help="Push pages to Canvas")
    push_parser.add_argument("--dir", "-d", default=".", help="Directory to push from (default: current)")
    push_parser.add_argument("--create-only", action="store_true", help="Only create new pages, don't update")
    push_parser.add_argument("--update-only", action="store_true", help="Only update existing pages, don't create")
    push_parser.add_argument("--no-update-meta", action="store_true", help="Don't update local frontmatter after push")
    push_parser.add_argument("--force-rename", action="store_true", 
                            help="Allow pushing when filename differs from Canvas-generated URL (will auto-rename files)")

    # create-page command
    create_page_parser = subparsers.add_parser("create-page", help="Create a new page on Canvas and local file")
    create_page_parser.add_argument("title", help="Page title (Canvas will generate URL from this)")
    create_page_parser.add_argument("--dir", "-d", default=".", help="Directory for the local file (default: current)")
    create_page_parser.add_argument("--body", "-b", default="", help="Initial page body content (markdown)")
    create_page_parser.add_argument("--draft", action="store_true", help="Create as unpublished draft")
    create_page_parser.add_argument("--force", "-f", action="store_true", help="Overwrite existing local file")

    # status command
    status_parser = subparsers.add_parser("status", help="Show sync status")
    status_parser.add_argument("--dir", "-d", default=".", help="Directory to check (default: current)")

    # list-courses command
    list_parser = subparsers.add_parser("list-courses", help="List available courses")
    list_parser.add_argument("--state", default="active", choices=["active", "all"], help="Course state filter")

    # server command (for MCP)
    server_parser = subparsers.add_parser("server", help="Run MCP server")

    # delete-page command
    delete_page_parser = subparsers.add_parser("delete-page", help="Delete a single page from Canvas")
    delete_page_parser.add_argument("page_url", help="URL of the page to delete")
    delete_page_parser.add_argument("--dir", "-d", default=".", help="Course directory (default: current)")

    # delete-orphaned-pages command
    delete_orphaned_parser = subparsers.add_parser("delete-orphaned-pages",
                                                    help="Delete pages on Canvas that don't exist locally")
    delete_orphaned_parser.add_argument("--dir", "-d", default=".", help="Course directory (default: current)")
    delete_orphaned_parser.add_argument("--yes", "-y", action="store_true", help="Skip confirmation prompt")
    delete_orphaned_parser.add_argument("--verbose", "-v", action="store_true", help="Show each deletion")

    # pull-assignments command
    pull_assignments_parser = subparsers.add_parser("pull-assignments", help="Pull assignments from Canvas")
    pull_assignments_parser.add_argument("--dir", "-d", default=".", help="Course directory (default: current)")
    pull_assignments_parser.add_argument("--force", "-f", action="store_true", help="Overwrite existing files")

    # push-assignments command
    push_assignments_parser = subparsers.add_parser("push-assignments", help="Push assignments to Canvas")
    push_assignments_parser.add_argument("--dir", "-d", default=".", help="Course directory (default: current)")
    push_assignments_parser.add_argument("--create-only", action="store_true", help="Only create new assignments")
    push_assignments_parser.add_argument("--update-only", action="store_true", help="Only update existing assignments")

    # assignment-status command
    assignment_status_parser = subparsers.add_parser("assignment-status", help="Show assignment sync status")
    assignment_status_parser.add_argument("--dir", "-d", default=".", help="Course directory (default: current)")

    # pull-quizzes command
    pull_quizzes_parser = subparsers.add_parser("pull-quizzes", help="Pull quizzes from Canvas")
    pull_quizzes_parser.add_argument("--dir", "-d", default=".", help="Course directory (default: current)")
    pull_quizzes_parser.add_argument("--force", "-f", action="store_true", help="Overwrite existing files")

    # push-quizzes command
    push_quizzes_parser = subparsers.add_parser("push-quizzes", help="Push quizzes to Canvas")
    push_quizzes_parser.add_argument("--dir", "-d", default=".", help="Course directory (default: current)")
    push_quizzes_parser.add_argument("--create-only", action="store_true", help="Only create new quizzes")
    push_quizzes_parser.add_argument("--update-only", action="store_true", help="Only update existing quizzes")

    # quiz-status command
    quiz_status_parser = subparsers.add_parser("quiz-status", help="Show quiz sync status")
    quiz_status_parser.add_argument("--dir", "-d", default=".", help="Course directory (default: current)")

    # list-quizzes command
    list_quizzes_parser = subparsers.add_parser("list-quizzes", help="List quizzes in course")
    list_quizzes_parser.add_argument("--dir", "-d", default=".", help="Course directory (default: current)")

    # pull-modules command
    pull_modules_parser = subparsers.add_parser("pull-modules", help="Pull modules from Canvas")
    pull_modules_parser.add_argument("--dir", "-d", default=".", help="Course directory (default: current)")

    # push-modules command
    push_modules_parser = subparsers.add_parser("push-modules", help="Push modules to Canvas")
    push_modules_parser.add_argument("--dir", "-d", default=".", help="Course directory (default: current)")
    push_modules_parser.add_argument("--delete-missing", action="store_true", help="Delete Canvas modules not in local file")

    # module-status command
    module_status_parser = subparsers.add_parser("module-status", help="Show module sync status")
    module_status_parser.add_argument("--dir", "-d", default=".", help="Course directory (default: current)")

    # pull-course command
    pull_course_parser = subparsers.add_parser("pull-course", help="Pull course settings from Canvas")
    pull_course_parser.add_argument("--dir", "-d", default=".", help="Course directory (default: current)")

    # push-course command
    push_course_parser = subparsers.add_parser("push-course", help="Push course settings to Canvas")
    push_course_parser.add_argument("--dir", "-d", default=".", help="Course directory (default: current)")
    push_course_parser.add_argument("--yes", "-y", action="store_true", help="Skip confirmation prompt")

    # course-status command
    course_status_parser = subparsers.add_parser("course-status", help="Show course settings sync status")
    course_status_parser.add_argument("--dir", "-d", default=".", help="Course directory (default: current)")

    # pull-rubrics command
    pull_rubrics_parser = subparsers.add_parser("pull-rubrics", help="Pull rubrics from Canvas")
    pull_rubrics_parser.add_argument("--dir", "-d", default=".", help="Course directory (default: current)")
    pull_rubrics_parser.add_argument("--force", "-f", action="store_true", help="Overwrite existing files")

    # push-rubrics command
    push_rubrics_parser = subparsers.add_parser("push-rubrics", help="Push rubrics to Canvas")
    push_rubrics_parser.add_argument("--dir", "-d", default=".", help="Course directory (default: current)")
    push_rubrics_parser.add_argument("--create-only", action="store_true", help="Only create new rubrics, don't update")

    # rubric-status command
    rubric_status_parser = subparsers.add_parser("rubric-status", help="Show rubric sync status")
    rubric_status_parser.add_argument("--dir", "-d", default=".", help="Course directory (default: current)")

    # pull-submissions command
    pull_submissions_parser = subparsers.add_parser("pull-submissions", help="Pull submissions from Canvas")
    pull_submissions_parser.add_argument("--dir", "-d", default=".", help="Course directory (default: current)")
    pull_submissions_parser.add_argument("--assignment", "-a", required=True, help="Assignment ID")
    pull_submissions_parser.add_argument("--no-attachments", action="store_true", help="Don't download attachment files")
    pull_submissions_parser.add_argument("--anonymize", action="store_true", help="Anonymize student identities for blind grading")

    # submission-status command
    submission_status_parser = subparsers.add_parser("submission-status", help="Show submission status for an assignment")
    submission_status_parser.add_argument("--dir", "-d", default=".", help="Course directory (default: current)")
    submission_status_parser.add_argument("--assignment", "-a", required=True, help="Assignment ID")

    # pull-discussions command
    pull_discussions_parser = subparsers.add_parser("pull-discussions", help="Pull discussions from Canvas")
    pull_discussions_parser.add_argument("--dir", "-d", default=".", help="Course directory (default: current)")
    pull_discussions_parser.add_argument("--force", "-f", action="store_true", help="Overwrite existing files")

    # push-discussions command
    push_discussions_parser = subparsers.add_parser("push-discussions", help="Push discussions to Canvas")
    push_discussions_parser.add_argument("--dir", "-d", default=".", help="Course directory (default: current)")
    push_discussions_parser.add_argument("--create-only", action="store_true", help="Only create new discussions")
    push_discussions_parser.add_argument("--update-only", action="store_true", help="Only update existing discussions")

    # pull-announcements command
    pull_announcements_parser = subparsers.add_parser("pull-announcements", help="Pull announcements from Canvas")
    pull_announcements_parser.add_argument("--dir", "-d", default=".", help="Course directory (default: current)")
    pull_announcements_parser.add_argument("--force", "-f", action="store_true", help="Overwrite existing files")
    pull_announcements_parser.add_argument("--limit", "-l", type=int, default=50, help="Maximum number to pull (default: 50)")

    # push-announcements command
    push_announcements_parser = subparsers.add_parser("push-announcements", help="Push announcements to Canvas")
    push_announcements_parser.add_argument("--dir", "-d", default=".", help="Course directory (default: current)")
    push_announcements_parser.add_argument("--create-only", action="store_true", help="Only create new announcements")
    push_announcements_parser.add_argument("--update-only", action="store_true", help="Only update existing announcements")

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return 0

    if args.command == "init":
        return cmd_init(args)
    elif args.command == "pull":
        return cmd_pull(args)
    elif args.command == "push":
        return cmd_push(args)
    elif args.command == "create-page":
        return cmd_create_page(args)
    elif args.command == "status":
        return cmd_status(args)
    elif args.command == "list-courses":
        return cmd_list_courses(args)
    elif args.command == "server":
        from .server import main as server_main
        server_main()
        return 0
    elif args.command == "delete-page":
        return cmd_delete_page(args)
    elif args.command == "delete-orphaned-pages":
        return cmd_delete_orphaned_pages(args)
    elif args.command == "pull-assignments":
        return cmd_pull_assignments(args)
    elif args.command == "push-assignments":
        return cmd_push_assignments(args)
    elif args.command == "assignment-status":
        return cmd_assignment_status(args)
    elif args.command == "pull-quizzes":
        return cmd_pull_quizzes(args)
    elif args.command == "push-quizzes":
        return cmd_push_quizzes(args)
    elif args.command == "quiz-status":
        return cmd_quiz_status(args)
    elif args.command == "list-quizzes":
        return cmd_list_quizzes(args)
    elif args.command == "pull-modules":
        return cmd_pull_modules(args)
    elif args.command == "push-modules":
        return cmd_push_modules(args)
    elif args.command == "module-status":
        return cmd_module_status(args)
    elif args.command == "pull-course":
        return cmd_pull_course(args)
    elif args.command == "push-course":
        return cmd_push_course(args)
    elif args.command == "course-status":
        return cmd_course_status(args)
    elif args.command == "pull-rubrics":
        return cmd_pull_rubrics(args)
    elif args.command == "push-rubrics":
        return cmd_push_rubrics(args)
    elif args.command == "rubric-status":
        return cmd_rubric_status(args)
    elif args.command == "pull-submissions":
        return cmd_pull_submissions(args)
    elif args.command == "submission-status":
        return cmd_submission_status(args)
    elif args.command == "pull-discussions":
        return cmd_pull_discussions(args)
    elif args.command == "push-discussions":
        return cmd_push_discussions(args)
    elif args.command == "pull-announcements":
        return cmd_pull_announcements(args)
    elif args.command == "push-announcements":
        return cmd_push_announcements(args)

    return 0


if __name__ == "__main__":
    sys.exit(main())


