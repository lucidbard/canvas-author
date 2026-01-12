# Canvas Discussion Checkpoints Analysis

## Overview

Canvas supports **checkpointed discussions** - a feature that allows separate grading and due dates for initial posts vs. peer replies. This is not currently supported by canvas-author.

## Key Features Identified

### 1. Discussion Topic Fields

From the Canvas API `/api/v1/courses/{course_id}/discussion_topics/{topic_id}` response:

```json
{
  "reply_to_entry_required_count": 2,
  "is_checkpointed": true,
  "require_initial_post": true
}
```

- **`reply_to_entry_required_count`**: Minimum number of replies required from each student
- **`is_checkpointed`**: Boolean indicating if this discussion uses checkpoint grading
- **`require_initial_post`**: Students must post before seeing others' posts

### 2. Assignment Checkpoint Structure

When checkpoints are enabled, the assignment includes a `checkpoints` array with two objects:

```json
{
  "has_sub_assignments": true,
  "checkpoints": [
    {
      "name": "Week 1 Discussion: AI Development Experience",
      "tag": "reply_to_topic",
      "points_possible": 6.0,
      "due_at": "2026-01-16T04:59:59Z",
      "only_visible_to_overrides": false,
      "overrides": [],
      "unlock_at": null,
      "lock_at": null
    },
    {
      "name": "Week 1 Discussion: AI Development Experience",
      "tag": "reply_to_entry",
      "points_possible": 4.0,
      "due_at": "2026-01-19T04:59:59Z",
      "only_visible_to_overrides": false,
      "overrides": [],
      "unlock_at": null,
      "lock_at": null
    }
  ]
}
```

**Checkpoint Tags:**
- **`reply_to_topic`**: Initial post checkpoint
- **`reply_to_entry`**: Peer reply checkpoint

**Each checkpoint has:**
- Separate point allocation
- Separate due date
- Support for overrides (differentiated assignments)
- Optional unlock/lock dates

### 3. Grading Behavior

When checkpoints are enabled:
1. Canvas tracks initial posts separately from replies
2. Points are allocated to each checkpoint independently
3. Gradebook shows two sub-columns under the discussion assignment
4. Students see two separate due dates in their calendar
5. Instructors can grade each checkpoint independently

## Recommendations for canvas-author

### 1. Data Structure Changes

**Discussion YAML Format** (new fields):

```yaml
discussion_id: 8424822
assignment_id: 9398144
title: Week 1 Discussion - AI Development Experience
discussion_type: threaded
published: true
require_initial_post: true
reply_to_entry_required_count: 2  # NEW
is_checkpointed: true  # NEW
checkpoints:  # NEW
  - tag: reply_to_topic
    name: Week 1 Discussion - AI Development Experience
    points_possible: 6.0
    due_at: "2026-01-16T04:59:59Z"
    unlock_at: null
    lock_at: null
  - tag: reply_to_entry
    name: Week 1 Discussion - AI Development Experience
    points_possible: 4.0
    due_at: "2026-01-19T04:59:59Z"
    unlock_at: null
    lock_at: null
message: |
  [Discussion content in markdown...]
```

### 2. API Integration

**Create Checkpointed Discussion:**

When `is_checkpointed: true`, the API call must include:

```python
discussion_data = {
    'title': 'Discussion Title',
    'message': '<html content>',
    'discussion_type': 'threaded',
    'published': True,
    'require_initial_post': True,
    'reply_to_entry_required_count': 2,
    'assignment': {
        'points_possible': 10,  # Total points (sum of checkpoints)
        'grading_type': 'points',
        'submission_types': ['discussion_topic'],
        'assignment_group_id': 2396054,
        # Checkpoints must be created via separate API endpoint
        # after initial discussion creation
    }
}
```

**Note:** Based on Canvas API documentation, checkpoints are likely created/updated via:
- `PUT /api/v1/courses/{course_id}/assignments/{assignment_id}` with checkpoint data
- Or a dedicated checkpoint endpoint (needs investigation)

### 3. Functions Needed

**In `discussion_sync.py` (new file):**

```python
def create_discussion(course_id: str, discussion_data: dict) -> dict:
    """Create discussion with optional checkpoints"""

def update_discussion(course_id: str, discussion_id: str, updates: dict) -> dict:
    """Update existing discussion including checkpoints"""

def pull_discussions(course_id: str, output_dir: str) -> dict:
    """Download all discussions to local YAML files"""

def push_discussions(course_id: str, input_dir: str) -> dict:
    """Upload local YAML discussions to Canvas"""

def create_checkpoints(course_id: str, assignment_id: str, checkpoints: list) -> dict:
    """Create or update checkpoints for a discussion assignment"""
```

### 4. GitHub Issue Update

The existing issue #1 should be updated to include checkpoint support:

- Support for `is_checkpointed`, `reply_to_entry_required_count`, `require_initial_post`
- Checkpoint configuration (tags, points, due dates)
- Pulling checkpoint data to YAML
- Pushing checkpoint data to Canvas
- Validation of checkpoint structure (must have both reply_to_topic and reply_to_entry)

### 5. MCP Tool Additions

**For `canvas_author/server.py`:**

```python
@server.call_tool()
async def create_discussion(
    course_id: str,
    title: str,
    body: str,
    discussion_type: str = "threaded",
    published: bool = True,
    is_checkpointed: bool = False,
    reply_to_entry_required_count: int = 0,
    checkpoints: Optional[list] = None
) -> list[types.TextContent]:
    """Create a discussion topic with optional checkpoint grading"""
```

## Implementation Priority

1. **High Priority:**
   - `pull_discussions()` - Download existing discussions with checkpoint data
   - `create_discussion()` - Create discussions with checkpoint support
   - YAML structure definition

2. **Medium Priority:**
   - `update_discussion()` - Update checkpoint configuration
   - `push_discussions()` - Bulk sync from YAML to Canvas
   - Checkpoint validation logic

3. **Low Priority:**
   - Discussion sync status checking
   - Bulk delete operations
   - Advanced checkpoint features (overrides, differentiated assignments)

## Testing Checklist

- [ ] Create discussion without checkpoints (backward compatibility)
- [ ] Create discussion with checkpoints (2 due dates, split points)
- [ ] Pull existing checkpointed discussion to YAML
- [ ] Modify YAML checkpoint config and push back to Canvas
- [ ] Verify gradebook shows separate checkpoint columns
- [ ] Test with `require_initial_post` enabled/disabled
- [ ] Test with different `reply_to_entry_required_count` values

## References

- Canvas API: Discussion Topics - https://canvas.instructure.com/doc/api/discussion_topics.html
- Canvas API: Assignments - https://canvas.instructure.com/doc/api/assignments.html
- Week 1 Discussion (Example): Assignment ID 9398144, Discussion ID 8424822
