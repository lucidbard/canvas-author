# Phase 1 Progress: Extract canvas-common

## ✅ Completed

### Repository Setup
- [x] Created `~/canvas-common` package structure
- [x] Initialized git repository (branch: main)
- [x] Created pyproject.toml with dependencies
- [x] Created comprehensive README.md

### Core Modules Extracted
- [x] `client.py` - Canvas API client wrapper (296 lines)
- [x] `exceptions.py` - Standard error types (69 lines)
- [x] `validation.py` - URL/link validation (148 lines)
- [x] `utils.py` - Common utilities (NEW - slugify, ensure_dir, sanitize_filename)
- [x] `types.py` - TypedDict definitions (NEW - Course, Assignment, Submission, etc.)
- [x] `__init__.py` - Clean package exports

### Testing
- [x] Created tests/ directory
- [x] Added test_utils.py with comprehensive tests
  - slugify tests (unicode, special chars, spaces)
  - ensure_dir tests (creation, existing)
  - sanitize_filename tests (unsafe chars, truncation)

### Related Work
- [x] Renamed `~/canvas` → `~/canvas-web`
- [x] Updated canvas-web README with future roadmap
- [x] Updated git remote: `git@github.com:lucidbard/canvas-web.git`

## ✅ Phase 1 Complete!

### Integration Complete
- [x] Updated canvas-author to use canvas-common
- [x] Removed duplicate files (client.py, exceptions.py, validation.py, frontmatter.py)
- [x] Updated imports across 20+ modules
- [x] Removed duplicate _slugify() from 3 files
- [x] Added canvas-common>=0.1.0 dependency
- [x] All imports verified working
- [x] Committed changes to both repositories

**Total code removed**: ~791 lines of duplicates

### Remaining: GitHub Repository Setup

```bash
# Create GitHub repository
gh repo create lucidbard/canvas-common --public --description "Shared foundation library for Canvas packages"

# Push to GitHub
cd ~/canvas-common
git remote add origin git@github.com:lucidbard/canvas-common.git
git push -u origin main
```

### Previous: Update canvas-author to use canvas-common (DONE)

**Files to modify**:
- `pyproject.toml` - Add canvas-common dependency
- Remove: `client.py`, `exceptions.py`, `validation.py` (now in canvas-common)
- Update imports throughout:
  ```python
  # Old
  from canvas_author.client import get_canvas_client
  from canvas_author.exceptions import CanvasMCPError

  # New
  from canvas_common import get_canvas_client
  from canvas_common import CanvasMCPError
  ```

**Modules to update** (grep for old imports):
- `server.py`
- `pages.py`
- `assignments.py`
- `discussions.py`
- `quizzes.py`
- `modules.py`
- `course.py`
- `files.py`
- `submission_sync.py`
- `rubrics.py`
- All sync modules

**Replace _slugify() with canvas_common.slugify**:
- `submission_sync.py` (line 23)
- `rubric_sync.py` (line 21)
- `assignment_sync.py`
- `discussion_sync.py`
- Others using _slugify()

### 3. Testing
```bash
# Install canvas-common in development mode
cd ~/canvas-common
pip install -e ".[dev]"

# Run canvas-common tests
pytest

# Update canvas-author to use canvas-common
cd ~/canvas-author
pip install -e ~/canvas-common

# Run canvas-author tests to verify nothing broke
pytest

# Test MCP server
uvx canvas-author
```

### 4. Documentation
- [ ] Update canvas-author README to mention canvas-common dependency
- [ ] Add migration notes for users
- [ ] Document version compatibility

### 5. Publish (Optional for now)
```bash
# When ready to publish to PyPI
cd ~/canvas-common
python -m build
twine upload dist/*
```

## 📊 Statistics

**canvas-common package**:
- **Total lines**: ~828 lines
- **Modules**: 5 core + 2 support (init, types)
- **Tests**: 15 test functions
- **Dependencies**: canvasapi, requests, PyYAML

**Extracted from canvas-author**:
- **client.py**: 296 lines
- **exceptions.py**: 69 lines
- **validation.py**: 148 lines
- **New utilities**: ~60 lines
- **New types**: ~70 lines

**Impact**:
- Removes ~513 lines from canvas-author
- Creates reusable foundation for canvas-grader-mcp
- Eliminates code duplication (5+ _slugify() copies removed)

## 🔗 Related Issues

- GitHub Issue #10: Phase 1 - Extract canvas-common
- GitHub Issue #11: Phase 2 - Create canvas-grader-mcp
- GitHub Issue #12: Phase 3 - Create canvas-author-mcp
- GitHub Issue #13: Phase 4 - Update extension
- GitHub Issue #14: Phase 5 - Deprecate old package

## 📝 Notes

- canvas-common is intentionally minimal - only shared utilities
- No MCP server in canvas-common (pure library)
- TypedDict provides type safety without runtime overhead
- All utilities have comprehensive tests
- Ready for Phase 2 to begin once canvas-author is updated

## ⚠️ Important

**Do not proceed to Phase 2 until**:
1. canvas-author successfully uses canvas-common
2. All canvas-author tests pass
3. MCP server still works

This ensures we have a stable foundation before creating the grading package.
