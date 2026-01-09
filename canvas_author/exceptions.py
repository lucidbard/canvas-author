"""
Custom Exceptions for Canvas MCP

Provides specific exception types for different error conditions.
"""


class CanvasMCPError(Exception):
    """Base exception for all Canvas MCP errors."""
    pass


class ConfigurationError(CanvasMCPError):
    """Raised when configuration is missing or invalid."""
    pass


class AuthenticationError(CanvasMCPError):
    """Raised when Canvas API authentication fails."""
    pass


class ResourceNotFoundError(CanvasMCPError):
    """Raised when a Canvas resource (page, assignment, etc.) is not found."""

    def __init__(self, resource_type: str, identifier: str, message: str = None):
        self.resource_type = resource_type
        self.identifier = identifier
        self.message = message or f"{resource_type} not found: {identifier}"
        super().__init__(self.message)


class APIError(CanvasMCPError):
    """Raised when Canvas API returns an error."""

    def __init__(self, message: str, status_code: int = None, response: str = None):
        self.status_code = status_code
        self.response = response
        super().__init__(message)


class RateLimitError(APIError):
    """Raised when Canvas API rate limit is exceeded."""

    def __init__(self, retry_after: int = None):
        self.retry_after = retry_after
        message = "Canvas API rate limit exceeded"
        if retry_after:
            message += f". Retry after {retry_after} seconds"
        super().__init__(message, status_code=429)


class ValidationError(CanvasMCPError):
    """Raised when input validation fails."""
    pass


class PandocError(CanvasMCPError):
    """Raised when pandoc conversion fails."""

    def __init__(self, message: str, stderr: str = None):
        self.stderr = stderr
        super().__init__(message)


class SyncError(CanvasMCPError):
    """Raised when sync operations fail."""
    pass


class URLMismatchError(SyncError):
    """Raised when local URL won't match Canvas-generated URL.

    Canvas generates page URLs from the title, so if your local filename
    differs from the slugified title, this error is raised to prevent
    creating duplicate files.

    Use --force-rename to allow the push and automatically rename local files.
    """

    def __init__(self, local_url: str, predicted_url: str, title: str, file_path: str):
        self.local_url = local_url
        self.predicted_url = predicted_url
        self.title = title
        self.file_path = file_path
        message = (
            f"URL mismatch: Local file '{file_path}' has URL '{local_url}', "
            f"but Canvas will generate '{predicted_url}' from title '{title}'.\n"
            f"This would create duplicate files on pull.\n"
            f"Options:\n"
            f"  1. Rename your file to '{predicted_url}.md'\n"
            f"  2. Change the title to match your desired URL\n"
            f"  3. Use --force-rename to push anyway and auto-rename local files"
        )
        super().__init__(message)


class FileOperationError(CanvasMCPError):
    """Raised when file operations fail."""

    def __init__(self, operation: str, path: str, cause: Exception = None):
        self.operation = operation
        self.path = path
        self.cause = cause
        message = f"Failed to {operation} file: {path}"
        if cause:
            message += f" ({cause})"
        super().__init__(message)
