"""
Tool access control for role-based agent restrictions.

Provides decorators and utilities to restrict MCP tool access based on agent role.
"""

import os
import json
import logging
from functools import wraps
from typing import Optional, List, Callable, Any
from pathlib import Path

logger = logging.getLogger("canvas_author.tool_access")


class ToolAccessError(Exception):
    """Raised when agent tries to use a tool they don't have access to."""
    pass


def get_agent_context() -> Optional[dict]:
    """
    Get current agent context from environment or execution context.
    
    Returns:
        Dict with agent_id, agent_role, scope, etc., or None if not in agent context.
    """
    # Check environment variable set by VS Code/Claude agent
    agent_context_json = os.environ.get("CANVAS_AGENT_CONTEXT")
    if agent_context_json:
        try:
            return json.loads(agent_context_json)
        except:
            logger.warning("Failed to parse CANVAS_AGENT_CONTEXT")
    
    # Check for agent metadata file in current directory
    metadata_file = Path(".agent-metadata.json")
    if metadata_file.exists():
        try:
            with open(metadata_file) as f:
                return json.load(f)
        except:
            logger.warning("Failed to load .agent-metadata.json")
    
    return None


def get_allowed_tools(agent_role: str) -> List[str]:
    """Get list of allowed tools for a role."""
    role_permissions = {
        "content_agent": [
            # Read-only tools
            "list_pages", "get_page", "list_assignments", "get_assignment",
            "list_quizzes", "get_quiz", "list_discussions", "get_discussion_posts",
            "get_rubric", "list_modules", "list_courses", "list_submissions",
            "get_submission", "sync_status", "quiz_sync_status", "module_sync_status",
            # Modification tools
            "create_page", "update_page", "delete_page",
            "pull_pages", "push_pages",
            "create_quiz", "update_quiz", "delete_quiz",
            "pull_quizzes", "push_quizzes",
            "update_assignment", "create_assignment",
            "update_rubric",
            "pull_modules", "push_modules",
            "create_discussion", "update_discussion",
            "pull_course_files", "download_pending_files"
        ],
        "style_agent": [
            # Read-only tools
            "list_pages", "get_page", "list_assignments", "get_assignment",
            "list_quizzes", "get_quiz", "list_discussions", "get_discussion_posts",
            "get_rubric", "list_modules", "list_courses", "list_submissions",
            "get_submission", "sync_status", "quiz_sync_status", "module_sync_status",
            # Review tools
            "submit_style_review", "get_item_review_history",
            "get_worktree_review_status", "get_review_conflicts"
        ],
        "fact_check_agent": [
            # Read-only tools
            "list_pages", "get_page", "list_assignments", "get_assignment",
            "list_quizzes", "get_quiz", "list_discussions", "get_discussion_posts",
            "get_rubric", "list_modules", "list_courses", "list_submissions",
            "get_submission", "sync_status", "quiz_sync_status", "module_sync_status",
            # Review tools
            "submit_fact_check_review", "get_item_review_history",
            "get_worktree_review_status", "get_review_conflicts"
        ],
        "consistency_agent": [
            # Read-only tools
            "list_pages", "get_page", "list_assignments", "get_assignment",
            "list_quizzes", "get_quiz", "list_discussions", "get_discussion_posts",
            "get_rubric", "list_modules", "list_courses", "list_submissions",
            "get_submission", "sync_status", "quiz_sync_status", "module_sync_status",
            # Review tools
            "submit_consistency_review", "get_item_review_history",
            "get_worktree_review_status", "get_review_conflicts"
        ],
        "approval_agent": [
            # Read-only tools
            "list_pages", "get_page", "list_assignments", "get_assignment",
            "list_quizzes", "get_quiz", "list_discussions", "get_discussion_posts",
            "get_rubric", "list_modules", "list_courses", "list_submissions",
            "get_submission", "sync_status", "quiz_sync_status", "module_sync_status",
            # Review tools
            "submit_style_review", "submit_fact_check_review", "submit_consistency_review",
            "get_item_review_history", "get_worktree_review_status",
            "get_review_conflicts", "escalate_review_conflict",
            # Merge/deploy tools
            "approve_and_merge_worktree"
        ]
    }
    
    return role_permissions.get(agent_role, [])


def require_agent_role(*allowed_roles: str) -> Callable:
    """
    Decorator to restrict tool access to specific agent roles.
    
    Usage:
        @require_agent_role("content_agent", "approval_agent")
        def my_tool(...) -> str:
            ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            agent_context = get_agent_context()
            
            # If no agent context, allow (running in CLI or non-agent context)
            if not agent_context:
                logger.debug(f"No agent context for {func.__name__}, allowing access")
                return func(*args, **kwargs)
            
            agent_role = agent_context.get("agent_role")
            
            if agent_role not in allowed_roles:
                raise ToolAccessError(
                    f"Agent role '{agent_role}' not authorized for {func.__name__}. "
                    f"Allowed roles: {', '.join(allowed_roles)}"
                )
            
            logger.info(f"Agent {agent_context.get('agent_id')} ({agent_role}) "
                       f"calling {func.__name__}")
            
            return func(*args, **kwargs)
        
        return wrapper
    return decorator


def require_scope(*content_types: str) -> Callable:
    """
    Decorator to restrict tool access based on content scope.
    
    Usage:
        @require_scope("pages", "quizzes")
        def my_tool(...) -> str:
            ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            agent_context = get_agent_context()
            
            # If no agent context, allow
            if not agent_context:
                return func(*args, **kwargs)
            
            agent_scope = agent_context.get("scope", [])
            
            if not any(ct in agent_scope for ct in content_types):
                raise ToolAccessError(
                    f"Content type not in agent scope. "
                    f"Agent scope: {agent_scope}, Required: {list(content_types)}"
                )
            
            logger.info(f"Agent {agent_context.get('agent_id')} "
                       f"has scope access for {func.__name__}")
            
            return func(*args, **kwargs)
        
        return wrapper
    return decorator


def check_tool_access(agent_role: str, tool_name: str) -> bool:
    """Check if an agent role can access a tool."""
    allowed = get_allowed_tools(agent_role)
    return tool_name in allowed
