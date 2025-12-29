# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2024-12-28

### Added

#### Core Features
- Canvas API client with environment-based configuration
- Wiki page CRUD operations (list, get, create, update, delete)
- Two-way sync between Canvas and local markdown files
- Markdown/HTML conversion via pandoc
- YAML frontmatter support for page metadata

#### CSS Styling
- Inline CSS styling using premailer (Canvas strips `<style>` tags)
- Pre-defined style presets: default, minimal, academic, colorful, dark
- Custom CSS support via strings or files
- Callout boxes and styled table helpers

#### MCP Server
- FastMCP server with 23 tools for Canvas operations
- Wiki pages: list, get, create, update, delete
- Sync: pull_pages, push_pages, sync_status
- Courses & Assignments: list_courses, list_assignments, get_assignment, list_submissions
- Discussions: list_discussions, get_discussion_posts, get_posts_by_user
- Rubrics: get_rubric, update_rubric
- Utilities: check_pandoc

#### CLI
- `canvas-mcp init` - Initialize course directory
- `canvas-mcp pull` - Download pages from Canvas
- `canvas-mcp push` - Upload pages to Canvas
- `canvas-mcp status` - Show sync status
- `canvas-mcp list-courses` - List available courses
- `canvas-mcp server` - Run MCP server

#### Assignment & Discussion Support
- List and get assignment details
- List and filter submissions
- List discussion topics
- Get discussion posts with nested replies
- Posts organized by user

#### Rubric Support
- Get rubric data with criteria and ratings
- Update rubrics via Canvas API
- Sync rubric IDs between local and Canvas

#### Developer Experience
- Custom exception hierarchy for specific error handling
- Comprehensive test suite (61 unit tests)
- GitHub Actions workflow examples
- Shell script for batch operations

### Dependencies
- canvasapi >= 3.0.0
- mcp >= 1.0.0
- python-dotenv >= 1.0.0
- PyYAML >= 6.0
- premailer >= 3.10.0

[Unreleased]: https://github.com/yourusername/canvas-mcp/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/yourusername/canvas-mcp/releases/tag/v0.1.0
