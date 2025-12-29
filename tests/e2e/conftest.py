"""
E2E Test Fixtures for Canvas MCP

Provides fixtures for end-to-end testing against a real Canvas instance.
Requires environment variables to be set before running.
"""

import os
import pytest
import tempfile
import shutil
import time
from pathlib import Path
from typing import Generator, Dict, Any
from datetime import datetime

# Mark all tests in this module as e2e
pytestmark = pytest.mark.e2e


def pytest_configure(config):
    """Register e2e marker and check for required environment variables."""
    config.addinivalue_line("markers", "e2e: End-to-end tests against real Canvas instance")


@pytest.fixture(scope="session")
def e2e_config() -> Dict[str, Any]:
    """
    Provide E2E test configuration from environment variables.

    Required environment variables:
    - E2E_CANVAS_API_TOKEN: Canvas API token
    - E2E_CANVAS_DOMAIN: Canvas domain (e.g., canvas.instructure.com)
    - E2E_CANVAS_COURSE_ID: Course ID for testing

    Optional:
    - E2E_CANVAS_ASSIGNMENT_WITH_RUBRIC: Assignment ID with rubric
    - E2E_CANVAS_DISCUSSION_ID: Discussion topic ID
    - E2E_CANVAS_SKIP_CLEANUP: Set to 'true' to skip cleanup (for debugging)
    """
    config = {
        "domain": os.getenv("E2E_CANVAS_DOMAIN"),
        "token": os.getenv("E2E_CANVAS_API_TOKEN"),
        "course_id": os.getenv("E2E_CANVAS_COURSE_ID"),
        "assignment_with_rubric": os.getenv("E2E_CANVAS_ASSIGNMENT_WITH_RUBRIC"),
        "discussion_id": os.getenv("E2E_CANVAS_DISCUSSION_ID"),
        "skip_cleanup": os.getenv("E2E_CANVAS_SKIP_CLEANUP", "false").lower() == "true",
    }

    # Check required variables
    missing = [k for k in ["domain", "token", "course_id"] if not config[k]]
    if missing:
        pytest.skip(
            f"Missing required E2E environment variables: {', '.join(f'E2E_CANVAS_{k.upper()}' for k in missing)}. "
            "Set them before running E2E tests."
        )

    return config


@pytest.fixture(scope="session")
def canvas_client(e2e_config: Dict[str, Any]):
    """Provide a real Canvas client for E2E tests."""
    from canvas_mcp.client import CanvasClient

    client = CanvasClient(
        domain=e2e_config["domain"],
        token=e2e_config["token"]
    )
    # Trigger initialization to validate credentials
    try:
        _ = client.client
    except Exception as e:
        pytest.skip(f"Failed to connect to Canvas: {e}")

    return client


@pytest.fixture(scope="session")
def test_course_id(e2e_config: Dict[str, Any]) -> str:
    """Provide the test course ID."""
    return e2e_config["course_id"]


@pytest.fixture(scope="function")
def temp_workspace() -> Generator[Path, None, None]:
    """Provide a temporary directory for file operations."""
    temp_dir = Path(tempfile.mkdtemp(prefix="canvas_e2e_"))
    try:
        yield temp_dir
    finally:
        if temp_dir.exists():
            shutil.rmtree(temp_dir)


@pytest.fixture(scope="function")
def test_page_name() -> str:
    """Generate a unique test page name with timestamp."""
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    return f"e2e-test-page-{timestamp}"


@pytest.fixture(scope="function")
def cleanup_test_pages(canvas_client, test_course_id: str, e2e_config: Dict[str, Any]):
    """
    Cleanup fixture that removes test pages before and after test.

    All pages with URLs starting with 'e2e-test-' are cleaned up.
    """
    from canvas_mcp.pages import list_pages, delete_page

    def _cleanup():
        if e2e_config["skip_cleanup"]:
            return

        try:
            pages = list_pages(test_course_id, canvas_client)
            for page in pages:
                if page["url"].startswith("e2e-test-"):
                    try:
                        delete_page(test_course_id, page["url"], canvas_client)
                        print(f"Cleaned up test page: {page['url']}")
                    except Exception as e:
                        print(f"Failed to cleanup page {page['url']}: {e}")
        except Exception as e:
            print(f"Failed to list pages for cleanup: {e}")

    # Cleanup before test
    _cleanup()

    # Run test
    yield

    # Cleanup after test
    _cleanup()


@pytest.fixture
def sample_markdown() -> str:
    """Provide sample markdown content for testing."""
    return """# Test Page

This is a **test** page created by E2E tests.

## Features

- Bullet points
- **Bold text**
- *Italic text*
- [Links](https://example.com)

## Code Example

```python
def hello_world():
    print("Hello, Canvas!")
```

## Table

| Column 1 | Column 2 |
|----------|----------|
| Data 1   | Data 2   |
| Data 3   | Data 4   |
"""


@pytest.fixture
def complex_markdown() -> str:
    """Provide complex markdown for edge case testing."""
    return """# Complex Test Page

## Nested Lists

1. First item
   - Nested bullet
   - Another nested
2. Second item

## Special Characters

Testing: <>&"'

## Blockquote

> This is a quote
> spanning multiple lines
> with **formatting**
"""


def wait_for_canvas_propagation(seconds: float = 1.0):
    """
    Wait for Canvas to propagate changes.

    Sometimes Canvas needs time to propagate updates.
    """
    time.sleep(seconds)
