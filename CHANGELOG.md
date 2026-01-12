# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.2] - 2026-01-12

### Added

#### Discussion Management
- `create_discussion()` - Create discussion topics with optional graded assignments
- `update_discussion()` - Update existing discussion topics
- `delete_discussion()` - Delete discussion topics
- **Checkpointed Discussion Support** - Separate grading for initial posts vs peer replies
  - `reply_to_topic` checkpoint - Initial post with dedicated points and due date
  - `reply_to_entry` checkpoint - Peer replies with separate points and due date
  - Full bidirectional sync preserves checkpoint configuration

#### Discussion Sync Module (`discussion_sync.py`)
- `pull_discussions()` - Download discussions to YAML markdown files
- `push_discussions()` - Upload local YAML files to Canvas
- Local editing of discussions in markdown/YAML format
- Preserves all discussion metadata: checkpoints, due dates, point allocations
- Support for `require_initial_post` and `reply_to_entry_required_count`

#### Announcement Management (`announcement_sync.py`)
- `pull_announcements()` - Download announcements to markdown files (with date prefixes)
- `push_announcements()` - Upload local announcements to Canvas
- `create_announcement_from_template()` - Create from templates with variable substitution
- Scheduled announcements via `delayed_post_at` field
- Date-prefixed filenames for chronological organization (e.g., `2026-01-12-welcome.announcement.md`)

#### CLI Commands
- `canvas-author pull-discussions` - Pull discussions from Canvas
- `canvas-author push-discussions` - Push discussions to Canvas
- `canvas-author pull-announcements` - Pull announcements from Canvas
- `canvas-author push-announcements` - Push announcements to Canvas
- All commands support `--force`, `--create-only`, `--update-only` flags

#### MCP Server Tools
- `create_discussion()` - Create discussions or announcements programmatically
- `update_discussion()` - Update existing discussions
- `delete_discussion()` - Delete discussions
- `pull_discussions()` - Sync discussions to local files
- `push_discussions()` - Sync discussions to Canvas
- `pull_announcements()` - Sync announcements to local files
- `push_announcements()` - Sync announcements to Canvas

### Changed
- Updated package description to include announcements
- Package exports now include `pull_discussions`, `push_discussions`, `pull_announcements`, `push_announcements`

### Fixed
- Checkpoint data now properly retrieved from discussion topic's assignment dict
- Date conversion for checkpoint due dates uses proper timezone handling

## [0.1.1] - 2025-01-10

### Added
- Documentation for discussion checkpoints and announcements
- Assignment groups Phase 1: read operations and pull support
- Datetime conversion utilities for Canvas API
- Improved course listing and auth error handling

### Fixed
- Event loop conflict in push_rubrics function

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

[Unreleased]: https://github.com/lucidbard/canvas-author/compare/v0.1.2...HEAD
[0.1.2]: https://github.com/lucidbard/canvas-author/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/lucidbard/canvas-author/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/lucidbard/canvas-author/releases/tag/v0.1.0
