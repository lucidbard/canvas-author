"""
Tests for the pages module.
"""

import pytest
from unittest.mock import patch, MagicMock
from canvasapi.exceptions import ResourceDoesNotExist

from canvas_author import pages
from canvas_author.exceptions import ResourceNotFoundError


class TestListPages:
    """Tests for list_pages function."""

    def test_list_pages_empty_course(self, mock_canvas_client):
        """Test listing pages from an empty course."""
        with patch.object(pages, "get_canvas_client", return_value=mock_canvas_client):
            result = pages.list_pages("12345")

        assert result == []

    def test_list_pages_with_pages(self, mock_canvas_client, mock_page):
        """Test listing pages from a course with pages."""
        course = mock_canvas_client.get_course("12345")
        course.add_page(mock_page)

        with patch.object(pages, "get_canvas_client", return_value=mock_canvas_client):
            result = pages.list_pages("12345")

        assert len(result) == 1
        assert result[0]["url"] == "test-page"
        assert result[0]["title"] == "Test Page"
        assert result[0]["published"] is True

    def test_list_pages_returns_metadata(self, mock_canvas_client, mock_page):
        """Test that list_pages returns correct metadata fields."""
        course = mock_canvas_client.get_course("12345")
        course.add_page(mock_page)

        with patch.object(pages, "get_canvas_client", return_value=mock_canvas_client):
            result = pages.list_pages("12345")

        page_data = result[0]
        assert "url" in page_data
        assert "title" in page_data
        assert "created_at" in page_data
        assert "updated_at" in page_data
        assert "published" in page_data
        assert "front_page" in page_data


class TestGetPage:
    """Tests for get_page function."""

    def test_get_page_success(self, mock_canvas_client, mock_page):
        """Test getting an existing page."""
        course = mock_canvas_client.get_course("12345")
        course.add_page(mock_page)

        with patch.object(pages, "get_canvas_client", return_value=mock_canvas_client):
            with patch.object(pages, "html_to_markdown", return_value="Test content"):
                result = pages.get_page("12345", "test-page")

        assert result["url"] == "test-page"
        assert result["title"] == "Test Page"
        assert "body" in result

    def test_get_page_not_found(self, mock_canvas_client):
        """Test getting a non-existent page raises ResourceNotFoundError."""
        with patch.object(pages, "get_canvas_client", return_value=mock_canvas_client):
            with pytest.raises(ResourceNotFoundError) as exc_info:
                pages.get_page("12345", "nonexistent")

        assert exc_info.value.resource_type == "page"
        assert exc_info.value.identifier == "nonexistent"

    def test_get_page_as_html(self, mock_canvas_client, mock_page):
        """Test getting a page without markdown conversion."""
        course = mock_canvas_client.get_course("12345")
        course.add_page(mock_page)

        with patch.object(pages, "get_canvas_client", return_value=mock_canvas_client):
            result = pages.get_page("12345", "test-page", as_markdown=False)

        assert result["body"] == "<p>Test content</p>"


class TestCreatePage:
    """Tests for create_page function."""

    def test_create_page_success(self, mock_canvas_client):
        """Test creating a new page."""
        with patch.object(pages, "get_canvas_client", return_value=mock_canvas_client):
            with patch.object(pages, "markdown_to_html", return_value="<p>Content</p>"):
                result = pages.create_page(
                    "12345",
                    title="New Page",
                    body="Content",
                    published=True
                )

        assert result["title"] == "New Page"
        assert "url" in result

    def test_create_page_unpublished(self, mock_canvas_client):
        """Test creating an unpublished page."""
        with patch.object(pages, "get_canvas_client", return_value=mock_canvas_client):
            with patch.object(pages, "markdown_to_html", return_value="<p>Draft</p>"):
                result = pages.create_page(
                    "12345",
                    title="Draft Page",
                    body="Draft",
                    published=False
                )

        assert result["published"] is False


class TestUpdatePage:
    """Tests for update_page function."""

    def test_update_page_title(self, mock_canvas_client, mock_page):
        """Test updating a page title."""
        course = mock_canvas_client.get_course("12345")
        course.add_page(mock_page)

        with patch.object(pages, "get_canvas_client", return_value=mock_canvas_client):
            result = pages.update_page(
                "12345",
                "test-page",
                title="Updated Title"
            )

        assert result["title"] == "Updated Title"

    def test_update_page_body(self, mock_canvas_client, mock_page):
        """Test updating page body."""
        course = mock_canvas_client.get_course("12345")
        course.add_page(mock_page)

        with patch.object(pages, "get_canvas_client", return_value=mock_canvas_client):
            with patch.object(pages, "markdown_to_html", return_value="<p>New content</p>"):
                result = pages.update_page(
                    "12345",
                    "test-page",
                    body="New content"
                )

        assert result["body"] == "<p>New content</p>"

    def test_update_page_not_found(self, mock_canvas_client):
        """Test updating a non-existent page raises ResourceNotFoundError."""
        with patch.object(pages, "get_canvas_client", return_value=mock_canvas_client):
            with pytest.raises(ResourceNotFoundError) as exc_info:
                pages.update_page("12345", "nonexistent", title="New")

        assert exc_info.value.resource_type == "page"


class TestDeletePage:
    """Tests for delete_page function."""

    def test_delete_page_success(self, mock_canvas_client, mock_page):
        """Test deleting an existing page."""
        course = mock_canvas_client.get_course("12345")
        course.add_page(mock_page)

        with patch.object(pages, "get_canvas_client", return_value=mock_canvas_client):
            result = pages.delete_page("12345", "test-page")

        assert result is True

    def test_delete_page_not_found(self, mock_canvas_client):
        """Test deleting a non-existent page raises ResourceNotFoundError."""
        with patch.object(pages, "get_canvas_client", return_value=mock_canvas_client):
            with pytest.raises(ResourceNotFoundError) as exc_info:
                pages.delete_page("12345", "nonexistent")

        assert exc_info.value.resource_type == "page"
