"""
Tests for the frontmatter module.
"""

import pytest
from canvas_mcp.frontmatter import (
    parse_frontmatter,
    generate_frontmatter,
    create_page_frontmatter,
)


class TestParseFrontmatter:
    """Tests for parse_frontmatter function."""

    def test_parse_valid_frontmatter(self):
        """Test parsing valid YAML frontmatter."""
        content = """---
title: Test Page
url: test-page
published: true
---

# Content here
"""
        metadata, body = parse_frontmatter(content)

        assert metadata["title"] == "Test Page"
        assert metadata["url"] == "test-page"
        assert metadata["published"] is True
        assert body.strip() == "# Content here"

    def test_parse_no_frontmatter(self):
        """Test parsing content without frontmatter."""
        content = "# Just a heading\n\nSome content."

        metadata, body = parse_frontmatter(content)

        assert metadata == {}
        assert body == content

    def test_parse_empty_content(self):
        """Test parsing empty content."""
        metadata, body = parse_frontmatter("")

        assert metadata == {}
        assert body == ""

    def test_parse_frontmatter_with_special_chars(self):
        """Test parsing frontmatter with special characters."""
        content = """---
title: Page with colon in value
description: Has single quotes here
---

Content
"""
        metadata, body = parse_frontmatter(content)

        assert metadata["title"] == "Page with colon in value"
        assert "Content" in body

    def test_parse_frontmatter_with_numeric_values(self):
        """Test parsing frontmatter with numeric values."""
        content = """---
title: Test
points: 100
weight: 0.5
---

Body
"""
        metadata, body = parse_frontmatter(content)

        assert metadata["points"] == 100
        assert metadata["weight"] == 0.5

    def test_body_content_preserved(self):
        """Test that body content with special formatting is preserved."""
        content = """---
title: Test
---

# Heading

```python
def hello():
    print("world")
```

| Column | Value |
|--------|-------|
| A      | 1     |
"""
        metadata, body = parse_frontmatter(content)

        assert "```python" in body
        assert "def hello():" in body
        assert "| Column |" in body


class TestGenerateFrontmatter:
    """Tests for generate_frontmatter function."""

    def test_generate_simple_frontmatter(self):
        """Test generating simple frontmatter."""
        metadata = {
            "title": "My Page",
            "url": "my-page",
        }

        result = generate_frontmatter(metadata)

        assert result.startswith("---\n")
        assert result.endswith("---\n")
        assert "title: My Page" in result
        assert "url: my-page" in result

    def test_generate_frontmatter_with_boolean(self):
        """Test generating frontmatter with boolean values."""
        metadata = {
            "title": "Test",
            "published": True,
            "front_page": False,
        }

        result = generate_frontmatter(metadata)

        assert "published: true" in result
        assert "front_page: false" in result

    def test_generate_empty_frontmatter(self):
        """Test generating frontmatter with empty metadata."""
        result = generate_frontmatter({})

        assert result == "---\n---\n"


class TestCreatePageFrontmatter:
    """Tests for create_page_frontmatter function."""

    def test_create_page_frontmatter_minimal(self):
        """Test creating page frontmatter with minimal args."""
        result = create_page_frontmatter(
            title="Test Page",
            url="test-page",
            course_id="12345",
        )

        assert "title: Test Page" in result
        assert "url: test-page" in result
        assert "course_id: 12345" in result

    def test_create_page_frontmatter_full(self):
        """Test creating page frontmatter with all args."""
        result = create_page_frontmatter(
            title="Full Page",
            url="full-page",
            course_id="12345",
            published=True,
            front_page=True,
            updated_at="2024-01-15T10:30:00Z",
        )

        assert "title: Full Page" in result
        assert "published: true" in result
        assert "front_page: true" in result
        assert "updated_at:" in result


class TestRoundTrip:
    """Tests for round-trip parse/generate operations."""

    def test_roundtrip_preserves_data(self):
        """Test that parsing and regenerating preserves metadata."""
        original = """---
title: Original Title
url: original-url
published: true
---

Body content here.
"""
        metadata, body = parse_frontmatter(original)
        regenerated = generate_frontmatter(metadata) + body

        # Parse again
        metadata2, body2 = parse_frontmatter(regenerated)

        assert metadata2["title"] == metadata["title"]
        assert metadata2["url"] == metadata["url"]
        assert metadata2["published"] == metadata["published"]
        assert body2 == body
