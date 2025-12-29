"""
Tests for the exceptions module.
"""

import pytest
from canvas_mcp.exceptions import (
    CanvasMCPError,
    ConfigurationError,
    AuthenticationError,
    ResourceNotFoundError,
    APIError,
    RateLimitError,
    ValidationError,
    PandocError,
    SyncError,
    FileOperationError,
)


class TestExceptionHierarchy:
    """Tests for exception class hierarchy."""

    def test_all_exceptions_inherit_from_base(self):
        """All custom exceptions should inherit from CanvasMCPError."""
        exceptions = [
            ConfigurationError("test"),
            AuthenticationError("test"),
            ResourceNotFoundError("page", "test-page"),
            APIError("test"),
            RateLimitError(),
            ValidationError("test"),
            PandocError("test"),
            SyncError("test"),
            FileOperationError("read", "/path/to/file"),
        ]

        for exc in exceptions:
            assert isinstance(exc, CanvasMCPError)
            assert isinstance(exc, Exception)


class TestResourceNotFoundError:
    """Tests for ResourceNotFoundError."""

    def test_basic_creation(self):
        """Test creating a ResourceNotFoundError."""
        error = ResourceNotFoundError("page", "test-page")

        assert error.resource_type == "page"
        assert error.identifier == "test-page"
        assert "page not found" in str(error).lower()
        assert "test-page" in str(error)

    def test_custom_message(self):
        """Test ResourceNotFoundError with custom message."""
        error = ResourceNotFoundError("user", "123", "User with ID 123 does not exist")

        assert error.resource_type == "user"
        assert error.identifier == "123"
        assert str(error) == "User with ID 123 does not exist"


class TestAPIError:
    """Tests for APIError."""

    def test_basic_creation(self):
        """Test creating an APIError."""
        error = APIError("Something went wrong")

        assert str(error) == "Something went wrong"
        assert error.status_code is None
        assert error.response is None

    def test_with_status_code(self):
        """Test APIError with status code."""
        error = APIError("Not found", status_code=404, response='{"error": "not found"}')

        assert error.status_code == 404
        assert error.response == '{"error": "not found"}'


class TestRateLimitError:
    """Tests for RateLimitError."""

    def test_basic_creation(self):
        """Test creating a RateLimitError."""
        error = RateLimitError()

        assert "rate limit" in str(error).lower()
        assert error.status_code == 429
        assert error.retry_after is None

    def test_with_retry_after(self):
        """Test RateLimitError with retry_after."""
        error = RateLimitError(retry_after=60)

        assert error.retry_after == 60
        assert "60" in str(error)


class TestFileOperationError:
    """Tests for FileOperationError."""

    def test_basic_creation(self):
        """Test creating a FileOperationError."""
        error = FileOperationError("read", "/path/to/file")

        assert error.operation == "read"
        assert error.path == "/path/to/file"
        assert error.cause is None
        assert "read" in str(error).lower()
        assert "/path/to/file" in str(error)

    def test_with_cause(self):
        """Test FileOperationError with cause."""
        cause = PermissionError("Permission denied")
        error = FileOperationError("write", "/etc/passwd", cause=cause)

        assert error.cause == cause
        assert "Permission denied" in str(error)


class TestPandocError:
    """Tests for PandocError."""

    def test_basic_creation(self):
        """Test creating a PandocError."""
        error = PandocError("Conversion failed")

        assert str(error) == "Conversion failed"
        assert error.stderr is None

    def test_with_stderr(self):
        """Test PandocError with stderr."""
        error = PandocError("Conversion failed", stderr="pandoc: error parsing input")

        assert error.stderr == "pandoc: error parsing input"


class TestExceptionCatching:
    """Tests for exception catching behavior."""

    def test_catch_specific_exception(self):
        """Test catching a specific exception type."""
        with pytest.raises(ResourceNotFoundError) as exc_info:
            raise ResourceNotFoundError("assignment", "999")

        assert exc_info.value.resource_type == "assignment"
        assert exc_info.value.identifier == "999"

    def test_catch_base_exception(self):
        """Test catching exceptions via base class."""
        exceptions_to_test = [
            ConfigurationError("config error"),
            AuthenticationError("auth error"),
            ResourceNotFoundError("page", "test"),
        ]

        for exc in exceptions_to_test:
            with pytest.raises(CanvasMCPError):
                raise exc
