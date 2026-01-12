# Canvas Announcements Feature Proposal for canvas-author

## Overview

Add announcement management to canvas-author to enable version control, local editing, and programmatic posting of course announcements.

## Why This Feature Matters

**Current Pain Points:**
1. Announcements are only editable through Canvas web interface
2. No version history for announcements
3. Can't preview announcement formatting locally
4. No way to template recurring announcement patterns
5. Can't sync announcements between courses
6. No local backup of course communications

**Benefits:**
1. **Version Control**: Track announcement history in Git
2. **Local Editing**: Write announcements in Markdown with your preferred editor
3. **Templates**: Create reusable announcement templates
4. **Consistency**: Ensure formatting/style across all announcements
5. **Backup**: Local copies of all course communications
6. **Automation**: Programmatically post announcements (e.g., weekly reminders)

## Canvas API Details

Announcements in Canvas are **discussion topics** with `is_announcement: true`.

### API Endpoints

**List Announcements:**
```
GET /api/v1/courses/{course_id}/discussion_topics?only_announcements=true
```

**Get Specific Announcement:**
```
GET /api/v1/courses/{course_id}/discussion_topics/{topic_id}
```

**Create Announcement:**
```
POST /api/v1/courses/{course_id}/discussion_topics
Body: {
  "title": "Announcement Title",
  "message": "<html content>",
  "is_announcement": true,
  "published": true,
  "delayed_post_at": "2026-01-15T09:00:00Z"  // Optional: schedule for later
}
```

**Update Announcement:**
```
PUT /api/v1/courses/{course_id}/discussion_topics/{topic_id}
```

**Delete Announcement:**
```
DELETE /api/v1/courses/{course_id}/discussion_topics/{topic_id}
```

## Proposed Implementation

### 1. Local File Format

**announcements/2026-01-12-week-1-welcome.announcement.md**

```markdown
---
announcement_id: 8424900
title: Week 1 - Welcome to DIG4503C
posted_at: "2026-01-12T13:00:00Z"
delayed_post_at: null
published: true
---

Good afternoon!

**IMPORTANT:** I had a few hiccups this morning with Canvas...

[rest of content in markdown]
```

**Key Features:**
- Markdown content (converted to HTML for Canvas)
- Frontmatter with metadata
- Filename includes date for sorting
- `announcement_id` links to Canvas (null if not yet posted)
- `delayed_post_at` for scheduled announcements

### 2. CLI Commands

```bash
# Pull all announcements from Canvas
python -m canvas_author.announcement_sync pull 1503378 ./announcements

# Push new/updated announcements to Canvas
python -m canvas_author.announcement_sync push 1503378 ./announcements

# Create announcement from template
python -m canvas_author.announcement_sync create 1503378 --title "Week 2 Reminder" --template weekly-reminder

# Schedule announcement for later
python -m canvas_author.announcement_sync schedule 1503378 ./announcements/week-2-reminder.md --post-at "2026-01-19T09:00:00Z"

# List all announcements
python -m canvas_author.announcement_sync list 1503378

# Delete announcement (local and/or Canvas)
python -m canvas_author.announcement_sync delete 1503378 8424900
```

### 3. MCP Tools

Add to `canvas_author/server.py`:

```python
@server.call_tool()
async def list_announcements(
    course_id: str,
    per_page: int = 10
) -> list[types.TextContent]:
    """List course announcements with titles, dates, and IDs"""

@server.call_tool()
async def get_announcement(
    course_id: str,
    announcement_id: str
) -> list[types.TextContent]:
    """Get full announcement content by ID"""

@server.call_tool()
async def create_announcement(
    course_id: str,
    title: str,
    message: str,
    published: bool = True,
    delayed_post_at: Optional[str] = None
) -> list[types.TextContent]:
    """Create and optionally schedule a new announcement"""

@server.call_tool()
async def update_announcement(
    course_id: str,
    announcement_id: str,
    title: Optional[str] = None,
    message: Optional[str] = None
) -> list[types.TextContent]:
    """Update existing announcement"""

@server.call_tool()
async def pull_announcements(
    course_id: str,
    output_dir: str,
    limit: int = 50
) -> list[types.TextContent]:
    """Download announcements to local markdown files"""

@server.call_tool()
async def push_announcements(
    course_id: str,
    input_dir: str,
    create_missing: bool = True,
    update_existing: bool = True
) -> list[types.TextContent]:
    """Upload local announcements to Canvas"""
```

### 4. File Structure

```
announcements/
├── 2026-01-12-week-1-welcome.announcement.md
├── 2026-01-15-discussion-reminder.announcement.md
├── 2026-01-19-week-2-overview.announcement.md
├── templates/
│   ├── weekly-overview.md
│   ├── assignment-reminder.md
│   └── office-hours-change.md
└── .announcement-config.yaml
```

**.announcement-config.yaml:**
```yaml
course_id: 1503378
default_post_time: "09:00:00"  # Default time for scheduled posts
auto_publish: false  # Require explicit publish flag
signature: |
  — John
  DIG4503C Instructor
```

### 5. Template System

**templates/weekly-overview.md:**
```markdown
---
title: Week {week_number} - {topic}
---

Good {time_of_day}!

Week {week_number} content is now available.

**This week's focus:** {topic}

**Key Dates:**
- {assignment_1}: Due {due_date_1}
- {assignment_2}: Due {due_date_2}

**Quick Links:**
- [Week {week_number} Overview](link)
- [Assignment Submission](link)

{custom_message}

{signature}
```

**Usage:**
```bash
python -m canvas_author.announcement_sync create 1503378 \
  --template weekly-overview \
  --vars week_number=2 topic="The 2026 Development Landscape" \
  --schedule "2026-01-19T09:00:00Z"
```

## Implementation Phases

### Phase 1: Core Functionality
- [ ] `pull_announcements()` - Download to local files
- [ ] `create_announcement()` - Post new announcements
- [ ] `update_announcement()` - Modify existing
- [ ] Markdown ↔ HTML conversion (using pandoc)
- [ ] Basic MCP tools

### Phase 2: Advanced Features
- [ ] `push_announcements()` - Bulk sync
- [ ] Scheduled announcements (`delayed_post_at`)
- [ ] Template system
- [ ] Announcement sync status checking
- [ ] CLI commands

### Phase 3: Polish
- [ ] Announcement preview (local HTML rendering)
- [ ] Duplicate detection
- [ ] Announcement analytics (view counts, if available via API)
- [ ] Announcement categories/tags

## Similar Patterns in canvas-author

This follows the same pattern as existing sync modules:

- **Pages**: `page_sync.py` - Already implemented ✅
- **Assignments**: `assignment_sync.py` - Already implemented ✅
- **Quizzes**: `quiz_sync.py` - Already implemented ✅
- **Discussions**: Proposed in issue #1 🚧
- **Announcements**: This proposal 📝

## Technical Considerations

### HTML Conversion
Use pandoc (already used for pages) to convert Markdown ↔ HTML:

```python
import pypandoc

def markdown_to_html(md_content: str) -> str:
    """Convert markdown to Canvas-compatible HTML"""
    return pypandoc.convert_text(
        md_content,
        'html',
        format='markdown',
        extra_args=['--wrap=none']
    )

def html_to_markdown(html_content: str) -> str:
    """Convert Canvas HTML to markdown"""
    return pypandoc.convert_text(
        html_content,
        'markdown',
        format='html'
    )
```

### Scheduled Announcements

Canvas supports `delayed_post_at` for scheduling:

```python
{
  "title": "Week 2 Reminder",
  "message": "<p>Don't forget...</p>",
  "is_announcement": true,
  "published": false,  # Will auto-publish at delayed_post_at
  "delayed_post_at": "2026-01-19T09:00:00Z"
}
```

### Read-Only vs Editable

Some users may want announcements to be:
1. **Read-only local copies** (pull only, never push)
2. **Fully bidirectional** (pull and push)

Add config option:
```yaml
sync_mode: "pull_only"  # or "bidirectional"
```

## Use Cases

### Use Case 1: Weekly Course Updates
```bash
# Monday morning: Create week 2 announcement from template
canvas-author announcement create 1503378 \
  --template weekly-overview \
  --title "Week 2 - The 2026 Development Landscape" \
  --schedule "2026-01-19T09:00:00Z"

# Edit in VS Code if needed
# Push to Canvas (will schedule for 9 AM Monday)
canvas-author announcement push 1503378 ./announcements
```

### Use Case 2: Emergency Announcement
```bash
# Quick announcement about office hours change
canvas-author announcement create 1503378 \
  --title "Office Hours Canceled Today" \
  --message "Sorry, office hours canceled due to illness. See you Wednesday!" \
  --publish
```

### Use Case 3: Course Archive
```bash
# End of semester: Pull all announcements for record-keeping
canvas-author announcement pull 1503378 ./archives/spring-2026/announcements

# Commit to Git for permanent record
git add archives/spring-2026/announcements
git commit -m "Archive Spring 2026 announcements"
```

### Use Case 4: Multi-Course Consistency
```bash
# Same announcement to multiple courses
for course_id in 1503378 1503379 1503380; do
  canvas-author announcement create $course_id \
    --file announcements/spring-break-reminder.md
done
```

## Testing Strategy

1. **Unit Tests**: Test markdown/HTML conversion
2. **Integration Tests**: Test Canvas API calls with test course
3. **E2E Tests**: Full workflow (create → pull → modify → push)
4. **Template Tests**: Verify variable substitution works correctly

## Documentation Needs

1. **README section**: Announcement management overview
2. **API docs**: All MCP tool signatures
3. **CLI reference**: Command examples
4. **Workflow guide**: Common announcement workflows
5. **Template guide**: Creating custom templates

## Open Questions

1. **Attachment support?** Canvas allows file attachments on announcements
2. **Comments?** Announcements can allow comments - sync those too?
3. **Notification settings?** Canvas can notify students - expose this?
4. **Announcement expiration?** Some LMS have announcement end dates

## Recommendation

**Start with Phase 1** (core functionality) to validate the approach:
1. Implement `pull_announcements()` and `create_announcement()`
2. Add MCP tools
3. Test with real course announcements
4. Gather feedback before building templates/scheduling

**Estimated effort:**
- Phase 1: 4-6 hours
- Phase 2: 6-8 hours
- Phase 3: 4-6 hours
- **Total**: ~14-20 hours for complete implementation

## Next Steps

1. Create GitHub issue for announcement feature
2. Implement Phase 1 (pull + create)
3. Use it for 2-3 weeks to validate approach
4. Add scheduling and templates based on real needs
5. Document workflows

---

**Would this solve your use case?** Having announcements in version control would let you:
- Track all course communications over time
- Reuse effective announcements across semesters
- Template common announcement types
- Never lose an announcement due to Canvas issues
- Collaborate on announcements with TAs (via Git)
