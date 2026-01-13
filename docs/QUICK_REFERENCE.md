# Quick Reference: Role-Based Multi-Agent Workflow

## Quick Start for Developers

### 1. Create Worktree for Content Agent

```bash
# Via MCP API (Python)
result = await mcp.call_tool('create_agent_worktree_tool', {
    'course_id': '12345',
    'course_path': '/path/to/course',
    'agent_name': 'claude-content-module1',
    'agent_role': 'content_agent',
    'scope': ['pages', 'quizzes']
})

# Returns:
{
  'worktree_name': 'claude-content-module1-20250113-abc123',
  'worktree_path': '/path/to/course/claude-content-module1-20250113-abc123',
  'tool_restrictions': {...}
}

# Content agent edits in worktree, commits changes
cd /path/to/course/claude-content-module1-20250113-abc123
# Create/edit pages/, quizzes/, assignments/, etc.
git add .
git commit -m "Update Module 1 content"
```

### 2. Submit Reviews

```bash
# Style Agent
submit_style_review(
    course_id='12345',
    course_path='/path/to/course',
    worktree_name='claude-content-module1-20250113-abc123',
    item_id='page:12345',
    item_title='Module 1 Overview',
    item_type='page',
    canvas_id='12345',
    file_path='pages/module-1-overview.md',
    agent_id='agent-style-001',
    decision='approved',
    reasoning='Tone consistent with course voice; no grammar issues'
)

# Fact-Check Agent
submit_fact_check_review(
    course_id='12345',
    course_path='/path/to/course',
    worktree_name='claude-content-module1-20250113-abc123',
    item_id='page:12345',
    item_title='Module 1 Overview',
    item_type='page',
    canvas_id='12345',
    file_path='pages/module-1-overview.md',
    agent_id='agent-factcheck-001',
    decision='rejected',
    reasoning='Date range contradicts Module 0',
    references='page:5678',
    severity='high'
)

# Consistency Agent (similar)
submit_consistency_review(...)
```

### 3. Query Reviews

```bash
# Get all reviews for an item (across all worktrees)
history = get_item_review_history(
    course_path='/path/to/course',
    item_id='page:12345',
    include_archived=True
)

# Get worktree summary
status = get_worktree_review_status(
    course_path='/path/to/course',
    worktree_name='claude-content-module1-20250113-abc123'
)

# Get conflicts/escalations
conflicts = get_review_conflicts(
    course_path='/path/to/course',
    worktree_name='claude-content-module1-20250113-abc123'
)
```

### 4. Escalate Conflict (if needed)

```bash
escalate_review_conflict(
    course_path='/path/to/course',
    worktree_name='claude-content-module1-20250113-abc123',
    item_id='page:12345',
    escalation_reason='Fact-checker and content differ on dates. Need human decision.',
    conflicting_reviews='[...JSON array of conflicting passes...]'
)
```

### 5. Approve & Merge (from VS Code)

```
1. Open VS Code with course directory
2. View Courses tree
3. Right-click course → "Approve & Merge Worktree"
4. Quick-pick: Select worktree from list
5. Confirmation dialog shows review summary
6. Click: "Merge & Delete"
7. System: Merges to main, deletes worktree, archives reviews
8. Notification: Success + "Check Canvas Sync" button
```

## Key Concepts

### Review Passes
- **style**: Tone, grammar, consistency with course voice
- **fact_check**: Claims, sources, accuracy verification
- **consistency**: Module integration, prerequisites, alignment

### Agent Roles
- **content_agent**: Full tool access (read + write)
- **style_agent**: Read + style review only
- **fact_check_agent**: Read + fact-check review only
- **consistency_agent**: Read + consistency review only
- **approval_agent**: Read + review + merge

### Review Status
- **approved**: All required passes approved
- **rejected**: At least one pass rejected
- **escalation_pending**: Needs human decision
- **escalation_paused**: Paused pending human resolution

### Tree Icons
- ✓ Synced with Canvas
- ⚠️ Modified locally
- ↑ Local only (not in Canvas)
- ↓ Canvas only (not local)
- 💬 Pending review
- 💬✓ Review approved
- 🔀 In active worktree

## Configuration Files

### `.canvas.workflow.yaml` (in course root)

```yaml
workflows:
  pages:
    required_passes: [style, fact_check, consistency]
    required_approvals: 1
  
  quizzes:
    required_passes: [style, fact_check, consistency]
    required_approvals: 2
  
  # ... other content types
```

### `.agent-metadata.json` (in worktree root)

Auto-generated when creating worktree:
```json
{
  "worktree_name": "...",
  "agent_name": "...",
  "agent_role": "content_agent",
  "scope": ["pages", "quizzes"],
  "tool_restrictions": {...},
  "status": "active"
}
```

## Review Storage

All reviews stored in:
```
~/.canvas-author/reviews/
  └─ {worktree_name}_{timestamp}.json
```

Reviews indexed by `worktree_name`, queryable even after worktree deleted.

Structure:
```json
{
  "worktree_name": "...",
  "created_at": "...",
  "archived_at": "2025-01-13T14:45:00Z",  // Set after merge
  "merged_by": "human-approver",
  "merge_commit_hash": "abc123...",
  "items": {
    "page:12345": {
      "passes": [
        {"pass_type": "style", "decision": "approved", ...},
        {"pass_type": "fact_check", "decision": "rejected", ...}
      ],
      "status": "rejected",
      "escalation": {...}  // If escalated
    }
  }
}
```

## MCP Tools Quick Reference

| Tool | Role | Purpose |
|------|------|---------|
| `create_agent_worktree_tool` | - | Create worktree with restrictions |
| `submit_style_review` | style_agent | Submit style pass |
| `submit_fact_check_review` | fact_check_agent | Submit fact-check pass |
| `submit_consistency_review` | consistency_agent | Submit consistency pass |
| `get_item_review_history` | Any | Query reviews for item |
| `get_worktree_review_status` | Any | Get worktree summary |
| `get_review_conflicts` | Any | Get escalated items |
| `escalate_review_conflict` | Any | Mark for human review |
| `approve_and_merge_worktree` | approval_agent | Merge & cleanup |

## Troubleshooting

### "Permission denied" when submitting review
- Check: Agent role allows that review type
- Check: Agent in correct worktree directory (has `.agent-metadata.json`)

### Reviews not showing in tree
- Check: Item ID format: `page:12345` (not just `12345`)
- Check: Reviews saved to `~/.canvas-author/reviews/`
- Try: Refresh courses tree

### Merge fails with conflict
- Resolve: Git conflicts manually
- Command: `git merge --abort`, then fix manually, then retry

### Can't see tool restrictions
- Check: Running in worktree directory
- Check: `CANVAS_AGENT_CONTEXT` environment variable set
- Check: `.agent-metadata.json` file exists

## File Locations

| Item | Location |
|------|----------|
| Workflow config | `{course_root}/.canvas.workflow.yaml` |
| Worktree metadata | `{course_root}/{worktree_name}/.agent-metadata.json` |
| Reviews (persistent) | `~/.canvas-author/reviews/{worktree_name}_{timestamp}.json` |
| Extension UI | VS Code Courses sidebar |
| MCP Server | `canvas_author.server` module |
| Workflow logic | `canvas_author.workflow` module |
| Tool access control | `canvas_author.tool_access` module |

## Environment Variables

Set when creating agent:

```bash
# Claude/Agent context
export CANVAS_AGENT_CONTEXT='{"agent_id":"agent-001","agent_role":"content_agent","scope":["pages"]}'

# Or store in .agent-metadata.json in worktree root
```

## Next Steps

1. **Test with Claude**: Create worktree, have Claude write content, review it
2. **Add UI**: Build review viewer panel in VS Code
3. **Integrate Canvas**: Auto-push approved content to Canvas
4. **Analytics**: Track review metrics
5. **Automation**: Schedule reviews, auto-merge if no issues
