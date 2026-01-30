"""
Test suite for OAuthStateManager.

This module contains comprehensive unit tests for OAuth state encoding/decoding:
- encode_state: Encode OAuth state with callback URL and remember_me
- decode_state: Decode and validate OAuth state
- validate_callback_url: Validate callback URLs against CORS origins

Run tests:
    pytest tests/services/oauth/test_oauth_state.py -v
"""

from unittest.mock import patch

import pytest


class TestOAuthStateData:
    """Test suite for OAuthStateData dataclass."""

    def test_oauth_state_data_defaults(self):
        """Test OAuthStateData has correct defaults."""
        from app.shared.services.oauth import OAuthStateData

        data = OAuthStateData()
        assert data.callback_url is None
        assert data.remember_me is False
        assert data.nonce is not None
        assert len(data.nonce) == 32  # 16 bytes hex = 32 chars

    def test_oauth_state_data_with_values(self):
        """Test OAuthStateData with custom values."""
        from app.shared.services.oauth import OAuthStateData

        data = OAuthStateData(
            callback_url="https://example.com/callback",
            remember_me=True,
            nonce="custom_nonce",
        )
        assert data.callback_url == "https://example.com/callback"
        assert data.remember_me is True
        assert data.nonce == "custom_nonce"


class TestOAuthStateManagerEncode:
    """Test suite for OAuthStateManager.encode_state."""

    def test_encode_state_returns_string(self):
        """Test encode_state returns a non-empty string."""
        from app.shared.services.oauth import OAuthStateManager

        state = OAuthStateManager.encode_state()
        assert isinstance(state, str)
        assert len(state) > 0

    def test_encode_state_with_callback_url(self):
        """Test encode_state includes callback_url."""
        from app.shared.services.oauth import OAuthStateManager

        state = OAuthStateManager.encode_state(
            callback_url="https://myapp.com/callback",
        )
        assert isinstance(state, str)
        assert len(state) > 0

        # Verify it decodes correctly
        decoded = OAuthStateManager.decode_state(state)
        assert decoded is not None
        assert decoded.callback_url == "https://myapp.com/callback"

    def test_encode_state_with_remember_me(self):
        """Test encode_state includes remember_me flag."""
        from app.shared.services.oauth import OAuthStateManager

        state = OAuthStateManager.encode_state(remember_me=True)
        decoded = OAuthStateManager.decode_state(state)
        assert decoded is not None
        assert decoded.remember_me is True

    def test_encode_state_unique_nonces(self):
        """Test encode_state generates unique nonces."""
        from app.shared.services.oauth import OAuthStateManager

        state1 = OAuthStateManager.encode_state()
        state2 = OAuthStateManager.encode_state()

        # States should be different due to unique nonces
        assert state1 != state2


class TestOAuthStateManagerDecode:
    """Test suite for OAuthStateManager.decode_state."""

    def test_decode_state_success(self):
        """Test decode_state successfully decodes valid state."""
        from app.shared.services.oauth import OAuthStateManager

        state = OAuthStateManager.encode_state(
            callback_url="https://example.com/cb",
            remember_me=True,
        )
        decoded = OAuthStateManager.decode_state(state)

        assert decoded is not None
        assert decoded.callback_url == "https://example.com/cb"
        assert decoded.remember_me is True
        assert decoded.nonce is not None

    def test_decode_state_invalid_signature(self):
        """Test decode_state returns None for tampered state."""
        from app.shared.services.oauth import OAuthStateManager

        # Tamper with the state
        state = OAuthStateManager.encode_state()
        tampered_state = state[:-5] + "xxxxx"

        decoded = OAuthStateManager.decode_state(tampered_state)
        assert decoded is None

    def test_decode_state_garbage_input(self):
        """Test decode_state returns None for garbage input."""
        from app.shared.services.oauth import OAuthStateManager

        decoded = OAuthStateManager.decode_state("not_a_valid_state")
        assert decoded is None

    def test_decode_state_empty_string(self):
        """Test decode_state returns None for empty string."""
        from app.shared.services.oauth import OAuthStateManager

        decoded = OAuthStateManager.decode_state("")
        assert decoded is None

    def test_decode_state_expired(self):
        """Test decode_state returns None for expired state."""
        from app.shared.services.oauth import OAuthStateManager
        from app.shared.services.oauth.base import _state_serializer

        # Create a state with the serializer directly, then mock max_age
        state = OAuthStateManager.encode_state()

        # Mock the loads to raise SignatureExpired
        from itsdangerous import SignatureExpired

        with patch.object(
            _state_serializer,
            "loads",
            side_effect=SignatureExpired("expired"),
        ):
            decoded = OAuthStateManager.decode_state(state)
            assert decoded is None


class TestOAuthStateManagerValidateCallback:
    """Test suite for OAuthStateManager.validate_callback_url."""

    def test_validate_callback_url_empty(self):
        """Test validate_callback_url rejects empty URL."""
        from app.shared.services.oauth import OAuthStateManager

        assert OAuthStateManager.validate_callback_url("") is False
        assert OAuthStateManager.validate_callback_url(None) is False

    def test_validate_callback_url_no_scheme(self):
        """Test validate_callback_url rejects URL without scheme."""
        from app.shared.services.oauth import OAuthStateManager

        assert OAuthStateManager.validate_callback_url("example.com/callback") is False

    def test_validate_callback_url_allowed_origin(self):
        """Test validate_callback_url accepts URL in CORS origins."""
        from app.shared.services.oauth import OAuthStateManager

        with patch(
            "app.shared.services.oauth.base.settings.CORS_ALLOW_ORIGINS",
            ["https://myapp.com"],
        ), patch(
            "app.shared.services.oauth.base.settings.ENVIRONMENT",
            "development",
        ):
            result = OAuthStateManager.validate_callback_url(
                "https://myapp.com/auth/callback"
            )
            assert result is True

    def test_validate_callback_url_not_in_origins(self):
        """Test validate_callback_url rejects URL not in CORS origins."""
        from app.shared.services.oauth import OAuthStateManager

        with patch(
            "app.shared.services.oauth.base.settings.CORS_ALLOW_ORIGINS",
            ["https://myapp.com"],
        ), patch(
            "app.shared.services.oauth.base.settings.ENVIRONMENT",
            "development",
        ):
            result = OAuthStateManager.validate_callback_url(
                "https://evil-site.com/callback"
            )
            assert result is False

    def test_validate_callback_url_wildcard_origin(self):
        """Test validate_callback_url accepts any URL with wildcard origin."""
        from app.shared.services.oauth import OAuthStateManager

        with patch(
            "app.shared.services.oauth.base.settings.CORS_ALLOW_ORIGINS",
            ["*"],
        ), patch(
            "app.shared.services.oauth.base.settings.ENVIRONMENT",
            "development",
        ):
            result = OAuthStateManager.validate_callback_url(
                "https://any-site.com/callback"
            )
            assert result is True

    def test_validate_callback_url_production_requires_https(self):
        """Test validate_callback_url requires HTTPS in production."""
        from app.shared.services.oauth import OAuthStateManager

        with patch(
            "app.shared.services.oauth.base.settings.CORS_ALLOW_ORIGINS",
            ["http://myapp.com", "https://myapp.com"],
        ), patch(
            "app.shared.services.oauth.base.settings.ENVIRONMENT",
            "production",
        ):
            # HTTP should fail in production
            result = OAuthStateManager.validate_callback_url(
                "http://myapp.com/callback"
            )
            assert result is False

            # HTTPS should work
            result = OAuthStateManager.validate_callback_url(
                "https://myapp.com/callback"
            )
            assert result is True

    def test_validate_callback_url_development_allows_http(self):
        """Test validate_callback_url allows HTTP in development."""
        from app.shared.services.oauth import OAuthStateManager

        with patch(
            "app.shared.services.oauth.base.settings.CORS_ALLOW_ORIGINS",
            ["http://localhost:3000"],
        ), patch(
            "app.shared.services.oauth.base.settings.ENVIRONMENT",
            "development",
        ):
            result = OAuthStateManager.validate_callback_url(
                "http://localhost:3000/callback"
            )
            assert result is True

    def test_validate_callback_url_trailing_slash_handling(self):
        """Test validate_callback_url handles trailing slashes correctly."""
        from app.shared.services.oauth import OAuthStateManager

        with patch(
            "app.shared.services.oauth.base.settings.CORS_ALLOW_ORIGINS",
            ["https://myapp.com/"],
        ), patch(
            "app.shared.services.oauth.base.settings.ENVIRONMENT",
            "development",
        ):
            # Should match despite different trailing slash
            result = OAuthStateManager.validate_callback_url(
                "https://myapp.com/callback"
            )
            assert result is True


class TestOAuthStateManagerIntegration:
    """Integration tests for OAuthStateManager."""

    def test_full_encode_decode_cycle(self):
        """Test complete encode/decode cycle preserves data."""
        from app.shared.services.oauth import OAuthStateManager

        original_callback = "https://frontend.app/oauth/callback"
        original_remember_me = True

        state = OAuthStateManager.encode_state(
            callback_url=original_callback,
            remember_me=original_remember_me,
        )

        decoded = OAuthStateManager.decode_state(state)

        assert decoded is not None
        assert decoded.callback_url == original_callback
        assert decoded.remember_me == original_remember_me

    def test_state_is_url_safe(self):
        """Test encoded state is URL-safe."""
        from app.shared.services.oauth import OAuthStateManager
        import re

        state = OAuthStateManager.encode_state(
            callback_url="https://example.com/path?query=value",
            remember_me=True,
        )

        # URL-safe characters: alphanumeric, hyphen, underscore, period, tilde
        # itsdangerous uses base64url encoding which includes - and _
        assert re.match(r"^[A-Za-z0-9_.\-]+$", state)


class TestModuleExports:
    """Test that OAuthStateManager is properly exported."""

    def test_exports_from_oauth_package(self):
        """Test OAuthStateManager is exported from oauth package."""
        from app.shared.services.oauth import OAuthStateManager, OAuthStateData

        assert OAuthStateManager is not None
        assert OAuthStateData is not None

    def test_all_includes_state_manager(self):
        """Test __all__ includes OAuthStateManager."""
        from app.shared.services import oauth

        assert "OAuthStateManager" in oauth.__all__
        assert "OAuthStateData" in oauth.__all__
