"""
Canvas API Client

Provides a singleton Canvas API client initialized from environment variables.
"""

import os
import re
import logging
from typing import Optional
from canvasapi import Canvas
from canvasapi.exceptions import InvalidAccessToken

from .exceptions import ConfigurationError, AuthenticationError, ValidationError

logger = logging.getLogger("canvas_author.client")

# Global client instance cache
_canvas_client: Optional["CanvasClient"] = None

# Valid domain pattern
DOMAIN_PATTERN = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9\-\.]*[a-zA-Z0-9]$')


def _validate_domain(domain: str) -> None:
    """Validate Canvas domain format."""
    if not domain:
        raise ConfigurationError(
            "CANVAS_DOMAIN not set.\n"
            "Set it in your .env file or environment:\n"
            "  CANVAS_DOMAIN=canvas.instructure.com"
        )
    if not DOMAIN_PATTERN.match(domain):
        raise ValidationError(f"Invalid Canvas domain format: {domain}")


def _validate_token(token: str) -> None:
    """Validate Canvas API token."""
    if not token:
        raise ConfigurationError(
            "CANVAS_API_TOKEN not set.\n"
            "Set it in your .env file or environment:\n"
            "  CANVAS_API_TOKEN=your_token_here\n"
            "Generate a token at: https://<your-domain>/profile/settings"
        )


class CanvasClient:
    """Wrapper around canvasapi.Canvas with lazy initialization."""

    def __init__(self, domain: Optional[str] = None, token: Optional[str] = None):
        """
        Initialize Canvas client.

        Args:
            domain: Canvas domain (e.g., 'canvas.instructure.com')
            token: Canvas API token

        If not provided, reads from CANVAS_DOMAIN and CANVAS_API_TOKEN environment variables.

        Raises:
            ConfigurationError: If credentials are missing
            ValidationError: If domain format is invalid
        """
        self.domain = domain or os.getenv("CANVAS_DOMAIN")
        self.token = token or os.getenv("CANVAS_API_TOKEN")
        self._client: Optional[Canvas] = None

    @property
    def client(self) -> Canvas:
        """
        Get or create the Canvas API client.

        Raises:
            ConfigurationError: If credentials are missing
            ValidationError: If domain format is invalid
            AuthenticationError: If token is invalid
        """
        if self._client is None:
            _validate_domain(self.domain)
            _validate_token(self.token)

            try:
                self._client = Canvas(f"https://{self.domain}", self.token)
                logger.info(f"Canvas API client initialized with domain: {self.domain}")
            except InvalidAccessToken:
                logger.error("Invalid Canvas API token provided")
                raise AuthenticationError(
                    "Invalid Canvas API token. Please check your token and try again.\n"
                    "Generate a new token at: https://{}/profile/settings".format(self.domain)
                )
            except Exception as e:
                logger.error(f"Error initializing Canvas API: {str(e)}")
                raise

        return self._client

    def get_course(self, course_id: str):
        """Get a course by ID."""
        return self.client.get_course(course_id)

    def get_courses(self, enrollment_type: str = "teacher", **kwargs):
        """Get courses for the current user."""
        return self.client.get_courses(enrollment_type=enrollment_type, **kwargs)

    def reinitialize(self, domain: Optional[str] = None, token: Optional[str] = None) -> bool:
        """
        Reinitialize the Canvas client with new credentials.

        Args:
            domain: New Canvas domain
            token: New Canvas API token

        Returns:
            True if successful, False otherwise
        """
        if domain:
            self.domain = domain
        if token:
            self.token = token

        self._client = None  # Force reinitialization

        try:
            _ = self.client  # Trigger initialization
            return True
        except Exception as e:
            logger.error(f"Failed to reinitialize Canvas client: {e}")
            return False


def get_canvas_client(domain: Optional[str] = None, token: Optional[str] = None) -> CanvasClient:
    """
    Get the global Canvas client instance.

    Args:
        domain: Optional Canvas domain override
        token: Optional Canvas API token override

    Returns:
        CanvasClient instance

    Raises:
        ConfigurationError: If credentials are missing
        ValidationError: If domain format is invalid
    """
    global _canvas_client

    # If new credentials provided, create new client
    if domain or token:
        return CanvasClient(domain=domain, token=token)

    # Return cached global client
    if _canvas_client is None:
        _canvas_client = CanvasClient()

    return _canvas_client
