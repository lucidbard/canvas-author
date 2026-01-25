"""
Workflow management for multi-agent content review and approval.

Handles:
- Worktree creation with role-based tool restrictions
- Review pass tracking (style, fact-check, consistency)
- Approval workflows with human escalation
- Review persistence and archival
"""

import json
import logging
import os
import subprocess
from datetime import datetime
from typing import Optional, List, Dict, Any
from pathlib import Path

logger = logging.getLogger("canvas_author.workflow")


class ReviewPass:
    """Represents a single review pass on an item."""

    PASS_TYPES = ["style", "fact_check", "consistency", "human"]
    DECISIONS = ["approved", "rejected", "needs_revision"]
    
    def __init__(
        self,
        pass_type: str,
        agent_id: str,
        agent_role: str,
        decision: str,
        reasoning: str,
        severity: str = "medium",
        timestamp: Optional[str] = None,
        references: Optional[List[str]] = None
    ):
        if pass_type not in self.PASS_TYPES:
            raise ValueError(f"Invalid pass_type: {pass_type}")
        if decision not in self.DECISIONS:
            raise ValueError(f"Invalid decision: {decision}")
        
        self.pass_type = pass_type
        self.agent_id = agent_id
        self.agent_role = agent_role
        self.decision = decision
        self.reasoning = reasoning
        self.severity = severity
        self.timestamp = timestamp or datetime.utcnow().isoformat() + "Z"
        self.references = references or []
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "pass_type": self.pass_type,
            "agent_id": self.agent_id,
            "agent_role": self.agent_role,
            "decision": self.decision,
            "reasoning": self.reasoning,
            "severity": self.severity,
            "timestamp": self.timestamp,
            "references": self.references
        }


class ItemReview:
    """Reviews for a single item across all passes."""
    
    def __init__(
        self,
        item_id: str,
        item_title: str,
        item_type: str,
        canvas_id: str,
        file_path: str
    ):
        self.item_id = item_id
        self.item_title = item_title
        self.item_type = item_type
        self.canvas_id = canvas_id
        self.file_path = file_path
        self.passes: List[ReviewPass] = []
        self.escalation: Optional[Dict[str, Any]] = None
    
    def add_pass(self, review_pass: ReviewPass) -> None:
        """Add a review pass result."""
        self.passes.append(review_pass)
    
    def get_pass_by_type(self, pass_type: str) -> Optional[ReviewPass]:
        """Get review pass by type."""
        for p in self.passes:
            if p.pass_type == pass_type:
                return p
        return None
    
    def get_status(self) -> str:
        """Get overall status: approved, rejected, or escalation."""
        if self.escalation:
            return "escalation_" + self.escalation.get("status", "unknown")
        
        if not self.passes:
            return "no_reviews"
        
        rejections = [p for p in self.passes if p.decision == "rejected"]
        if rejections:
            return "rejected"
        
        all_approved = all(p.decision == "approved" for p in self.passes)
        if all_approved:
            return "approved"
        
        return "pending"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "item_id": self.item_id,
            "item_title": self.item_title,
            "item_type": self.item_type,
            "canvas_id": self.canvas_id,
            "file_path": self.file_path,
            "passes": [p.to_dict() for p in self.passes],
            "escalation": self.escalation,
            "status": self.get_status()
        }


class WorktreeReviewSession:
    """Manages all reviews for a worktree."""
    
    def __init__(
        self,
        worktree_name: str,
        course_id: str,
        created_at: Optional[str] = None
    ):
        self.worktree_name = worktree_name
        self.course_id = course_id
        self.created_at = created_at or datetime.utcnow().isoformat() + "Z"
        self.items: Dict[str, ItemReview] = {}
        self.archived_at: Optional[str] = None
        self.merged_by: Optional[str] = None
        self.merge_commit_hash: Optional[str] = None
    
    def add_item_review(self, item_review: ItemReview) -> None:
        """Add or update an item's review."""
        self.items[item_review.item_id] = item_review
    
    def get_item_review(self, item_id: str) -> Optional[ItemReview]:
        """Get review for a specific item."""
        return self.items.get(item_id)
    
    def get_summary(self) -> Dict[str, Any]:
        """Get summary of all reviews in this session."""
        approved = sum(1 for i in self.items.values() if i.get_status() == "approved")
        rejected = sum(1 for i in self.items.values() if i.get_status() == "rejected")
        escalations = sum(1 for i in self.items.values() if "escalation" in i.get_status())
        
        return {
            "total_items": len(self.items),
            "approved": approved,
            "rejected": rejected,
            "escalations": escalations,
            "pending": len(self.items) - approved - rejected - escalations
        }
    
    def archive(
        self,
        merged_by: str,
        merge_commit_hash: str
    ) -> None:
        """Mark session as archived after merge."""
        self.archived_at = datetime.utcnow().isoformat() + "Z"
        self.merged_by = merged_by
        self.merge_commit_hash = merge_commit_hash
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "worktree_name": self.worktree_name,
            "course_id": self.course_id,
            "created_at": self.created_at,
            "archived_at": self.archived_at,
            "merged_by": self.merged_by,
            "merge_commit_hash": self.merge_commit_hash,
            "items": {item_id: item.to_dict() for item_id, item in self.items.items()},
            "summary": self.get_summary()
        }


class WorkflowManager:
    """Manages workflow configuration and review state."""
    
    def __init__(self, course_dir: str):
        self.course_dir = course_dir
        self.reviews_dir = Path.home() / ".canvas-author" / "reviews"
        self.workflow_config_path = Path(course_dir) / ".canvas.workflow.yaml"
        self.reviews_dir.mkdir(parents=True, exist_ok=True)
    
    def get_workflow_config(self) -> Dict[str, Any]:
        """Load workflow configuration from course directory."""
        if not self.workflow_config_path.exists():
            return self._get_default_workflow()
        
        import yaml
        with open(self.workflow_config_path) as f:
            config = yaml.safe_load(f)
        
        return config or self._get_default_workflow()
    
    def _get_default_workflow(self) -> Dict[str, Any]:
        """Get default workflow configuration."""
        return {
            "pages": {
                "required_passes": ["style", "fact_check", "consistency"],
                "required_approvals": 1,
                "approval_type": "consensus"
            },
            "quizzes": {
                "required_passes": ["style", "fact_check", "consistency"],
                "required_approvals": 2,
                "approval_type": "consensus"
            },
            "assignments": {
                "required_passes": ["fact_check", "consistency", "style"],
                "required_approvals": 2,
                "approval_type": "consensus"
            },
            "rubrics": {
                "required_passes": ["consistency", "style"],
                "required_approvals": 1,
                "approval_type": "single"
            }
        }
    
    def save_review_session(self, session: WorktreeReviewSession) -> str:
        """Save review session to disk."""
        timestamp = datetime.utcnow().strftime("%Y-%m-%dT%H-%M-%SZ")
        filename = f"{session.worktree_name}_{timestamp}.json"
        filepath = self.reviews_dir / filename
        
        with open(filepath, "w") as f:
            json.dump(session.to_dict(), f, indent=2)
        
        logger.info(f"Saved review session to {filepath}")
        return str(filepath)
    
    def load_review_session(self, filename: str) -> WorktreeReviewSession:
        """Load review session from disk."""
        filepath = self.reviews_dir / filename
        
        with open(filepath) as f:
            data = json.load(f)
        
        session = WorktreeReviewSession(
            data["worktree_name"],
            data["course_id"],
            data["created_at"]
        )
        
        for item_id, item_data in data.get("items", {}).items():
            item_review = ItemReview(
                item_data["item_id"],
                item_data["item_title"],
                item_data["item_type"],
                item_data["canvas_id"],
                item_data["file_path"]
            )
            
            for pass_data in item_data.get("passes", []):
                review_pass = ReviewPass(
                    pass_data["pass_type"],
                    pass_data["agent_id"],
                    pass_data["agent_role"],
                    pass_data["decision"],
                    pass_data["reasoning"],
                    pass_data.get("severity", "medium"),
                    pass_data.get("timestamp"),
                    pass_data.get("references", [])
                )
                item_review.add_pass(review_pass)
            
            if item_data.get("escalation"):
                item_review.escalation = item_data["escalation"]
            
            session.add_item_review(item_review)
        
        if data.get("archived_at"):
            session.archived_at = data["archived_at"]
        if data.get("merged_by"):
            session.merged_by = data["merged_by"]
        if data.get("merge_commit_hash"):
            session.merge_commit_hash = data["merge_commit_hash"]
        
        return session
    
    def get_item_review_history(
        self,
        item_id: str,
        include_archived: bool = True
    ) -> List[Dict[str, Any]]:
        """Get all reviews for an item across all worktrees."""
        reviews = []
        
        for review_file in self.reviews_dir.glob("*.json"):
            try:
                session = self.load_review_session(review_file.name)
                
                if not include_archived and session.archived_at:
                    continue
                
                item_review = session.get_item_review(item_id)
                if item_review:
                    reviews.append({
                        "worktree_name": session.worktree_name,
                        "review_session": session.created_at,
                        "archived_at": session.archived_at,
                        "merged_by": session.merged_by,
                        "merge_commit_hash": session.merge_commit_hash,
                        "item": item_review.to_dict()
                    })
            except Exception as e:
                logger.error(f"Failed to load review {review_file}: {e}")
        
        # Sort by timestamp descending
        reviews.sort(key=lambda x: x["review_session"], reverse=True)
        return reviews
    
    def get_worktree_review_conflicts(
        self,
        worktree_name: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get all items with escalations/conflicts."""
        conflicts = []
        
        for review_file in self.reviews_dir.glob("*.json"):
            try:
                session = self.load_review_session(review_file.name)
                
                if worktree_name and session.worktree_name != worktree_name:
                    continue
                
                for item_review in session.items.values():
                    if item_review.escalation:
                        conflicts.append({
                            "worktree_name": session.worktree_name,
                            "item_id": item_review.item_id,
                            "item_title": item_review.item_title,
                            "escalation": item_review.escalation,
                            "passes": [p.to_dict() for p in item_review.passes]
                        })
            except Exception as e:
                logger.error(f"Failed to load review {review_file}: {e}")
        
        return conflicts


def create_agent_worktree(
    course_id: str,
    course_path: str,
    agent_name: str,
    agent_role: str,
    scope: List[str]
) -> Dict[str, Any]:
    """
    Create a new git worktree for an agent with role-based restrictions.
    Worktrees are stored in .canvas-author/worktrees/ (gitignored).
    
    Args:
        course_id: Canvas course ID
        course_path: Path to course directory
        agent_name: Name/ID of the agent
        agent_role: Role of agent (content_agent, style_agent, fact_check_agent, consistency_agent)
        scope: List of content types this agent can work on (e.g., ["pages", "quizzes"])
    
    Returns:
        Dict with worktree info and tool restrictions
    """
    from datetime import datetime
    import uuid
    
    # Generate worktree name
    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    unique_id = str(uuid.uuid4())[:8]
    worktree_name = f"{agent_name}-{timestamp}-{unique_id}"
    
    # Create worktree in .canvas-author/worktrees/ subdirectory
    canvas_author_dir = Path(course_path) / ".canvas-author"
    worktrees_dir = canvas_author_dir / "worktrees"
    worktrees_dir.mkdir(parents=True, exist_ok=True)
    
    worktree_path = worktrees_dir / worktree_name
    
    try:
        # Create worktree from main branch
        subprocess.run(
            ["git", "worktree", "add", str(worktree_path), "main"],
            cwd=course_path,
            check=True,
            capture_output=True
        )
        
        logger.info(f"Created worktree: {worktree_name}")
    except subprocess.CalledProcessError as e:
        return {"error": f"Failed to create worktree: {e.stderr.decode()}"}
    
    # Generate tool restrictions based on role
    tool_restrictions = _get_tool_restrictions_for_role(agent_role)
    
    # Store metadata
    metadata = {
        "worktree_name": worktree_name,
        "agent_name": agent_name,
        "agent_role": agent_role,
        "created_at": datetime.utcnow().isoformat() + "Z",
        "scope": scope,
        "status": "active",
        "tool_restrictions": tool_restrictions,
        "git_ref": subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=course_path,
            capture_output=True,
            text=True
        ).stdout.strip()
    }
    
    # Save metadata to worktree
    metadata_file = worktree_path / ".agent-metadata.json"
    with open(metadata_file, "w") as f:
        json.dump(metadata, f, indent=2)
    
    return {
        "worktree_name": worktree_name,
        "worktree_path": str(worktree_path),
        "agent_role": agent_role,
        "scope": scope,
        "tool_restrictions": tool_restrictions,
        "status": "created"
    }


def _get_tool_restrictions_for_role(role: str) -> Dict[str, List[str]]:
    """Get allowed MCP tools for a given agent role."""
    
    # Read-only tools available to all roles
    read_only_tools = [
        "list_pages", "get_page", "list_assignments", "get_assignment",
        "list_quizzes", "get_quiz", "list_discussions", "get_discussion_posts",
        "get_rubric", "list_modules", "list_courses", "list_submissions",
        "get_submission", "sync_status", "quiz_sync_status", "module_sync_status"
    ]
    
    # Review tools for review agents
    review_tools = [
        "submit_style_review", "submit_fact_check_review",
        "submit_consistency_review", "get_item_reviews",
        "get_worktree_review_status"
    ]
    
    # Modification tools for content agents
    modification_tools = [
        "create_page", "update_page", "delete_page",
        "pull_pages", "push_pages",
        "create_quiz", "update_quiz", "delete_quiz",
        "pull_quizzes", "push_quizzes",
        "update_assignment", "create_assignment",
        "update_rubric",
        "pull_modules", "push_modules",
        "create_discussion", "update_discussion"
    ]
    
    if role == "content_agent":
        return {
            "allowed": read_only_tools + modification_tools,
            "restricted": []
        }
    
    elif role in ["style_agent", "fact_check_agent", "consistency_agent"]:
        return {
            "allowed": read_only_tools + review_tools,
            "restricted": modification_tools
        }
    
    elif role == "approval_agent":
        return {
            "allowed": read_only_tools + review_tools + ["approve_and_merge_worktree"],
            "restricted": modification_tools
        }
    
    else:
        # Default: read-only
        return {
            "allowed": read_only_tools,
            "restricted": modification_tools + review_tools
        }
