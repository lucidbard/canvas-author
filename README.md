# Canvas MCP

A Canvas LMS MCP server and CLI for managing wiki pages, assignments, discussions, and rubrics with markdown support via pandoc.

## Features

- **Wiki Pages**: Create, read, update, delete Canvas wiki pages using markdown
- **Two-way Sync**: Pull pages from Canvas to local files, push local changes to Canvas
- **CSS Styling**: Inline CSS styling for Canvas pages (Canvas strips `<style>` tags)
- **Assignments & Discussions**: Access assignment details, submissions, and discussion posts
- **Rubrics**: Get and update rubrics for assignments
- **MCP Server**: Expose all functionality as MCP tools for Claude Code, Codex, VS Code
- **CLI**: Non-agentic command-line interface for shell scripts and CI/CD

## Installation

```bash
# Clone and install
git clone https://github.com/yourusername/canvas-author.git
cd canvas-author
pip install -e .

# Install pandoc (required for markdown conversion)
# Ubuntu/Debian:
sudo apt install pandoc
# macOS:
brew install pandoc
```

## Configuration

Set environment variables or create a `.env` file:

```bash
CANVAS_API_TOKEN=your_canvas_api_token
CANVAS_DOMAIN=canvas.instructure.com  # or your institution's domain
```

## CLI Usage

### Initialize a course directory

```bash
# List your courses to find the ID
canvas-mcp list-courses

# Initialize a directory for a course
canvas-mcp init 12345 --dir courses/my-course
```

This creates a `.canvas.json` file with the course configuration.

### Pull pages from Canvas

```bash
# Pull all wiki pages as markdown files
canvas-mcp pull --dir courses/my-course

# Force overwrite existing files
canvas-mcp pull --dir courses/my-course --force
```

### Push pages to Canvas

```bash
# Push all markdown files to Canvas
canvas-mcp push --dir courses/my-course

# Only create new pages, don't update existing
canvas-mcp push --dir courses/my-course --create-only

# Only update existing pages, don't create new
canvas-mcp push --dir courses/my-course --update-only
```

### Check sync status

```bash
canvas-mcp status --dir courses/my-course
```

## Directory Structure

```
courses/
├── course-12345/
│   ├── .canvas.json          # Course config
│   ├── syllabus.md           # Wiki pages as markdown
│   ├── week-1-notes.md
│   └── resources.md
└── course-67890/
    ├── .canvas.json
    └── welcome.md
```

## Markdown Frontmatter

Each markdown file includes YAML frontmatter with page metadata:

```markdown
---
title: Course Syllabus
page_id: syllabus
url: syllabus
published: true
updated_at: 2024-01-15T10:30:00Z
---

# Course Syllabus

Your content here...
```

## GitHub Actions

### Push on commit

Add `.github/workflows/sync-to-canvas.yml` to automatically push changes when markdown files are committed:

```yaml
name: Sync to Canvas
on:
  push:
    branches: [main]
    paths: ['courses/**/*.md']

jobs:
  sync:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: sudo apt-get install -y pandoc
      - run: pip install canvas-mcp
      - run: |
          for dir in courses/*/; do
            canvas-mcp push --dir "$dir"
          done
        env:
          CANVAS_API_TOKEN: ${{ secrets.CANVAS_API_TOKEN }}
          CANVAS_DOMAIN: ${{ secrets.CANVAS_DOMAIN }}
```

### Scheduled pull

Pull from Canvas daily to capture changes made in the web UI:

```yaml
name: Pull from Canvas
on:
  schedule:
    - cron: '0 6 * * *'

jobs:
  pull:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
      - run: sudo apt-get install -y pandoc
      - run: pip install canvas-mcp
      - run: |
          for dir in courses/*/; do
            canvas-mcp pull --dir "$dir" --force
          done
        env:
          CANVAS_API_TOKEN: ${{ secrets.CANVAS_API_TOKEN }}
          CANVAS_DOMAIN: ${{ secrets.CANVAS_DOMAIN }}
      - uses: peter-evans/create-pull-request@v6
        with:
          commit-message: "Sync from Canvas"
          title: "📚 Canvas Wiki Sync"
          branch: canvas-sync
```

## MCP Server

Run the MCP server for use with Claude Code or other MCP clients:

```bash
canvas-mcp server
```

Or add to your MCP configuration:

```json
{
  "mcpServers": {
    "canvas": {
      "command": "canvas-mcp",
      "args": ["server"],
      "env": {
        "CANVAS_API_TOKEN": "your_token",
        "CANVAS_DOMAIN": "your_domain"
      }
    }
  }
}
```

### Available MCP Tools

**Wiki Pages:**
- `list_pages(course_id)` - List wiki pages
- `get_page(course_id, page_url)` - Get page content as markdown
- `create_page(course_id, title, body)` - Create from markdown
- `update_page(course_id, page_url, body)` - Update from markdown
- `delete_page(course_id, page_url)` - Delete a page

**Sync:**
- `pull_pages(course_id, output_dir)` - Download all pages
- `push_pages(course_id, input_dir)` - Upload all pages
- `sync_status(course_id, local_dir)` - Check sync status

**Courses & Assignments:**
- `list_courses()` - List your courses
- `list_assignments(course_id)` - List assignments
- `get_assignment(course_id, assignment_id)` - Get assignment details
- `list_submissions(course_id, assignment_id)` - List submissions

**Discussions:**
- `list_discussions(course_id)` - List discussion topics
- `get_discussion_posts(course_id, discussion_id)` - Get posts as markdown

**Rubrics:**
- `get_rubric(course_id, assignment_id)` - Get rubric
- `update_rubric(course_id, assignment_id, rubric_data)` - Update rubric

## Shell Script

For syncing multiple courses:

```bash
./scripts/sync-all.sh status  # Check all courses
./scripts/sync-all.sh pull    # Pull all courses
./scripts/sync-all.sh push    # Push all courses
```

## CSS Styling for Canvas

Canvas LMS strips `<style>` tags and external stylesheets from wiki pages. This library uses [premailer](https://github.com/peterbe/premailer) to inline CSS directly on HTML elements (like email HTML).

### Using Style Presets

Apply pre-defined styles when converting markdown:

```python
from canvas_mcp import markdown_to_html

# Use default Canvas-friendly styling
html = markdown_to_html(content, apply_styles=True)

# Use a specific preset
html = markdown_to_html(content, apply_styles=True, style_preset="academic")
```

Available presets:
- `default` - Clean, readable styling matching Canvas aesthetic
- `minimal` - Light touch, mostly typography
- `academic` - Formal styling for course content
- `colorful` - More vibrant colors and backgrounds
- `dark` - Dark theme (note: Canvas has white background)

### Custom CSS

Add your own CSS rules:

```python
from canvas_mcp import markdown_to_html, inline_styles

# Custom CSS with markdown conversion
custom_css = """
    h1 { color: navy; border-bottom: 2px solid gold; }
    .important { background-color: #fff3cd; padding: 1em; }
"""
html = markdown_to_html(content, apply_styles=True, custom_css=custom_css)

# Or apply to existing HTML
html = inline_styles(existing_html, css=custom_css, preset="default")
```

### Helper Functions

Create styled elements programmatically:

```python
from canvas_mcp import add_callout_box, add_styled_table

# Callout boxes (info, warning, success, danger, note)
callout = add_callout_box(
    "Don't forget to submit by Friday!",
    style="warning",
    title="Deadline Reminder"
)

# Styled tables
table = add_styled_table(
    headers=["Week", "Topic", "Due Date"],
    rows=[
        ["1", "Introduction", "Jan 15"],
        ["2", "Fundamentals", "Jan 22"],
    ],
    style="striped"  # default, striped, or bordered
)
```

### Using a CSS File

Load styles from an external CSS file:

```python
from canvas_mcp import inline_styles_from_file

html = inline_styles_from_file(
    existing_html,
    css_file_path="styles/course-theme.css"
)
```

### Frontmatter Styling

Specify styles in your markdown frontmatter (planned feature):

```markdown
---
title: Week 1 Notes
style_preset: academic
custom_css: |
  .code-example { background: #f0f0f0; }
---

# Week 1: Introduction
```

## Python API

Use canvas-mcp as a library:

```python
from canvas_mcp import (
    get_canvas_client,
    markdown_to_html,
    html_to_markdown,
    inline_styles,
)
from canvas_mcp.pages import list_pages, get_page, create_page
from canvas_mcp.assignments import list_assignments
from canvas_mcp.discussions import get_discussion_posts

# Get a Canvas client
client = get_canvas_client()

# List pages in a course
pages = list_pages("12345", client=client)

# Convert markdown to styled HTML
html = markdown_to_html("# Hello\n\nWorld", apply_styles=True)

# Create a page
result = create_page(
    course_id="12345",
    title="New Page",
    body="# Welcome\n\nThis is a new page.",
    published=True
)
```

## Troubleshooting

### Pandoc not found

Install pandoc for your system:
```bash
# Ubuntu/Debian
sudo apt install pandoc

# macOS
brew install pandoc

# Windows
choco install pandoc
```

### Authentication errors

Verify your Canvas API token:
1. Go to your Canvas profile settings
2. Generate a new access token
3. Set `CANVAS_API_TOKEN` in your environment

### Rate limiting

Canvas has API rate limits. If you hit them:
- Add delays between operations
- Use batch operations when possible
- Check Canvas API documentation for current limits

## License

MIT

