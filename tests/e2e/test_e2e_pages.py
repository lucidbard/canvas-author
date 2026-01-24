"""
E2E tests for Canvas wiki page operations.

These tests run against a real Canvas instance and require:
- E2E_CANVAS_API_TOKEN
- E2E_CANVAS_DOMAIN
- E2E_CANVAS_COURSE_ID

Run with: pytest tests/e2e/ -v -m e2e
"""

import pytest
from canvas_author.pages import (
    create_page, get_page, update_page, delete_page, list_pages
)
from canvas_author.exceptions import ResourceNotFoundError


pytestmark = pytest.mark.e2e


class TestPageCreation:
    """Test page creation operations."""

    def test_create_simple_markdown_page(
        self,
        canvas_client,
        test_course_id: str,
        test_page_name: str,
        sample_markdown: str,
        cleanup_test_pages
    ):
        """Test creating a page from markdown content."""
        result = create_page(
            course_id=test_course_id,
            title=f"Test: {test_page_name}",
            body=sample_markdown,
            from_markdown=True,
            published=True,
            client=canvas_client
        )

        # Verify result structure
        assert "url" in result
        assert "title" in result
        assert result["published"] is True

        # Retrieve and verify
        page = get_page(
            course_id=test_course_id,
            page_url=result["url"],
            as_markdown=True,
            client=canvas_client
        )

        assert page["title"] == f"Test: {test_page_name}"
        assert "Test Page" in page["body"]

    def test_create_page_with_complex_markdown(
        self,
        canvas_client,
        test_course_id: str,
        test_page_name: str,
        complex_markdown: str,
        cleanup_test_pages
    ):
        """Test creating a page with complex markdown features."""
        result = create_page(
            course_id=test_course_id,
            title=f"Complex: {test_page_name}",
            body=complex_markdown,
            from_markdown=True,
            client=canvas_client
        )

        page = get_page(
            course_id=test_course_id,
            page_url=result["url"],
            as_markdown=True,
            client=canvas_client
        )

        assert "Complex Test Page" in page["body"]

    def test_create_unpublished_page(
        self,
        canvas_client,
        test_course_id: str,
        test_page_name: str,
        cleanup_test_pages
    ):
        """Test creating an unpublished page."""
        result = create_page(
            course_id=test_course_id,
            title=f"Unpublished: {test_page_name}",
            body="Draft content",
            from_markdown=True,
            published=False,
            client=canvas_client
        )

        page = get_page(
            course_id=test_course_id,
            page_url=result["url"],
            client=canvas_client
        )

        assert page["published"] is False


class TestPageRetrieval:
    """Test page retrieval operations."""

    def test_list_all_pages(
        self,
        canvas_client,
        test_course_id: str
    ):
        """Test listing all pages in a course."""
        pages = list_pages(test_course_id, canvas_client)

        assert isinstance(pages, list)
        if pages:
            page = pages[0]
            assert "url" in page
            assert "title" in page
            assert "published" in page

    def test_get_page_as_markdown(
        self,
        canvas_client,
        test_course_id: str,
        test_page_name: str,
        sample_markdown: str,
        cleanup_test_pages
    ):
        """Test retrieving a page with markdown conversion."""
        created = create_page(
            course_id=test_course_id,
            title=f"Get: {test_page_name}",
            body=sample_markdown,
            from_markdown=True,
            client=canvas_client
        )

        page = get_page(
            course_id=test_course_id,
            page_url=created["url"],
            as_markdown=True,
            client=canvas_client
        )

        assert page["body"]
        assert isinstance(page["body"], str)

    def test_get_nonexistent_page_raises_error(
        self,
        canvas_client,
        test_course_id: str
    ):
        """Test that getting a non-existent page raises ResourceNotFoundError."""
        with pytest.raises(ResourceNotFoundError) as exc_info:
            get_page(
                course_id=test_course_id,
                page_url="this-page-definitely-does-not-exist-xyz123",
                client=canvas_client
            )

        assert exc_info.value.resource_type == "page"


class TestPageUpdate:
    """Test page update operations."""

    def test_update_page_content(
        self,
        canvas_client,
        test_course_id: str,
        test_page_name: str,
        cleanup_test_pages
    ):
        """Test updating page content."""
        created = create_page(
            course_id=test_course_id,
            title=f"Update: {test_page_name}",
            body="# Initial Content",
            from_markdown=True,
            client=canvas_client
        )

        update_page(
            course_id=test_course_id,
            page_url=created["url"],
            body="# Updated Content\n\nThis is new!",
            from_markdown=True,
            client=canvas_client
        )

        page = get_page(
            course_id=test_course_id,
            page_url=created["url"],
            as_markdown=True,
            client=canvas_client
        )

        assert "Updated Content" in page["body"]

    def test_update_page_publish_status(
        self,
        canvas_client,
        test_course_id: str,
        test_page_name: str,
        cleanup_test_pages
    ):
        """Test toggling page published status."""
        created = create_page(
            course_id=test_course_id,
            title=f"Publish: {test_page_name}",
            body="Test content",
            from_markdown=True,
            published=True,
            client=canvas_client
        )

        update_page(
            course_id=test_course_id,
            page_url=created["url"],
            published=False,
            client=canvas_client
        )

        page = get_page(
            course_id=test_course_id,
            page_url=created["url"],
            client=canvas_client
        )

        assert page["published"] is False


class TestPageDeletion:
    """Test page deletion operations."""

    def test_delete_page(
        self,
        canvas_client,
        test_course_id: str,
        test_page_name: str
    ):
        """Test deleting a page."""
        created = create_page(
            course_id=test_course_id,
            title=f"Delete: {test_page_name}",
            body="To be deleted",
            from_markdown=True,
            client=canvas_client
        )

        result = delete_page(
            course_id=test_course_id,
            page_url=created["url"],
            client=canvas_client
        )

        assert result is True

        with pytest.raises(ResourceNotFoundError):
            get_page(
                course_id=test_course_id,
                page_url=created["url"],
                client=canvas_client
            )
