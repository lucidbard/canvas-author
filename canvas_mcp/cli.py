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
import json
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional

from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from .client import get_canvas_client
from .pages import list_pages, get_page, create_page, update_page
from .pandoc import is_pandoc_available
from .assignments import list_courses
from .frontmatter import parse_frontmatter, generate_frontmatter
from . import quiz_sync, quizzes

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
    directory = Path(args.dir).resolve()

    # Load config
    config = load_course_config(directory)
    if not config:
        print(f"Error: Directory not initialized. Run 'canvas-mcp init COURSE_ID --dir {directory}' first")
        return 1

    course_id = config["course_id"]

    # Check pandoc
    if not is_pandoc_available():
        print("Warning: pandoc not installed. HTML will not be converted to markdown.")
        print("Install with: apt install pandoc (Linux) or brew install pandoc (macOS)")

    try:
        client = get_canvas_client()
        pages = list_pages(course_id, client)
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
            page = get_page(course_id, url, as_markdown=True, client=client)

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

            content = generate_frontmatter(metadata) + page["body"]

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
    directory = Path(args.dir).resolve()

    # Load config
    config = load_course_config(directory)
    if not config:
        print(f"Error: Directory not initialized. Run 'canvas-mcp init COURSE_ID --dir {directory}' first")
        return 1

    course_id = config["course_id"]

    # Check pandoc
    if not is_pandoc_available():
        print("Error: pandoc is required for push. Install with: apt install pandoc")
        return 1

    # Get existing Canvas pages
    try:
        client = get_canvas_client()
        canvas_pages = {p["url"]: p for p in list_pages(course_id, client)}
    except Exception as e:
        print(f"Error fetching Canvas pages: {e}")
        return 1

    # Find local markdown files
    md_files = list(directory.glob("*.md"))
    if not md_files:
        print("No markdown files found in directory")
        return 0

    print(f"Found {len(md_files)} markdown files")

    created = 0
    updated = 0
    skipped = 0
    errors = 0

    for file_path in sorted(md_files):
        try:
            content = file_path.read_text(encoding="utf-8")
            metadata, body = parse_frontmatter(content)

            if not body.strip():
                print(f"  - {file_path.name}: empty, skipping")
                skipped += 1
                continue

            # Determine page URL and title
            url = metadata.get("url") or file_path.stem
            title = metadata.get("title") or file_path.stem.replace("-", " ").title()
            published = metadata.get("published", True)
            if isinstance(published, str):
                published = published.lower() == "true"

            if url in canvas_pages:
                # Update existing page
                if not args.create_only:
                    update_page(
                        course_id=course_id,
                        page_url=url,
                        title=title,
                        body=body,
                        from_markdown=True,
                        published=published,
                        client=client,
                    )
                    print(f"  ↑ {file_path.name} (updated)")
                    updated += 1

                    # Update local frontmatter with latest info
                    if not args.no_update_meta:
                        page = get_page(course_id, url, as_markdown=False, client=client)
                        metadata["updated_at"] = page.get("updated_at", "")
                        new_content = generate_frontmatter(metadata) + body
                        file_path.write_text(new_content, encoding="utf-8")
                else:
                    skipped += 1
            else:
                # Create new page
                if not args.update_only:
                    result = create_page(
                        course_id=course_id,
                        title=title,
                        body=body,
                        from_markdown=True,
                        published=published,
                        client=client,
                    )
                    print(f"  + {file_path.name} (created)")
                    created += 1

                    # Update local frontmatter with page_id
                    metadata["page_id"] = result.get("url", url)
                    metadata["url"] = result.get("url", url)
                    metadata["updated_at"] = result.get("updated_at", "")
                    new_content = generate_frontmatter(metadata) + body
                    file_path.write_text(new_content, encoding="utf-8")
                else:
                    print(f"  - {file_path.name}: not on Canvas, skipping (--update-only)")
                    skipped += 1

        except Exception as e:
            print(f"  ✗ {file_path.name}: {e}")
            errors += 1

    print(f"\nCreated: {created}, Updated: {updated}, Skipped: {skipped}, Errors: {errors}")
    return 0 if errors == 0 else 1


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

    # status command
    status_parser = subparsers.add_parser("status", help="Show sync status")
    status_parser.add_argument("--dir", "-d", default=".", help="Directory to check (default: current)")

    # list-courses command
    list_parser = subparsers.add_parser("list-courses", help="List available courses")
    list_parser.add_argument("--state", default="active", choices=["active", "all"], help="Course state filter")

    # server command (for MCP)
    server_parser = subparsers.add_parser("server", help="Run MCP server")

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
    elif args.command == "status":
        return cmd_status(args)
    elif args.command == "list-courses":
        return cmd_list_courses(args)
    elif args.command == "server":
        from .server import main as server_main
        server_main()
        return 0
    elif args.command == "pull-quizzes":
        return cmd_pull_quizzes(args)
    elif args.command == "push-quizzes":
        return cmd_push_quizzes(args)
    elif args.command == "quiz-status":
        return cmd_quiz_status(args)
    elif args.command == "list-quizzes":
        return cmd_list_quizzes(args)

    return 0


if __name__ == "__main__":
    sys.exit(main())
