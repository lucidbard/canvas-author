# Role-Based Multi-Agent Workflow Implementation

## Overview

This implementation enables agents to create course content in isolated git worktrees, receive specialized feedback (style, fact-check, consistency), vote on approvals, and merge changes back to main with a complete audit trail. The system enforces tool restrictions so review agents cannot modify content, only review and vote.

## Architecture

### Components

#### 1. **Python Backend (canvas-author)**

**New Modules:**

- **`workflow.py`** — Core workflow management
  - `ReviewPass`: Represents a single review pass (style, fact-check, or consistency)
  - `ItemReview`: Collects all reviews for a single item
  - `WorktreeReviewSession`: Manages all reviews for a worktree
  - `WorkflowManager`: Handles review persistence, loading, and querying
  - `create_agent_worktree()`: Creates git worktree with role-based tool restrictions

- **`tool_access.py`** — Tool access control and authorization
  - `get_agent_context()`: Retrieves agent identity and role from environment
  - `get_allowed_tools()`: Returns tool list for a given role
  - `require_agent_role()`: Decorator to restrict tool access by role
  - `require_scope()`: Decorator to restrict tool access by content type
  - `check_tool_access()`: Check if agent can use a tool

**New MCP Tools (in `server.py`):**

```
create_agent_worktree_tool(course_id, course_path, agent_name, agent_role, scope)
  ├─ Creates git worktree with agent metadata
  ├─ Returns tool restrictions for agent role
  └─ Status: active

submit_style_review(course_id, course_path, worktree_name, item_id, ..., decision, reasoning)
submit_fact_check_review(...)
submit_consistency_review(...)
  ├─ Submit review pass for an item
  ├─ Stored in ~/.canvas-author/reviews/{worktree_name}_{timestamp}.json
  └─ Indexed by worktree_name for persistence

get_item_review_history(course_path, item_id, include_archived=true)
  ├─ Get all reviews across all worktrees
  └─ Shows full review progression

get_worktree_review_status(course_path, worktree_name)
  ├─ Get summary of all reviews in a worktree
  └─ Returns approved/rejected/pending counts

get_review_conflicts(course_path, worktree_name="")
  ├─ Get all items with escalations
  └─ For human review

escalate_review_conflict(course_path, worktree_name, item_id, escalation_reason, ...)
  ├─ Mark item as escalated to human
  └─ Pauses worktree merge

approve_and_merge_worktree(course_path, worktree_name, approved_by_agent_id, review_summary)
  ├─ Merge git branch to main
  ├─ Delete worktree
  ├─ Archive reviews with metadata
  └─ Check Canvas sync status
```

#### 2. **VS Code Extension (canvas-author-code)**

**Updated Components:**

- **`courseTreeProvider.ts`**
  - Extended `SyncStatus` type: added `'pendingReview' | 'reviewApproved' | 'inWorktree'`
  - New icons: `pendingReview`, `reviewApproved`, `inWorktree`
  - New methods:
    - `getFileWorktreeContext()`: Check if file is in a worktree
    - `getItemReviewStatus()`: Query MCP for item's review status
    - `extractPageIdFromFrontmatter()`: Get page_id for review queries
  - Enhanced `getPageItems()`: Show worktree branch name and review status in tree

- **`extension.ts`**
  - New command: `approveAndMergeWorktree()`
  - Lists active worktrees, lets user select one
  - Shows confirmation dialog
  - Calls MCP tool to merge, delete, archive
  - Shows success with option to check Canvas sync

- **`package.json`**
  - New command: `canvas-author.approveAndMergeWorktree`

#### 3. **Configuration**

**`.canvas.workflow.yaml`** — Workflow configuration (in course root)
- Defines approval requirements per content type (pages, quizzes, assignments, rubrics, discussions)
- Specifies required review passes and number of approvers
- Defines agent roles and their allowed/restricted tools
- Escalation rules and merge strategy

## Workflow

### Create Agent Worktree

```
User/Agent calls: create_agent_worktree(course_id, course_path, agent_name, agent_role, scope)
  ↓
System creates git worktree from main branch
  ↓
Generate tool restriction manifest based on agent_role:
  - content_agent: Full read + write access
  - style_agent: Read + style review only
  - fact_check_agent: Read + fact-check review only
  - consistency_agent: Read + consistency review only
  - approval_agent: Read + review + merge access
  ↓
Store .agent-metadata.json in worktree root:
  {
    "worktree_name": "agent-claude-module1-abc123",
    "agent_name": "Claude",
    "agent_role": "content_agent",
    "scope": ["pages", "quizzes"],
    "tool_restrictions": {...},
    "status": "active"
  }
  ↓
Return: worktree_name, worktree_path, tool_restrictions
  ↓
Content agent edits in worktree, commits changes
```

### Review & Approval

```
Review agents work (in same or different worktree):
  - style_agent calls: submit_style_review(...)
  - fact_check_agent calls: submit_fact_check_review(...)
  - consistency_agent calls: submit_consistency_review(...)
  ↓
Reviews stored in: ~/.canvas-author/reviews/{worktree_name}_{timestamp}.json
  {
    "worktree_name": "...",
    "created_at": "...",
    "items": {
      "page:12345": {
        "item_id": "page:12345",
        "item_title": "Module Overview",
        "passes": [
          {
            "pass_type": "style",
            "agent_id": "agent-style-001",
            "decision": "approved",
            "reasoning": "..."
          },
          {
            "pass_type": "fact_check",
            "agent_id": "agent-factcheck-001",
            "decision": "rejected",
            "reasoning": "Claim unverified",
            "severity": "high"
          }
        ],
        "status": "rejected"  // One pass rejected
      }
    }
  }
  ↓
If any pass rejected:
  - escalate_review_conflict() marks item for human review
  - Human reviews conflicting feedback
  - Decides: approve override, request revision, or dismiss review
  ↓
If all passes approved:
  - Item status: "approved"
  - Ready for merge
```

### Merge Worktree

```
Human or approval_agent views VS Code tree:
  - Tree shows items with review status badges:
    ✓ (approved)
    ⏳ (pending review)
    ✗ (rejected / escalation)
    🔄 (in worktree)
  ↓
Right-click course → "Approve & Merge Worktree"
  ↓
Extension shows quick-pick of active worktrees
  ↓
User selects worktree
  ↓
Confirmation dialog with review summary
  ↓
Extension calls: approve_and_merge_worktree(...)
  ↓
MCP tool:
  1. Verify all required review passes approved
  2. git merge {worktree_branch} to main
  3. git worktree remove {worktree_path} --force
  4. Archive reviews: set archived_at, merged_by, merge_commit_hash
  5. Check Canvas sync
  ↓
Returns: merge_commit, deleted_worktree=true, reviews_archived=true, canvas_sync_status
  ↓
Extension shows: "✓ Merged! X items out of sync with Canvas"
  ↓
User can: "Push to Canvas" or iterate locally
```

## Tool Restrictions

### How They Work

1. **At Worktree Creation**: `create_agent_worktree()` generates tool restriction manifest
2. **Agent Environment**: Manifest passed to Claude/VS Code agent via:
   - System prompt instruction
   - `CANVAS_AGENT_CONTEXT` environment variable (JSON)
   - `.agent-metadata.json` in worktree root
3. **Tool Enforcement**: 
   - Content agents: Can call all tools
   - Review agents: Can only call read + review tools (no modifications)
   - Approval agent: Can call review + merge tools
4. **Runtime Check** (optional): MCP server uses `@require_agent_role()` decorator to verify

### Example: Review Agent Workflow

```yaml
Agent Role: fact_check_agent
Allowed Tools:
  - list_pages, get_page, list_quizzes, get_quiz, ... (all read-only)
  - submit_fact_check_review
  - get_item_review_history
  - get_worktree_review_status

Restricted Tools:
  - create_page, update_page, delete_page
  - push_pages, push_quizzes
  - approve_and_merge_worktree

Result:
  ✓ Can read all content
  ✓ Can submit fact-check reviews
  ✓ Cannot modify content
  ✓ Cannot merge worktrees
```

## Review Persistence

Reviews are stored centrally, indexed by worktree name, and survive worktree deletion.

### Storage Location

```
~/.canvas-author/reviews/
  ├─ agent-claude-module1-abc123_2025-01-13T10-30-00Z.json
  ├─ agent-claude-quiz1-def456_2025-01-13T11-00-00Z.json
  └─ ...
```

### Querying Reviews

```python
# All reviews for a specific item (across all worktrees)
history = wm.get_item_review_history(item_id="page:12345", include_archived=True)
# Returns: [
#   {worktree_name: "...", item: {...passes, status}},
#   {worktree_name: "...", item: {...passes, status}},
#   ...
# ]

# All reviews from a specific worktree
conflicts = wm.get_worktree_review_conflicts(worktree_name="agent-claude-module1")
# Returns items with escalations/conflicts

# Post-merge: Review data persists
# Worktree deleted? Reviews still accessible:
archived_history = wm.get_item_review_history(item_id="page:12345")
# Shows reviews with archived_at, merged_by, merge_commit_hash
```

## VS Code Integration

### Tree Icons

- **✓ (synced)** — Matches Canvas
- **⚠️ (modified)** — Changed locally
- **↑ (localOnly)** — Not in Canvas
- **↓ (canvasOnly)** — Not downloaded
- **💬 (pendingReview)** — Awaiting approval
- **💬✓ (reviewApproved)** — Approved
- **🔀 (inWorktree)** — In active worktree

### Item Description

```
Page Title
├─ If in worktree: "🔀 agent-claude-module1-abc123"
├─ If has review: Shows review status
└─ If published: "✓ Published" or "○ Unpublished"
```

### Context Menu

```
Right-click on course:
  → Approve & Merge Worktree
      Shows list of active worktrees
      Prompts for confirmation
      Executes merge + cleanup + archive
```

## Usage Examples

### 1. Create Worktree for Content Agent

```bash
# Agent calls MCP:
POST /mcp
{
  "method": "create_agent_worktree_tool",
  "params": {
    "course_id": "12345",
    "course_path": "/path/to/course",
    "agent_name": "claude-content-module1",
    "agent_role": "content_agent",
    "scope": ["pages", "quizzes"]
  }
}

# Response:
{
  "worktree_name": "claude-content-module1-20250113-abc123",
  "worktree_path": "/path/to/course/claude-content-module1-20250113-abc123",
  "agent_role": "content_agent",
  "scope": ["pages", "quizzes"],
  "tool_restrictions": {
    "allowed": [...list of 50+ tools...],
    "restricted": []
  },
  "status": "created"
}

# Content agent edits files, commits
cd /path/to/course/claude-content-module1-20250113-abc123
# Edit pages/, quizzes/ ...
git add .
git commit -m "Update module 1 content"
```

### 2. Style Agent Reviews

```bash
# After content agent commits:
POST /mcp
{
  "method": "submit_style_review",
  "params": {
    "course_id": "12345",
    "course_path": "/path/to/course",
    "worktree_name": "claude-content-module1-20250113-abc123",
    "item_id": "page:12345",
    "item_title": "Module 1 Overview",
    "item_type": "page",
    "canvas_id": "12345",
    "file_path": "pages/module-1-overview.md",
    "agent_id": "agent-style-001",
    "decision": "approved",
    "reasoning": "Tone consistent with course voice; no grammar issues"
  }
}

# Response:
{
  "status": "success",
  "review_pass": {
    "pass_type": "style",
    "decision": "approved",
    "timestamp": "2025-01-13T10:40:00Z",
    ...
  },
  "item_status": "approved"  // If all passes approved
}
```

### 3. Fact-Check Agent Flags Issue

```bash
POST /mcp
{
  "method": "submit_fact_check_review",
  "params": {
    "course_id": "12345",
    "course_path": "/path/to/course",
    "worktree_name": "claude-content-module1-20250113-abc123",
    "item_id": "page:12345",
    "item_title": "Module 1 Overview",
    "item_type": "page",
    "canvas_id": "12345",
    "file_path": "pages/module-1-overview.md",
    "agent_id": "agent-factcheck-001",
    "decision": "rejected",
    "reasoning": "Claim 'Renaissance 1400-1600' contradicts Module 0 which states 1350-1550",
    "references": ["page:5678"],
    "severity": "high"
  }
}

# Response: item_status = "rejected"
```

### 4. Escalate Conflict

```bash
POST /mcp
{
  "method": "escalate_review_conflict",
  "params": {
    "course_path": "/path/to/course",
    "worktree_name": "claude-content-module1-20250113-abc123",
    "item_id": "page:12345",
    "escalation_reason": "Fact-check contradicts content agent's dates. Need human decision.",
    "conflicting_reviews": "[...serialized review passes...]"
  }
}

# Response:
{
  "status": "escalated",
  "item_id": "page:12345",
  "escalation": {
    "status": "pending_human_review",
    "reason": "...",
    "escalated_at": "2025-01-13T10:50:00Z",
    "conflicting_reviews": [...]
  }
}
```

### 5. Human Reviews and Approves Merge

```
VS Code:
  View tree:
    📚 Course 12345
      📄 Pages
        └─ Module 1 Overview  💬✗ (has review issues)
      🎯 Quizzes
        └─ Module 1 Quiz  ✓

  Right-click Course → "Approve & Merge Worktree"
    Quick-pick: Select "claude-content-module1-20250113-abc123"
    Confirmation: Show review summary
      - 1 item has escalation
      - 2 items approved
      - Click: Review Escalations / Approve & Merge
    
    User clicks escalation → Shows fact-checker vs. content disagreement
    User decides: "Approve override - dates are context-dependent"
    
    Click: "Approve & Merge"
```

### 6. Merge Executes

```bash
POST /mcp
{
  "method": "approve_and_merge_worktree",
  "params": {
    "course_path": "/path/to/course",
    "worktree_name": "claude-content-module1-20250113-abc123",
    "approved_by_agent_id": "human-reviewer",
    "review_summary": "Approved with override on fact-check: dates are context-dependent"
  }
}

# System executes:
# 1. git merge claude-content-module1-20250113-abc123 (from branch)
# 2. git worktree remove claude-content-module1-20250113-abc123 --force
# 3. Archive reviews with: archived_at, merged_by, merge_commit_hash
# 4. Check Canvas sync

# Response:
{
  "status": "success",
  "merge_commit": "abc123def456",
  "deleted_worktree": true,
  "reviews_archived": true,
  "canvas_sync_status": {
    "out_of_sync_items": [
      {"item_id": "page:12345", "reason": "modified_locally"}
    ],
    "push_to_canvas_available": true
  }
}

# VS Code shows: "✓ Merged! 1 item out of sync with Canvas"
# Offers: "Push to Canvas"
```

## Future Enhancements

1. **Scheduled Reviews** — Auto-schedule reviews for agent work
2. **Review Templates** — Pre-filled review forms for common issues
3. **Batch Operations** — Review/merge multiple items in one action
4. **Statistics & Analytics** — Track review turnaround, approval rates
5. **Review Notifications** — Email/Slack alerts when reviews needed
6. **Custom Review Criteria** — Define custom checks per course
7. **Diff Viewer** — Side-by-side comparison of old vs. new in UI
8. **Review Comments** — Back-and-forth discussion before approval

## Troubleshooting

### Review Not Showing in Tree

- Check: `~/.canvas-author/reviews/` for review files
- Verify: item_id format is `type:canvas_id` (e.g., `page:12345`)
- Try: Refresh courses tree (`canvas-author.refreshCourses`)

### Cannot Merge Worktree

- Check: All required review passes approved
- Check: No git merge conflicts (resolve manually if needed)
- Try: `git worktree list` to verify worktree exists

### Tool Restriction Not Enforced

- Check: `.agent-metadata.json` in worktree root
- Check: `CANVAS_AGENT_CONTEXT` environment variable set
- Verify: Agent running in correct worktree directory

### Reviews Lost After Worktree Delete

- Reviews should NOT be lost — they're in `~/.canvas-author/reviews/`
- If missing: Check file permissions on `~/.canvas-author/` directory
- Restore: Look for `{worktree_name}_*.json` files

## Configuration Reference

See `.canvas.workflow.yaml` for full configuration options including:
- Per-content-type approval requirements
- Agent roles and tool access
- Escalation rules
- Merge strategy options
