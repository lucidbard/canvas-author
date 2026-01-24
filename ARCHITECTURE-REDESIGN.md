# Canvas Tools Architecture Redesign

## Current State Problems

1. **Monolithic Structure**: `~/canvas-author` contains both MCP server AND extension logic
2. **Mixed Concerns**: Authoring, grading, and redaction all in one package
3. **Tight Coupling**: VSCode extension directly depends on Python implementation
4. **No Reusability**: Other tools can't use grading features without pulling in authoring

## Proposed Architecture

### Package Structure

```
~/canvas-common/                    # Shared foundation library
├── canvas_common/
│   ├── client.py                   # Canvas API client wrapper
│   ├── exceptions.py               # Standard error types
│   ├── validation.py               # Link/URL validation
│   ├── utils.py                    # Shared utilities (slugify, etc.)
│   └── types.py                    # Common type definitions
├── pyproject.toml
└── README.md

~/canvas-author-mcp/                # Authoring MCP server
├── canvas_author_mcp/
│   ├── server.py                   # MCP server for authoring
│   ├── pages.py                    # Page CRUD + sync
│   ├── assignments.py              # Assignment CRUD + sync
│   ├── discussions.py              # Discussion CRUD + sync
│   ├── quizzes.py                  # Quiz CRUD + sync
│   ├── modules.py                  # Module management
│   ├── course.py                   # Course settings
│   ├── files.py                    # File management
│   └── frontmatter.py              # Markdown frontmatter parsing
├── pyproject.toml                  # Depends on canvas-common
└── README.md

~/canvas-grader-mcp/                # Grading MCP server
├── canvas_grader_mcp/
│   ├── server.py                   # MCP server for grading
│   ├── submissions.py              # Submission fetching + management
│   ├── rubrics.py                  # Rubric CRUD + sync
│   ├── drafts.py                   # Draft grade storage + versioning
│   ├── grading.py                  # Grade submission to Canvas
│   ├── redaction.py                # Auto-redaction (anonymization)
│   ├── conversations.py            # Student messaging
│   └── workflow.py                 # Review workflow (optional)
├── pyproject.toml                  # Depends on canvas-common
└── README.md

~/canvas-author-code/               # VSCode Extension (UI only)
├── src/
│   ├── extension.ts                # Extension entry point
│   ├── mcpClients.ts               # Connect to multiple MCP servers
│   ├── authoring/                  # Authoring UI panels
│   │   ├── pagesPanel.ts
│   │   ├── assignmentsPanel.ts
│   │   └── discussionsPanel.ts
│   ├── grading/                    # Grading UI panels
│   │   ├── submissionsPanel.ts
│   │   ├── rubricPanel.ts
│   │   └── gradingPanel.ts
│   └── common/
│       └── canvasMcpClient.ts      # Generic MCP client wrapper
├── package.json                    # MCP server configs
└── README.md
```

---

## Package Responsibilities

### 1. `canvas-common` (Foundation Library)

**Purpose**: Shared Canvas API access and utilities used by both authoring and grading

**Exports**:
- `CanvasClient` - Canvas API wrapper (singleton pattern)
- `get_canvas_client()` - Factory function
- Standard exceptions (CanvasMCPError, etc.)
- Validation utilities
- Type definitions (Course, Assignment, Submission, etc.)
- Common helpers (slugify, path utilities)

**Dependencies**:
- `canvasapi>=3.0.0`
- `requests>=2.x`
- `PyYAML>=6.0`

**No MCP Server**: Pure library, no server component

---

### 2. `canvas-author-mcp` (Authoring MCP Server)

**Purpose**: MCP server for Canvas content authoring (pages, assignments, courses)

**MCP Tools Provided**:

**Pages**:
- `list_pages(course_id)`
- `get_page(course_id, page_url, as_markdown)`
- `create_page(course_id, title, body, published)`
- `update_page(course_id, page_url, body, title, published)`
- `delete_page(course_id, page_url)`
- `pull_pages(course_id, output_dir, overwrite, download_images)`
- `push_pages(course_id, input_dir, create_missing, update_existing, upload_images)`
- `sync_status(course_id, local_dir)`

**Assignments**:
- `list_assignments(course_id)`
- `get_assignment(course_id, assignment_id)`
- `delete_assignment(course_id, assignment_id)`
- `pull_assignments(course_id, output_dir, overwrite)`
- `push_assignments(course_id, input_dir, create_missing, update_existing)`
- `assignment_sync_status(course_id, local_dir)`

**Discussions**:
- `list_discussions(course_id)`
- `get_discussion_posts(course_id, discussion_id)`
- `create_discussion(course_id, title, message, ...)`
- `update_discussion(course_id, discussion_id, ...)`
- `delete_discussion(course_id, discussion_id)`
- `pull_discussions(course_id, output_dir, overwrite)`
- `push_discussions(course_id, input_dir, ...)`

**Quizzes**:
- `list_quizzes(course_id)`
- `get_quiz(course_id, quiz_id)`
- `get_quiz_questions(course_id, quiz_id)`
- `pull_quizzes(course_id, output_dir, ...)`
- `push_quizzes(course_id, input_dir, ...)`

**Modules**:
- `pull_modules(course_id, output_dir)`
- `push_modules(course_id, input_dir, ...)`
- `module_sync_status(course_id, local_dir)`

**Course**:
- `list_courses(enrollment_state)`
- `init_course(course_id, directory)`
- `pull_course(course_id, directory)`
- `push_course(directory)`
- `course_status(course_id, directory)`

**Files**:
- `list_course_files(course_id)`
- `pull_course_files(course_id, output_dir, ...)`
- `download_pending_files(course_id, files_dir, file_ids)`

**Dependencies**:
- `canvas-common`
- `mcp>=1.0.0`
- `pandoc` (for markdown conversion)

**Configuration**: Single MCP server config in `package.json`

---

### 3. `canvas-grader-mcp` (Grading MCP Server)

**Purpose**: MCP server for grading workflows with built-in redaction

**MCP Tools Provided**:

**Submissions**:
- `pull_submissions(course_id, assignment_id, output_dir, include_attachments, anonymize)`
- `submission_status(course_id, assignment_id, local_dir)`
- `get_all_submissions_hierarchical(course_id, include_user, include_rubric, force_refresh)`
- `list_submissions(course_id, assignment_id, anonymize)` ← auto-redaction flag
- `get_submission(course_id, assignment_id, user_id, anonymize)` ← auto-redaction flag

**Rubrics**:
- `get_rubric(course_id, assignment_id)`
- `update_rubric(course_id, assignment_id, rubric_data)`
- `pull_rubrics(course_id, output_dir, overwrite)`
- `push_rubrics(course_id, input_dir, create_only)`
- `rubric_sync_status(course_id, local_dir)`

**Draft Grading** (AI-assisted grading workflow):
- `load_draft_grade(assignment_id, user_id)`
- `save_draft_grade(assignment_id, user_id, draft_data)`
- `add_draft_run(assignment_id, user_id, run_data, set_as_current)`
- `get_current_draft_run(assignment_id, user_id)`
- `set_current_draft_run(assignment_id, user_id, run_id)`
- `update_draft_run(assignment_id, user_id, run_id, updates)`
- `list_draft_grades(assignment_id)`
- `delete_draft_grade(assignment_id, user_id)`
- `set_official_rubric(assignment_id, user_id, rubric_data)`

**Grade Submission**:
- `update_grade(course_id, assignment_id, user_id, grade, comment)`

**Student Communication**:
- `message_non_submitters(course_id, assignment_id, subject, message, anonymize)`

**Review Workflow** (optional, for multi-agent grading):
- `create_agent_worktree(...)`
- `submit_style_review(...)`
- `submit_fact_check_review(...)`
- `submit_consistency_review(...)`
- `approve_and_merge_worktree(...)`

**Built-in Redaction Features**:
- **Default behavior**: `anonymize=true` on all submission/list tools
- Automatic ID mapping: `~/.canvas/data/[assignment]/id_mapping.json`
- Student name replacement: "Student 1", "Student 2", etc.
- Preserves Canvas user_id in mapping for deanonymization
- Warning messages when AI assistant requests identifiable data

**Dependencies**:
- `canvas-common`
- `mcp>=1.0.0`

**Configuration**: Single MCP server config in `package.json`

**Storage**:
- Draft grades: `~/.canvas/data/[assignment_id]/drafts/draft_grades_[user_id].json`
- ID mappings: `~/.canvas/data/[assignment_id]/id_mapping.json`

---

### 4. `canvas-author-code` (VSCode Extension - UI Only)

**Purpose**: VSCode extension providing UI for both authoring and grading

**Architecture**:
```typescript
// Connect to multiple MCP servers
const authoringMcp = new CanvasMcpClient('canvas-author-mcp');
const gradingMcp = new CanvasMcpClient('canvas-grader-mcp');

// Authoring panels use authoringMcp
class PagesPanel {
  async listPages(courseId: string) {
    return this.authoringMcp.callTool('list_pages', { course_id: courseId });
  }
}

// Grading panels use gradingMcp
class SubmissionsPanel {
  async listSubmissions(courseId: string, assignmentId: string) {
    // Auto-redaction enabled by default for AI privacy
    return this.gradingMcp.callTool('list_submissions', {
      course_id: courseId,
      assignment_id: assignmentId,
      anonymize: true  // Default to true for AI safety
    });
  }
}
```

**Package.json MCP Configuration**:
```json
{
  "contributes": {
    "configuration": {
      "mcpServers": {
        "canvas-author-mcp": {
          "command": "uvx",
          "args": ["--from", "canvas-author-mcp", "canvas-author-mcp"]
        },
        "canvas-grader-mcp": {
          "command": "uvx",
          "args": ["--from", "canvas-grader-mcp", "canvas-grader-mcp"]
        }
      }
    }
  }
}
```

**UI Components**:
- **Authoring Views**: Pages, Assignments, Discussions, Quizzes, Modules, Course Settings
- **Grading Views**: Submissions, Rubrics, Draft Grading, Grade Entry
- **Common**: Settings panel, course selector, error handling

**Dependencies**:
- VSCode API
- No direct Python dependencies (communicates via MCP only)

---

## Migration Strategy

### Phase 1: Extract Common Library (Week 1)

**Tasks**:
1. Create `~/canvas-common` package
2. Move `client.py`, `exceptions.py`, `validation.py` from canvas-author
3. Extract `_slugify()` and other utilities to `utils.py`
4. Define common types in `types.py`
5. Update imports in canvas-author to use canvas-common
6. Publish to PyPI or private package registry

**Testing**:
- Ensure canvas-author still works with new dependency
- Verify all utilities are accessible

---

### Phase 2: Create Grading Package (Week 2)

**Tasks**:
1. Create `~/canvas-grader-mcp` package structure
2. Copy grading modules from canvas-author:
   - `draft_storage.py` → `drafts.py`
   - `submission_sync.py` → `submissions.py`
   - `rubrics.py` → `rubrics.py`
   - `rubric_sync.py` → (merge into rubrics.py)
   - Relevant parts of `assignments.py` → `grading.py`
   - `conversations.py` → `conversations.py`
   - `workflow.py` → `workflow.py` (optional)
3. Create standalone MCP server in `server.py`
4. Build redaction features directly into `submissions.py`
5. Update imports to use `canvas-common`
6. Write tests for all grading tools
7. Publish package

**Redaction Implementation**:
```python
# Built into submissions.py
def list_submissions(course_id: str, assignment_id: str, anonymize: bool = True):
    """List submissions with optional auto-redaction.

    Args:
        anonymize: If True (default), redact student identities for AI privacy.
                  Stores mapping in ~/.canvas/data/[assignment]/id_mapping.json
    """
    submissions = _fetch_from_canvas(course_id, assignment_id)

    if anonymize:
        submissions, mapping = _redact_identities(submissions)
        _save_id_mapping(assignment_id, mapping)

    return submissions
```

**Testing**:
- Test MCP server standalone: `uvx canvas-grader-mcp`
- Verify all grading tools work
- Test redaction creates proper mappings
- Test draft storage versioning

---

### Phase 3: Create Authoring Package (Week 3)

**Tasks**:
1. Create `~/canvas-author-mcp` package structure
2. Move authoring modules from canvas-author:
   - `pages.py`
   - `assignments.py` (non-grading parts)
   - `discussions.py`
   - `quizzes.py`
   - `quiz_sync.py`
   - `modules.py`
   - `module_sync.py`
   - `course.py`
   - `files.py`
   - `frontmatter.py`
   - `pandoc.py`
3. Create standalone MCP server in `server.py`
4. Update imports to use `canvas-common`
5. Write tests
6. Publish package

**Testing**:
- Test MCP server standalone: `uvx canvas-author-mcp`
- Verify all authoring tools work
- Test page/assignment sync workflows

---

### Phase 4: Update VSCode Extension (Week 4)

**Tasks**:
1. Update `package.json` with both MCP server configs
2. Create `mcpClients.ts` to manage multiple connections
3. Update panels to use appropriate MCP client
4. Remove all Python code from extension (if any)
5. Update settings UI to configure both servers
6. Add toggle for redaction in grading UI
7. Test full workflow end-to-end

**Extension Changes**:
```typescript
// Before (single MCP)
const mcp = getMcpClient();
await mcp.callTool('list_pages', { course_id });

// After (multiple MCPs)
const authoringMcp = getMcpClient('canvas-author-mcp');
const gradingMcp = getMcpClient('canvas-grader-mcp');

await authoringMcp.callTool('list_pages', { course_id });
await gradingMcp.callTool('list_submissions', {
  course_id,
  assignment_id,
  anonymize: true  // Configurable in settings
});
```

**Testing**:
- Test authoring workflows (pages, assignments, etc.)
- Test grading workflows (submissions, rubrics, drafts)
- Test redaction toggle
- Test error handling for both servers

---

### Phase 5: Deprecate Old Package (Week 5)

**Tasks**:
1. Mark `~/canvas-author` as deprecated
2. Update documentation to point to new packages
3. Archive old repository
4. Maintain for 1-2 months for backward compatibility
5. Add migration guide

---

## Configuration Management

### User Configuration (~/.canvas/config.yaml)

```yaml
# Shared by all packages
canvas:
  domain: "canvas.instructure.com"
  token: "your-api-token"  # Or use environment variable

# Package-specific settings
authoring:
  default_output_dir: "~/canvas-course"
  auto_upload_images: true

grading:
  default_anonymize: true  # Auto-redact by default
  draft_storage_path: "~/.canvas/data"
  ai_privacy_mode: true  # Warn on non-anonymized requests
```

### Environment Variables

```bash
CANVAS_API_TOKEN=your-token
CANVAS_DOMAIN=canvas.instructure.com
CANVAS_GRADING_ANONYMIZE=true  # Default redaction setting
```

---

## Benefits of This Architecture

### 1. **Separation of Concerns**
- Authoring and grading are independent
- Can update grading without affecting authoring
- Each package has clear responsibility

### 2. **Reusability**
- Other tools can use `canvas-grader-mcp` without authoring features
- Command-line grading tools can use grading MCP directly
- Web apps can connect to MCP servers

### 3. **Built-in Privacy (Auto-Redaction)**
- Redaction is default behavior in grading package
- No need to remember to anonymize - it's automatic
- ID mapping is transparent to end users

### 4. **Easier Maintenance**
- Smaller codebases per package
- Clear dependency graph
- Independent versioning

### 5. **Better Testing**
- Each package can be tested independently
- Mock dependencies easily
- Integration tests are clearer

### 6. **Scalability**
- Can add more packages (e.g., analytics, reports)
- Each MCP server can scale independently
- Extension just orchestrates, doesn't implement

---

## Example Usage Scenarios

### Scenario 1: Grading with CLI

```bash
# Use grading MCP directly without VSCode
uvx canvas-grader-mcp

# In Python/Node.js script
from mcp import Client
grading = Client('canvas-grader-mcp')

# Auto-redaction enabled by default
submissions = grading.call_tool('list_submissions', {
    'course_id': '12345',
    'assignment_id': '67890',
    'anonymize': True  # Default
})

# Submissions have "Student 1", "Student 2" instead of real names
for sub in submissions:
    print(f"{sub['user_name']}: {sub['score']}")
```

### Scenario 2: Authoring from VSCode

```typescript
// Extension automatically connects to canvas-author-mcp
const pages = await vscode.commands.executeCommand(
  'canvas-author.listPages',
  courseId
);

// UI displays pages
this.webview.postMessage({ type: 'pages', data: pages });
```

### Scenario 3: Grading from VSCode with Privacy

```typescript
// Extension connects to canvas-grader-mcp
const submissions = await vscode.commands.executeCommand(
  'canvas-grader.listSubmissions',
  courseId,
  assignmentId,
  { anonymize: true }  // Enforced for AI privacy
);

// UI shows "Student 1", "Student 2"
// ID mapping stored automatically for deanonymization
```

---

## File Layout After Migration

```
~/canvas-common/
├── canvas_common/
│   ├── __init__.py
│   ├── client.py          (296 lines from canvas-author)
│   ├── exceptions.py      (69 lines from canvas-author)
│   ├── validation.py      (148 lines from canvas-author)
│   ├── utils.py           (NEW - extracted utilities)
│   └── types.py           (NEW - type definitions)
├── tests/
├── pyproject.toml
└── README.md

~/canvas-author-mcp/
├── canvas_author_mcp/
│   ├── __init__.py
│   ├── server.py          (MCP server entry point)
│   ├── pages.py           (238 lines from canvas-author)
│   ├── assignments.py     (~200 lines, grading parts removed)
│   ├── discussions.py     (357 lines from canvas-author)
│   ├── quizzes.py         (162 lines from canvas-author)
│   ├── quiz_sync.py       (347 lines from canvas-author)
│   ├── modules.py         (279 lines from canvas-author)
│   ├── module_sync.py     (235 lines from canvas-author)
│   ├── course.py          (268 lines from canvas-author)
│   ├── files.py           (237 lines from canvas-author)
│   ├── frontmatter.py     (84 lines from canvas-author)
│   └── pandoc.py          (80 lines from canvas-author)
├── tests/
├── pyproject.toml
└── README.md

~/canvas-grader-mcp/
├── canvas_grader_mcp/
│   ├── __init__.py
│   ├── server.py          (MCP server entry point)
│   ├── submissions.py     (517 lines from canvas-author)
│   ├── rubrics.py         (313 lines from canvas-author)
│   ├── drafts.py          (364 lines from canvas-author/draft_storage)
│   ├── grading.py         (~200 lines, grade submission logic)
│   ├── redaction.py       (NEW - auto-redaction implementation)
│   ├── conversations.py   (100+ lines from canvas-author)
│   └── workflow.py        (OPTIONAL - review workflows)
├── tests/
├── pyproject.toml
└── README.md

~/canvas-author-code/  (VSCode Extension)
├── src/
│   ├── extension.ts
│   ├── mcpClients.ts      (NEW - multiple MCP management)
│   ├── authoring/
│   │   ├── pagesPanel.ts
│   │   ├── assignmentsPanel.ts
│   │   └── discussionsPanel.ts
│   ├── grading/
│   │   ├── submissionsPanel.ts  (uses gradingMcp)
│   │   ├── rubricPanel.ts       (uses gradingMcp)
│   │   └── gradingPanel.ts      (uses gradingMcp)
│   └── common/
│       └── canvasMcpClient.ts
├── package.json          (Updated with both MCP configs)
└── README.md

# Deprecated (kept for 1-2 months)
~/canvas-author/          (Mark as deprecated, archive)
```

---

## Summary

This architecture achieves:
✅ Clean separation: Authoring vs Grading vs Common
✅ VSCode extension is pure UI (no business logic)
✅ Auto-redaction built into grading package (privacy by default)
✅ Each package is independently usable via MCP
✅ Shared foundation prevents code duplication
✅ Clear migration path with backward compatibility

**Next Steps**: Review this plan and approve phases to begin implementation.
