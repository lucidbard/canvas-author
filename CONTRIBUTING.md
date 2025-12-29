# Contributing to Canvas MCP

Thank you for your interest in contributing to Canvas MCP! This document provides guidelines and instructions for contributing.

## Development Setup

### Prerequisites

- Python 3.10 or higher
- pandoc (for markdown/HTML conversion)
- A Canvas LMS account with API access

### Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/canvas-mcp.git
   cd canvas-mcp
   ```

2. Create a virtual environment:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

3. Install development dependencies:
   ```bash
   pip install -e ".[dev]"
   ```

4. Install pandoc:
   ```bash
   # Ubuntu/Debian
   sudo apt install pandoc

   # macOS
   brew install pandoc

   # Windows
   choco install pandoc
   ```

5. Set up environment variables:
   ```bash
   cp .env.example .env
   # Edit .env with your Canvas credentials
   ```

## Running Tests

### Unit Tests

Run the test suite with pytest:

```bash
pytest tests/ -v
```

Run with coverage:

```bash
pytest tests/ --cov=canvas_mcp --cov-report=html
```

### End-to-End Tests

E2E tests require a real Canvas instance. Set the following environment variables:

```bash
export CANVAS_DOMAIN=your-canvas.instructure.com
export CANVAS_API_TOKEN=your-token
export CANVAS_TEST_COURSE_ID=123456  # A course you can modify
```

Then run:

```bash
pytest tests/e2e/ -v --run-e2e
```

## Code Style

This project follows these conventions:

- **Python**: PEP 8 with line length of 100 characters
- **Docstrings**: Google style docstrings
- **Type Hints**: Use type hints for all public functions
- **Imports**: Use absolute imports, group by standard library, third-party, local

### Example Function

```python
def example_function(
    param1: str,
    param2: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Brief description of function.

    Longer description if needed.

    Args:
        param1: Description of param1
        param2: Description of param2

    Returns:
        Description of return value

    Raises:
        ValueError: When something is wrong
    """
    pass
```

## Pull Request Process

1. **Fork** the repository and create your branch from `main`
2. **Write tests** for any new functionality
3. **Update documentation** if you're changing behavior
4. **Run tests** and ensure they pass
5. **Submit** your pull request

### PR Checklist

- [ ] Tests pass locally (`pytest tests/`)
- [ ] Code follows project style conventions
- [ ] Docstrings are complete for new functions
- [ ] CHANGELOG.md is updated (for user-facing changes)
- [ ] README.md is updated if needed

## Reporting Issues

When reporting issues, please include:

1. **Python version** (`python --version`)
2. **Package version** (`pip show canvas-mcp`)
3. **Operating system**
4. **Steps to reproduce** the issue
5. **Expected behavior** vs **actual behavior**
6. **Error messages** and tracebacks (if applicable)

## Feature Requests

Feature requests are welcome! Please:

1. Check if the feature already exists or is planned
2. Open an issue describing the feature
3. Explain the use case and why it would be valuable
4. Be open to discussion about implementation approaches

## Project Structure

```
canvas-mcp/
├── canvas_mcp/           # Main package
│   ├── __init__.py       # Package exports
│   ├── client.py         # Canvas API client
│   ├── pages.py          # Wiki page operations
│   ├── assignments.py    # Assignment operations
│   ├── discussions.py    # Discussion operations
│   ├── rubrics.py        # Rubric operations
│   ├── pandoc.py         # Markdown/HTML conversion
│   ├── styling.py        # CSS inlining for Canvas
│   ├── frontmatter.py    # YAML frontmatter parsing
│   ├── sync.py           # Two-way sync logic
│   ├── cli.py            # Command-line interface
│   ├── server.py         # MCP server
│   └── exceptions.py     # Custom exceptions
├── tests/                # Test files
├── scripts/              # Utility scripts
└── .github/workflows/    # GitHub Actions
```

## Questions?

If you have questions about contributing, feel free to:

1. Open an issue with your question
2. Check existing issues and discussions

Thank you for contributing!
