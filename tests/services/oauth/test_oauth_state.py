"""
Test suite for OAuthStateManager.

- encode_state: Encode OAuth state with callback URL and remember_me
- decode_state: Decode and validate OAuth state
- validate_callback_url: Validate callback URLs against CORS origins

Run tests:
    pytest tests/services/oauth/test_oauth_state.py -v
"""

from unittest.mock import patch

import pytest


class TestOAuthStateData:

    def test_oauth_state_data_defaults(self):
        from app.core.services.oauth import OAuthStateData

        data = OAuthStateData()
        assert data.callback_url is None
        assert data.remember_me is False
        assert data.nonce is not None
        assert len(data.nonce) == 32  # 16 bytes hex = 32 chars

    def test_oauth_state_data_with_values(self):
        from app.core.services.oauth import OAuthStateData

        data = OAuthStateData(
            callback_url="https://example.com/callback",
            remember_me=True,
            nonce="custom_nonce",
        )
        assert data.callback_url == "https://example.com/callback"
        assert data.remember_me is True
        assert data.nonce == "custom_nonce"


class TestOAuthStateManagerEncode:

    def test_encode_state_returns_string(self):
        from app.core.services.oauth import OAuthStateManager

        state = OAuthStateManager.encode_state()
        assert isinstance(state, str)
        assert len(state) > 0

    def test_encode_state_with_callback_url(self):
        from app.core.services.oauth import OAuthStateManager

        state = OAuthStateManager.encode_state(
            callback_url="https://myapp.com/callback",
        )
        assert isinstance(state, str)
        assert len(state) > 0

        decoded = OAuthStateManager.decode_state(state)
        assert decoded is not None
        assert decoded.callback_url == "https://myapp.com/callback"

    def test_encode_state_with_remember_me(self):
        from app.core.services.oauth import OAuthStateManager

        state = OAuthStateManager.encode_state(remember_me=True)
        decoded = OAuthStateManager.decode_state(state)
        assert decoded is not None
        assert decoded.remember_me is True

    def test_encode_state_unique_nonces(self):
        from app.core.services.oauth import OAuthStateManager

        state1 = OAuthStateManager.encode_state()
        state2 = OAuthStateManager.encode_state()

        # States should be different due to unique nonces
        assert state1 != state2


class TestOAuthStateManagerDecode:

    def test_decode_state_success(self):
        from app.core.services.oauth import OAuthStateManager

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
        from app.core.services.oauth import OAuthStateManager

        # Tamper with the state
        state = OAuthStateManager.encode_state()
        tampered_state = state[:-5] + "xxxxx"

        decoded = OAuthStateManager.decode_state(tampered_state)
        assert decoded is None

    def test_decode_state_garbage_input(self):
        from app.core.services.oauth import OAuthStateManager

        decoded = OAuthStateManager.decode_state("not_a_valid_state")
        assert decoded is None

    def test_decode_state_empty_string(self):
        from app.core.services.oauth import OAuthStateManager

        decoded = OAuthStateManager.decode_state("")
        assert decoded is None

    def test_decode_state_expired(self):
        from app.core.services.oauth import OAuthStateManager
        from app.core.services.oauth.base import _state_serializer

        state = OAuthStateManager.encode_state()

        from itsdangerous import SignatureExpired

        with patch.object(
            _state_serializer,
            "loads",
            side_effect=SignatureExpired("expired"),
        ):
            decoded = OAuthStateManager.decode_state(state)
            assert decoded is None


class TestOAuthStateManagerValidateCallback:

    def test_validate_callback_url_empty(self):
        from app.core.services.oauth import OAuthStateManager

        assert OAuthStateManager.validate_callback_url("") is False
        assert OAuthStateManager.validate_callback_url(None) is False

    def test_validate_callback_url_no_scheme(self):
        from app.core.services.oauth import OAuthStateManager

        assert OAuthStateManager.validate_callback_url("example.com/callback") is False

    def test_validate_callback_url_allowed_origin(self):
        from app.core.services.oauth import OAuthStateManager

        with patch(
            "app.core.services.oauth.base.settings.CORS_ALLOW_ORIGINS",
            ["https://myapp.com"],
        ), patch(
            "app.core.services.oauth.base.settings.ENVIRONMENT",
            "development",
        ):
            result = OAuthStateManager.validate_callback_url(
                "https://myapp.com/auth/callback"
            )
            assert result is True

    def test_validate_callback_url_not_in_origins(self):
        from app.core.services.oauth import OAuthStateManager

        with patch(
            "app.core.services.oauth.base.settings.CORS_ALLOW_ORIGINS",
            ["https://myapp.com"],
        ), patch(
            "app.core.services.oauth.base.settings.ENVIRONMENT",
            "development",
        ):
            result = OAuthStateManager.validate_callback_url(
                "https://evil-site.com/callback"
            )
            assert result is False

    def test_validate_callback_url_wildcard_origin(self):
        from app.core.services.oauth import OAuthStateManager

        with patch(
            "app.core.services.oauth.base.settings.CORS_ALLOW_ORIGINS",
            ["*"],
        ), patch(
            "app.core.services.oauth.base.settings.ENVIRONMENT",
            "development",
        ):
            result = OAuthStateManager.validate_callback_url(
                "https://any-site.com/callback"
            )
            assert result is True

    def test_validate_callback_url_production_requires_https(self):
        from app.core.services.oauth import OAuthStateManager

        with patch(
            "app.core.services.oauth.base.settings.CORS_ALLOW_ORIGINS",
            ["http://myapp.com", "https://myapp.com"],
        ), patch(
            "app.core.services.oauth.base.settings.ENVIRONMENT",
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
        from app.core.services.oauth import OAuthStateManager

        with patch(
            "app.core.services.oauth.base.settings.CORS_ALLOW_ORIGINS",
            ["http://localhost:3000"],
        ), patch(
            "app.core.services.oauth.base.settings.ENVIRONMENT",
            "development",
        ):
            result = OAuthStateManager.validate_callback_url(
                "http://localhost:3000/callback"
            )
            assert result is True

    def test_validate_callback_url_trailing_slash_handling(self):
        from app.core.services.oauth import OAuthStateManager

        with patch(
            "app.core.services.oauth.base.settings.CORS_ALLOW_ORIGINS",
            ["https://myapp.com/"],
        ), patch(
            "app.core.services.oauth.base.settings.ENVIRONMENT",
            "development",
        ):
            # Should match despite different trailing slash
            result = OAuthStateManager.validate_callback_url(
                "https://myapp.com/callback"
            )
            assert result is True


class TestOAuthStateManagerIntegration:

    def test_full_encode_decode_cycle(self):
        from app.core.services.oauth import OAuthStateManager

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
        from app.core.services.oauth import OAuthStateManager
        import re

        state = OAuthStateManager.encode_state(
            callback_url="https://example.com/path?query=value",
            remember_me=True,
        )

        # URL-safe characters: alphanumeric, hyphen, underscore, period, tilde
        # itsdangerous uses base64url encoding which includes - and _
        assert re.match(r"^[A-Za-z0-9_.\-]+$", state)


class TestModuleExports:

    def test_exports_from_oauth_package(self):
        from app.core.services.oauth import OAuthStateManager, OAuthStateData

        assert OAuthStateManager is not None
        assert OAuthStateData is not None

    def test_all_includes_state_manager(self):
        from app.core.services import oauth

        assert "OAuthStateManager" in oauth.__all__
        assert "OAuthStateData" in oauth.__all__

