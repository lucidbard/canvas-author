"""
Canvas MCP - Canvas LMS MCP server for managing wiki pages, assignments, discussions, announcements, and rubrics.

Uses pandoc for markdown <-> HTML conversion and supports two-way sync with local files.
"""

__version__ = "0.1.2"

from canvas_common import get_canvas_client, CanvasClient
from .pandoc import markdown_to_html, html_to_markdown
from canvas_common import (
    CanvasMCPError,
    ConfigurationError,
    AuthenticationError,
    ResourceNotFoundError,
    APIError,
    RateLimitError,
    ValidationError,
    PandocError,
    SyncError,
    FileOperationError,
)
from .styling import (
    inline_styles,
    inline_styles_from_file,
    add_callout_box,
    add_styled_table,
    get_preset_names,
    get_preset_css,
)
from .quiz_format import (
    parse_quiz_markdown,
    generate_quiz_markdown,
    Question,
    Answer,
)
from .quiz_sync import (
    pull_quizzes,
    push_quizzes,
    quiz_sync_status,
)
from .assignment_groups import (
    list_assignment_groups,
    get_assignment_group,
)
from .discussion_sync import (
    pull_discussions,
    push_discussions,
)
from .announcement_sync import (
    pull_announcements,
    push_announcements,
)
from .submission_sync import (
    pull_submissions,
    submission_status,
    get_all_submissions_hierarchical,
)
from .workflow import (
    WorkflowManager,
    WorktreeReviewSession,
    ItemReview,
    ReviewPass,
    create_agent_worktree,
)
from .tool_access import (
    get_agent_context,
    get_allowed_tools,
    require_agent_role,
    require_scope,
    check_tool_access,
    ToolAccessError,
)

__all__ = [
    # Client
    "get_canvas_client",
    "CanvasClient",
    # Pandoc
    "markdown_to_html",
    "html_to_markdown",
    # Styling
    "inline_styles",
    "inline_styles_from_file",
    "add_callout_box",
    "add_styled_table",
    "get_preset_names",
    "get_preset_css",
    # Exceptions
    "CanvasMCPError",
    "ConfigurationError",
    "AuthenticationError",
    "ResourceNotFoundError",
    "APIError",
    "RateLimitError",
    "ValidationError",
    "PandocError",
    "SyncError",
    "FileOperationError",
    # Quiz
    "parse_quiz_markdown",
    "generate_quiz_markdown",
    "Question",
    "Answer",
    "pull_quizzes",
    "push_quizzes",
    "quiz_sync_status",
    # Assignment Groups
    "list_assignment_groups",
    "get_assignment_group",
    # Discussion Sync
    "pull_discussions",
    "push_discussions",
    # Announcement Sync
    "pull_announcements",
    "push_announcements",
    # Submission Sync
    "pull_submissions",
    "submission_status",
    "get_all_submissions_hierarchical",
    # Workflow
    "WorkflowManager",
    "WorktreeReviewSession",
    "ItemReview",
    "ReviewPass",
    "create_agent_worktree",
    # Tool Access Control
    "get_agent_context",
    "get_allowed_tools",
    "require_agent_role",
    "require_scope",
    "check_tool_access",
    "ToolAccessError",
]
