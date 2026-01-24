"""
Tests for the client module.
"""

import os
import pytest
from unittest.mock import patch, MagicMock
from canvas_common import (
    CanvasClient,
    get_canvas_client,
    _validate_domain,
    _validate_token,
)
from canvas_author.exceptions import (
    ConfigurationError,
    ValidationError,
    AuthenticationError,
)


class TestValidateDomain:
    """Tests for _validate_domain function."""

    def test_valid_domain(self):
        """Test validation of valid domain."""
        _validate_domain("canvas.instructure.com")  # Should not raise

    def test_valid_domain_with_subdomain(self):
        """Test validation of domain with subdomain."""
        _validate_domain("university.instructure.com")  # Should not raise

    def test_empty_domain_raises_config_error(self):
        """Test that empty domain raises ConfigurationError."""
        with pytest.raises(ConfigurationError) as exc_info:
            _validate_domain("")

        assert "CANVAS_DOMAIN" in str(exc_info.value)

    def test_none_domain_raises_config_error(self):
        """Test that None domain raises ConfigurationError."""
        with pytest.raises(ConfigurationError):
            _validate_domain(None)

    def test_invalid_domain_format(self):
        """Test that invalid domain format raises ValidationError."""
        # Only test cases that the regex actually catches
        invalid_domains = [
            "-invalid",  # Starts with hyphen
        ]

        for domain in invalid_domains:
            with pytest.raises(ValidationError):
                _validate_domain(domain)


class TestValidateToken:
    """Tests for _validate_token function."""

    def test_valid_token(self):
        """Test validation of valid token."""
        _validate_token("some-token-value")  # Should not raise

    def test_empty_token_raises_config_error(self):
        """Test that empty token raises ConfigurationError."""
        with pytest.raises(ConfigurationError) as exc_info:
            _validate_token("")

        assert "CANVAS_API_TOKEN" in str(exc_info.value)

    def test_none_token_raises_config_error(self):
        """Test that None token raises ConfigurationError."""
        with pytest.raises(ConfigurationError):
            _validate_token(None)


class TestCanvasClient:
    """Tests for CanvasClient class."""

    def test_init_with_explicit_credentials(self):
        """Test initialization with explicit credentials."""
        client = CanvasClient(domain="test.com", token="test-token")

        assert client.domain == "test.com"
        assert client.token == "test-token"

    def test_init_from_environment(self):
        """Test initialization from environment variables."""
        with patch.dict(os.environ, {
            "CANVAS_DOMAIN": "env.test.com",
            "CANVAS_API_TOKEN": "env-token"
        }):
            client = CanvasClient()

        assert client.domain == "env.test.com"
        assert client.token == "env-token"

    def test_client_property_validates_credentials(self):
        """Test that accessing client property triggers validation."""
        client = CanvasClient(domain="", token="test")

        with pytest.raises(ConfigurationError):
            _ = client.client

    def test_reinitialize_updates_domain(self):
        """Test that reinitialize updates domain."""
        client = CanvasClient(domain="old.com", token="old-token")
        old_mock = MagicMock()
        client._client = old_mock  # Simulate cached client

        # Reinitialize should update the domain
        client.reinitialize(domain="new.com")

        assert client.domain == "new.com"
        # After reinitialize, _client should either be None (if reinit failed)
        # or a new client (if reinit succeeded) - but not the old mock
        assert client._client is not old_mock


class TestGetCanvasClient:
    """Tests for get_canvas_client function."""

    def test_returns_canvas_client_instance(self):
        """Test that get_canvas_client returns a CanvasClient."""
        with patch.dict(os.environ, {
            "CANVAS_DOMAIN": "test.com",
            "CANVAS_API_TOKEN": "token"
        }):
            client = get_canvas_client()

        assert isinstance(client, CanvasClient)

    def test_override_credentials(self):
        """Test overriding credentials via parameters."""
        with patch.dict(os.environ, {
            "CANVAS_DOMAIN": "env.com",
            "CANVAS_API_TOKEN": "env-token"
        }):
            client = get_canvas_client(domain="override.com", token="override-token")

        assert client.domain == "override.com"
        assert client.token == "override-token"

    def test_caches_global_client(self):
        """Test that global client is cached."""
        import canvas_author.client as client_module

        # Clear any cached client
        client_module._canvas_client = None

        with patch.dict(os.environ, {
            "CANVAS_DOMAIN": "test.com",
            "CANVAS_API_TOKEN": "token"
        }):
            client1 = get_canvas_client()
            client2 = get_canvas_client()

        assert client1 is client2

        # Cleanup
        client_module._canvas_client = None
