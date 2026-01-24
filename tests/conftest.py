"""
Pytest fixtures for canvas_author tests.
"""

import pytest
from unittest.mock import Mock, MagicMock


class MockPage:
    """Mock Canvas page object."""

    def __init__(self, url="test-page", title="Test Page", body="<p>Test content</p>",
                 published=True, front_page=False):
        self.url = url
        self.title = title
        self.body = body
        self.published = published
        self.front_page = front_page
        self.created_at = "2024-01-01T00:00:00Z"
        self.updated_at = "2024-01-02T00:00:00Z"
        self.editing_roles = "teachers"

    def edit(self, wiki_page):
        """Mock edit method."""
        for key, value in wiki_page.items():
            setattr(self, key, value)
        return self

    def delete(self):
        """Mock delete method."""
        pass


class MockCourse:
    """Mock Canvas course object."""

    def __init__(self, course_id="12345"):
        self.id = course_id
        self.name = f"Test Course {course_id}"
        self.course_code = f"TC{course_id}"
        self._pages = {}

    def get_pages(self):
        """Return list of mock pages."""
        return list(self._pages.values())

    def get_page(self, page_url):
        """Get a specific page by URL."""
        from canvasapi.exceptions import ResourceDoesNotExist
        if page_url not in self._pages:
            raise ResourceDoesNotExist("Page not found")
        return self._pages[page_url]

    def create_page(self, wiki_page):
        """Create a new page."""
        page = MockPage(
            url=wiki_page.get("title", "new-page").lower().replace(" ", "-"),
            title=wiki_page.get("title", "New Page"),
            body=wiki_page.get("body", ""),
            published=wiki_page.get("published", True),
            front_page=wiki_page.get("front_page", False),
        )
        self._pages[page.url] = page
        return page

    def add_page(self, page):
        """Helper to add a page for testing."""
        self._pages[page.url] = page


class MockCanvasClient:
    """Mock Canvas client for testing."""

    def __init__(self):
        self.domain = "canvas.test.edu"
        self.token = "test-token"
        self._courses = {}

    def get_course(self, course_id):
        """Get a course by ID."""
        if course_id not in self._courses:
            self._courses[course_id] = MockCourse(course_id)
        return self._courses[course_id]

    def get_courses(self, enrollment_type="teacher", **kwargs):
        """Get courses for the current user."""
        return list(self._courses.values())


@pytest.fixture
def mock_canvas_client():
    """Provide a mock Canvas client."""
    return MockCanvasClient()


@pytest.fixture
def mock_course():
    """Provide a mock Canvas course."""
    return MockCourse("12345")


@pytest.fixture
def mock_page():
    """Provide a mock Canvas page."""
    return MockPage()


@pytest.fixture
def sample_markdown():
    """Sample markdown content for testing."""
    return """# Hello World

This is a **test** page.

- Item 1
- Item 2
- Item 3
"""


@pytest.fixture
def sample_html():
    """Sample HTML content for testing."""
    return """<h1>Hello World</h1>
<p>This is a <strong>test</strong> page.</p>
<ul>
<li>Item 1</li>
<li>Item 2</li>
<li>Item 3</li>
</ul>
"""


@pytest.fixture
def sample_frontmatter_content():
    """Sample markdown with frontmatter."""
    return """---
title: Test Page
url: test-page
published: true
updated_at: 2024-01-15T10:30:00Z
---

# Content

This is the page content.
"""
