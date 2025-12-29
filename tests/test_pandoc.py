"""
Tests for the pandoc module.
"""

import pytest
import subprocess
from unittest.mock import patch, MagicMock
from canvas_mcp.pandoc import (
    is_pandoc_available,
    markdown_to_html,
    html_to_markdown,
)


class TestIsPandocAvailable:
    """Tests for is_pandoc_available function."""

    def test_pandoc_available(self):
        """Test when pandoc is available."""
        with patch("shutil.which", return_value="/usr/bin/pandoc"):
            assert is_pandoc_available() is True

    def test_pandoc_not_available(self):
        """Test when pandoc is not available."""
        with patch("shutil.which", return_value=None):
            assert is_pandoc_available() is False


class TestMarkdownToHtml:
    """Tests for markdown_to_html function."""

    def test_converts_basic_markdown(self):
        """Test converting basic markdown to HTML."""
        with patch("shutil.which", return_value="/usr/bin/pandoc"):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(
                    returncode=0,
                    stdout="<p>Hello <strong>world</strong></p>\n"
                )

                result = markdown_to_html("Hello **world**")

                assert "<strong>world</strong>" in result
                mock_run.assert_called_once()

    def test_raises_when_pandoc_not_installed(self):
        """Test that RuntimeError is raised when pandoc is not installed."""
        with patch("shutil.which", return_value=None):
            with pytest.raises(RuntimeError) as exc_info:
                markdown_to_html("Some content")

            assert "pandoc is not installed" in str(exc_info.value)

    def test_raises_on_pandoc_failure(self):
        """Test that RuntimeError is raised when pandoc fails."""
        with patch("shutil.which", return_value="/usr/bin/pandoc"):
            with patch("subprocess.run") as mock_run:
                mock_run.side_effect = subprocess.CalledProcessError(
                    1, "pandoc", stderr="error parsing"
                )

                with pytest.raises(RuntimeError):
                    markdown_to_html("Some content")


class TestHtmlToMarkdown:
    """Tests for html_to_markdown function."""

    def test_converts_basic_html(self):
        """Test converting basic HTML to markdown."""
        with patch("shutil.which", return_value="/usr/bin/pandoc"):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(
                    returncode=0,
                    stdout="Hello **world**\n"
                )

                result = html_to_markdown("<p>Hello <strong>world</strong></p>")

                assert "world" in result
                mock_run.assert_called_once()

    def test_raises_when_pandoc_not_installed(self):
        """Test that RuntimeError is raised when pandoc is not installed."""
        with patch("shutil.which", return_value=None):
            with pytest.raises(RuntimeError) as exc_info:
                html_to_markdown("<p>Content</p>")

            assert "pandoc is not installed" in str(exc_info.value)

    def test_raises_on_pandoc_failure(self):
        """Test that RuntimeError is raised when pandoc fails."""
        with patch("shutil.which", return_value="/usr/bin/pandoc"):
            with patch("subprocess.run") as mock_run:
                mock_run.side_effect = subprocess.CalledProcessError(
                    1, "pandoc", stderr="error"
                )

                with pytest.raises(RuntimeError):
                    html_to_markdown("<p>Content</p>")


class TestPandocIntegration:
    """Integration tests that require actual pandoc installation."""

    @pytest.fixture(autouse=True)
    def skip_if_no_pandoc(self):
        """Skip these tests if pandoc is not installed."""
        if not is_pandoc_available():
            pytest.skip("pandoc not available")

    def test_real_markdown_to_html(self):
        """Test actual markdown to HTML conversion."""
        markdown = "# Hello\n\nThis is **bold** text."
        result = markdown_to_html(markdown)

        assert "<h1" in result or "Hello" in result
        assert "<strong>" in result or "**" not in result

    def test_real_html_to_markdown(self):
        """Test actual HTML to markdown conversion."""
        html = "<h1>Hello</h1><p>This is <strong>bold</strong> text.</p>"
        result = html_to_markdown(html)

        assert "Hello" in result
        assert "bold" in result
        # Should not contain raw HTML tags
        assert "<h1>" not in result
        assert "<p>" not in result

    def test_roundtrip(self):
        """Test markdown -> HTML -> markdown roundtrip."""
        original = "# Title\n\nSome **bold** and *italic* text."
        html = markdown_to_html(original)
        back = html_to_markdown(html)

        # Content should be preserved (exact formatting may differ)
        assert "Title" in back
        assert "bold" in back
        assert "italic" in back
