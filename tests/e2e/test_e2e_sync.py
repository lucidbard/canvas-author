"""
E2E tests for sync operations (pull/push).

Run with: pytest tests/e2e/test_e2e_sync.py -v -m e2e
"""

import pytest
from pathlib import Path
from canvas_author.sync import pull_pages, push_pages, sync_status
from canvas_author.pages import create_page
from canvas_author.frontmatter import parse_frontmatter


pytestmark = pytest.mark.e2e


class TestPullOperations:
    """Test pulling pages from Canvas to local files."""

    def test_pull_all_pages_to_directory(
        self,
        canvas_client,
        test_course_id: str,
        temp_workspace: Path,
        test_page_name: str,
        cleanup_test_pages
    ):
        """Test pulling all pages from Canvas to a directory."""
        create_page(
            course_id=test_course_id,
            title=f"Pull: {test_page_name}",
            body="# Content to pull",
            from_markdown=True,
            client=canvas_client
        )

        result = pull_pages(
            course_id=test_course_id,
            output_dir=str(temp_workspace),
            include_frontmatter=True,
            overwrite=True,
            client=canvas_client
        )

        assert "pulled" in result
        assert len(result["pulled"]) > 0

        md_files = list(temp_workspace.glob("*.md"))
        assert len(md_files) > 0

    def test_pull_creates_correct_frontmatter(
        self,
        canvas_client,
        test_course_id: str,
        temp_workspace: Path,
        test_page_name: str,
        cleanup_test_pages
    ):
        """Test that pulled pages have correct YAML frontmatter."""
        created = create_page(
            course_id=test_course_id,
            title=f"Frontmatter: {test_page_name}",
            body="# Test",
            from_markdown=True,
            published=True,
            client=canvas_client
        )

        pull_pages(
            course_id=test_course_id,
            output_dir=str(temp_workspace),
            include_frontmatter=True,
            overwrite=True,
            client=canvas_client
        )

        file_path = temp_workspace / f"{created['url']}.md"
        assert file_path.exists()

        content = file_path.read_text(encoding="utf-8")
        metadata, body = parse_frontmatter(content)

        assert "title" in metadata
        assert "url" in metadata
        assert metadata["published"] is True


class TestPushOperations:
    """Test pushing local markdown files to Canvas."""

    def test_push_new_markdown_file_creates_page(
        self,
        canvas_client,
        test_course_id: str,
        temp_workspace: Path,
        test_page_name: str,
        cleanup_test_pages
    ):
        """Test that pushing a new markdown file creates a page on Canvas."""
        md_file = temp_workspace / f"{test_page_name}.md"
        md_file.write_text(
            f"---\ntitle: Push Test\nurl: {test_page_name}\npublished: true\n---\n\n# New Page\n\nContent here.",
            encoding="utf-8"
        )

        result = push_pages(
            course_id=test_course_id,
            input_dir=str(temp_workspace),
            create_missing=True,
            update_existing=False,
            client=canvas_client
        )

        assert len(result["created"]) == 1
        assert result["created"][0]["url"] == test_page_name


class TestSyncStatus:
    """Test sync status checking."""

    def test_sync_status_returns_structure(
        self,
        canvas_client,
        test_course_id: str,
        temp_workspace: Path
    ):
        """Test that sync status returns correct structure."""
        status = sync_status(
            course_id=test_course_id,
            local_dir=str(temp_workspace),
            client=canvas_client
        )

        assert "canvas_only" in status
        assert "local_only" in status
        assert "both" in status
        assert "summary" in status
