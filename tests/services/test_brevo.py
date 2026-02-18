"""
Test suite for BrevoService email service.

This module contains comprehensive tests for the Brevo email service including:
- Client initialization and cleanup
- Authentication and headers
- Retry logic with exponential backoff
- Rate limiting and error handling
- Transactional email sending (single and batch)
- Message version handling

Run all tests:
    pytest app/tests/services/test_brevo.py -v

Run with coverage:
    pytest app/tests/services/test_brevo.py --cov=app.core.services.brevo --cov-report=term-missing -v
"""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi import status as http_status

from app.core.services.brevo import (
    BrevoService,
    Contact,
    ListContact,
    ListMessageVersion,
    MessageVersion,
)
from app.core.exceptions.types import AppException


class TestBrevoServiceInit:
    """Test suite for BrevoService initialization and cleanup."""

    @pytest.fixture(autouse=True)
    async def cleanup(self):
        """Cleanup fixture to ensure client is closed after each test."""
        yield
        await BrevoService.aclose()

    def test_get_message_version_batch_size(self):
        """Test getting message version batch size constant."""
        batch_size = BrevoService.get_message_version_batch_size()
        assert batch_size == 1000
        assert isinstance(batch_size, int)

    def test_init_client_creates_new_client(self):
        """Test that _init_client creates a new httpx.AsyncClient."""
        # Ensure client is None initially
        BrevoService._client = None

        BrevoService._init_client()

        assert BrevoService._client is not None
        assert isinstance(BrevoService._client, httpx.AsyncClient)
        # httpx adds trailing slash to base_url
        assert str(BrevoService._client.base_url).rstrip(
            "/"
        ) == BrevoService._base_url.rstrip("/")

    def test_init_client_only_initializes_once(self):
        """Test that _init_client doesn't reinitialize if client exists."""
        BrevoService._init_client()
        first_client = BrevoService._client

        BrevoService._init_client()
        second_client = BrevoService._client

        # Should be the same instance
        assert first_client is second_client

    @pytest.mark.asyncio
    async def test_aclose_closes_client(self):
        """Test that aclose properly closes the client."""
        BrevoService._init_client()
        assert BrevoService._client is not None

        await BrevoService.aclose()

        assert BrevoService._client is None

    @pytest.mark.asyncio
    async def test_aclose_when_client_is_none(self):
        """Test that aclose handles None client gracefully."""
        BrevoService._client = None

        # Should not raise any exception
        await BrevoService.aclose()

        assert BrevoService._client is None

    @pytest.mark.asyncio
    async def test_init_updates_configuration(self):
        """Test that init updates service configuration."""
        original_api_key = BrevoService._api_key
        original_sender_email = BrevoService._sender_email
        original_sender_name = BrevoService._sender_name

        new_api_key = "test-api-key-123"
        new_sender_email = "test@example.com"
        new_sender_name = "Test Sender"

        await BrevoService.init(
            api_key=new_api_key,
            sender_email=new_sender_email,
            sender_name=new_sender_name,
        )

        assert BrevoService._api_key == new_api_key
        assert BrevoService._sender_email == new_sender_email
        assert BrevoService._sender_name == new_sender_name
        assert BrevoService._client is not None

        # Restore original values
        BrevoService._api_key = original_api_key
        BrevoService._sender_email = original_sender_email
        BrevoService._sender_name = original_sender_name

    @pytest.mark.asyncio
    async def test_init_partial_update(self):
        """Test that init only updates provided parameters."""
        original_api_key = BrevoService._api_key
        original_sender_email = BrevoService._sender_email
        original_sender_name = BrevoService._sender_name

        new_api_key = "new-key"

        await BrevoService.init(api_key=new_api_key)

        assert BrevoService._api_key == new_api_key
        assert BrevoService._sender_email == original_sender_email  # Unchanged
        assert BrevoService._sender_name == original_sender_name  # Unchanged

        # Restore
        BrevoService._api_key = original_api_key


class TestBrevoServiceBackoff:
    """Test suite for backoff calculation logic."""

    def test_compute_backoff_first_attempt(self):
        """Test backoff calculation for first retry attempt."""
        backoff = BrevoService._compute_backoff(attempt=1, err_headers=None)

        # First attempt: base * jitter
        # base = min(3.0 * 2^0, 60.0) = 3.0
        # jitter = random in [0.8, 1.2]
        # result = 3.0 * jitter
        assert 2.4 <= backoff <= 3.6

    def test_compute_backoff_second_attempt(self):
        """Test backoff calculation for second retry attempt."""
        backoff = BrevoService._compute_backoff(attempt=2, err_headers=None)

        # Second attempt: base = min(3.0 * 2^1, 60.0) = 6.0
        # result = 6.0 * jitter
        assert 4.8 <= backoff <= 7.2

    def test_compute_backoff_max_capped(self):
        """Test that backoff is capped at maximum value."""
        # Large attempt number should hit the cap
        backoff = BrevoService._compute_backoff(attempt=10, err_headers=None)

        # base = min(3.0 * 2^9, 60.0) = min(1536, 60) = 60.0
        # result = 60.0 * jitter (0.8 to 1.2)
        assert 48.0 <= backoff <= 72.0

    def test_compute_backoff_with_rate_limit_header(self):
        """Test backoff uses rate limit header when available."""
        headers = httpx.Headers({"x-sib-ratelimit-reset": "15.5"})

        backoff = BrevoService._compute_backoff(attempt=1, err_headers=headers)

        # Should use the header value directly
        assert backoff == 15.5

    def test_compute_backoff_with_invalid_header(self):
        """Test backoff falls back to computed value with invalid header."""
        headers = httpx.Headers({"x-sib-ratelimit-reset": "invalid"})

        backoff = BrevoService._compute_backoff(attempt=1, err_headers=headers)

        # Should fall back to computed backoff
        assert 2.4 <= backoff <= 3.6


class TestBrevoServiceAuthHeaders:
    """Test suite for authentication headers generation."""

    def test_auth_headers_default(self):
        """Test auth headers with no extra headers."""
        headers = BrevoService._auth_headers()

        assert headers["api-key"] == BrevoService._api_key
        assert headers["Content-Type"] == "application/json"
        assert headers["Accept"] == "application/json"
        assert len(headers) == 3

    def test_auth_headers_with_extra(self):
        """Test auth headers merge with extra headers."""
        extra = {"X-Custom-Header": "custom-value"}

        headers = BrevoService._auth_headers(extra)

        assert headers["api-key"] == BrevoService._api_key
        assert headers["Content-Type"] == "application/json"
        assert headers["Accept"] == "application/json"
        assert headers["X-Custom-Header"] == "custom-value"
        assert len(headers) == 4

    def test_auth_headers_extra_overrides(self):
        """Test that extra headers can override default headers."""
        extra = {"Content-Type": "text/plain"}

        headers = BrevoService._auth_headers(extra)

        assert headers["Content-Type"] == "text/plain"


class TestBrevoServiceRequest:
    """Test suite for HTTP request handling with retry logic."""

    @pytest.fixture(autouse=True)
    async def cleanup(self):
        """Cleanup fixture."""
        yield
        await BrevoService.aclose()

    @pytest.mark.asyncio
    async def test_request_successful(self):
        """Test successful HTTP request."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"messageId": "123"}
        mock_response.raise_for_status = MagicMock()

        with patch.object(BrevoService, "_init_client"), patch.object(
            BrevoService, "_client"
        ) as mock_client:
            mock_client.request = AsyncMock(return_value=mock_response)

            result = await BrevoService._request(
                "POST", "/smtp/email", json={"test": "data"}
            )

            assert result == {"messageId": "123"}
            mock_client.request.assert_called_once()

    @pytest.mark.asyncio
    async def test_request_initializes_client_if_none(self):
        """Test that request initializes client if not already initialized."""
        # Store original and set to None
        original_client = BrevoService._client
        BrevoService._client = None

        try:
            mock_response = MagicMock()
            mock_response.json.return_value = {"success": True}
            mock_response.raise_for_status = MagicMock()

            mock_client_instance = AsyncMock()
            mock_client_instance.request = AsyncMock(return_value=mock_response)

            with patch.object(BrevoService, "_init_client") as mock_init:
                # Set up mock to actually set the client
                def init_side_effect():
                    BrevoService._client = mock_client_instance

                mock_init.side_effect = init_side_effect

                await BrevoService._request("GET", "/test")

                mock_init.assert_called_once()
        finally:
            BrevoService._client = original_client

    @pytest.mark.asyncio
    async def test_request_returns_text_when_json_fails(self):
        """Test that request returns text when JSON parsing fails."""
        mock_response = MagicMock()
        mock_response.json.side_effect = ValueError("Not JSON")
        mock_response.text = "plain text response"
        mock_response.raise_for_status = MagicMock()

        with patch.object(BrevoService, "_init_client"), patch.object(
            BrevoService, "_client"
        ) as mock_client:
            mock_client.request = AsyncMock(return_value=mock_response)

            result = await BrevoService._request("GET", "/test")

            assert result == "plain text response"

    @pytest.mark.asyncio
    async def test_request_retries_on_5xx_error(self):
        """Test that request retries on 5xx server errors."""
        mock_response = MagicMock()
        mock_response.status_code = 503
        mock_response.json.return_value = {"error": "Service unavailable"}

        error = httpx.HTTPStatusError(
            "Server error", request=MagicMock(), response=mock_response
        )

        with patch.object(BrevoService, "_init_client"), patch.object(
            BrevoService, "_client"
        ) as mock_client, patch("asyncio.sleep", new_callable=AsyncMock):
            mock_client.request = AsyncMock(side_effect=error)

            with pytest.raises(AppException) as exc_info:
                await BrevoService._request("POST", "/test", max_attempts=3)

            assert exc_info.value.status_code == 503
            assert "Server error after retries" in exc_info.value.message
            assert mock_client.request.call_count == 3  # Initial + 2 retries

    @pytest.mark.asyncio
    async def test_request_retries_on_429_rate_limit(self):
        """Test that request retries on 429 rate limit errors."""
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.headers = httpx.Headers({})
        mock_response.json.return_value = {"error": "Rate limited"}

        error = httpx.HTTPStatusError(
            "Rate limit", request=MagicMock(), response=mock_response
        )

        with patch.object(BrevoService, "_init_client"), patch.object(
            BrevoService, "_client"
        ) as mock_client, patch("asyncio.sleep", new_callable=AsyncMock):
            mock_client.request = AsyncMock(side_effect=error)

            with pytest.raises(AppException) as exc_info:
                await BrevoService._request("POST", "/test", max_attempts=2)

            assert exc_info.value.status_code == http_status.HTTP_429_TOO_MANY_REQUESTS
            assert "rate limit exceeded" in exc_info.value.message.lower()
            assert mock_client.request.call_count == 2

    @pytest.mark.asyncio
    async def test_request_no_retry_on_4xx_client_error(self):
        """Test that request doesn't retry on 4xx client errors."""
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.json.return_value = {"error": "Bad request"}

        error = httpx.HTTPStatusError(
            "Bad request", request=MagicMock(), response=mock_response
        )

        with patch.object(BrevoService, "_init_client"), patch.object(
            BrevoService, "_client"
        ) as mock_client:
            mock_client.request = AsyncMock(side_effect=error)

            with pytest.raises(AppException) as exc_info:
                await BrevoService._request("POST", "/test", max_attempts=3)

            assert exc_info.value.status_code == 400
            assert mock_client.request.call_count == 1  # No retries

    @pytest.mark.asyncio
    async def test_request_retries_on_timeout(self):
        """Test that request retries on timeout errors."""
        with patch.object(BrevoService, "_init_client"), patch.object(
            BrevoService, "_client"
        ) as mock_client, patch("asyncio.sleep", new_callable=AsyncMock):
            mock_client.request = AsyncMock(
                side_effect=httpx.TimeoutException("Timeout")
            )

            with pytest.raises(AppException) as exc_info:
                await BrevoService._request("GET", "/test", max_attempts=2)

            assert (
                exc_info.value.status_code == http_status.HTTP_503_SERVICE_UNAVAILABLE
            )
            assert "network error" in exc_info.value.message.lower()
            assert mock_client.request.call_count == 2

    @pytest.mark.asyncio
    async def test_request_retries_on_transport_error(self):
        """Test that request retries on transport errors."""
        with patch.object(BrevoService, "_init_client"), patch.object(
            BrevoService, "_client"
        ) as mock_client, patch("asyncio.sleep", new_callable=AsyncMock):
            mock_client.request = AsyncMock(
                side_effect=httpx.TransportError("Network error")
            )

            with pytest.raises(AppException) as exc_info:
                await BrevoService._request("GET", "/test", max_attempts=2)

            assert (
                exc_info.value.status_code == http_status.HTTP_503_SERVICE_UNAVAILABLE
            )
            assert mock_client.request.call_count == 2

    @pytest.mark.asyncio
    async def test_request_uses_text_on_json_error_in_exception(self):
        """Test that request uses text when JSON parsing fails in error response."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.json.side_effect = ValueError("Not JSON")
        mock_response.text = "Server error text"

        error = httpx.HTTPStatusError(
            "Server error", request=MagicMock(), response=mock_response
        )

        with patch.object(BrevoService, "_init_client"), patch.object(
            BrevoService, "_client"
        ) as mock_client, patch("asyncio.sleep", new_callable=AsyncMock):
            mock_client.request = AsyncMock(side_effect=error)

            with pytest.raises(AppException):
                await BrevoService._request("POST", "/test", max_attempts=1)


class TestBrevoServiceMessageVersions:
    """Test suite for message version handling."""

    @pytest.fixture(autouse=True)
    async def cleanup(self):
        """Cleanup fixture."""
        yield
        await BrevoService.aclose()

    @pytest.mark.asyncio
    async def test_handle_message_versions_single_batch(self):
        """Test handling message versions within single batch limit."""
        message_versions = ListMessageVersion(
            messageVersions=[
                MessageVersion(
                    to=[Contact(email=f"user{i}@example.com")],
                    subject="Test",
                    htmlContent="<p>Test</p>",
                )
                for i in range(10)  # Well under 1000 limit
            ]
        )

        payload = {"sender": {"email": "sender@example.com"}, "subject": "Test"}

        with patch.object(
            BrevoService, "_request", new_callable=AsyncMock
        ) as mock_request:
            mock_request.return_value = {"messageId": "123"}

            results = await BrevoService._handle_message_versions(
                payload, message_versions
            )

            assert len(results) == 1
            assert results[0] == {"messageId": "123"}
            mock_request.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_message_versions_multiple_batches(self):
        """Test handling message versions split into multiple batches."""
        # Create 2500 message versions (will split into 3 batches: 1000, 1000, 500)
        message_versions = ListMessageVersion(
            messageVersions=[
                MessageVersion(
                    to=[Contact(email=f"user{i}@example.com")],
                    subject="Test",
                    htmlContent="<p>Test</p>",
                )
                for i in range(2500)
            ]
        )

        payload = {"sender": {"email": "sender@example.com"}, "subject": "Test"}

        with patch.object(
            BrevoService, "_request", new_callable=AsyncMock
        ) as mock_request:
            mock_request.return_value = {"messageId": "123"}

            results = await BrevoService._handle_message_versions(
                payload, message_versions
            )

            assert len(results) == 3  # 3 batches
            assert mock_request.call_count == 3

    @pytest.mark.asyncio
    async def test_handle_message_versions_empty_list_raises_error(self):
        """Test that empty message versions list raises ValueError."""
        message_versions = ListMessageVersion(messageVersions=[])
        payload = {"sender": {"email": "sender@example.com"}}

        with pytest.raises(ValueError, match="messageVersions list cannot be empty"):
            await BrevoService._handle_message_versions(payload, message_versions)


class TestBrevoServiceSendTransactionalEmail:
    """Test suite for sending transactional emails."""

    @pytest.fixture(autouse=True)
    async def cleanup(self):
        """Cleanup fixture."""
        yield
        await BrevoService.aclose()

    @pytest.mark.asyncio
    async def test_send_email_with_html_content(self):
        """Test sending email with HTML content."""
        with patch.object(
            BrevoService, "_request", new_callable=AsyncMock
        ) as mock_request:
            mock_request.return_value = {"messageId": "test-123"}

            result = await BrevoService.send_transactional_email(
                subject="Test Subject",
                to=ListContact(to=[Contact(email="recipient@example.com")]),
                htmlContent="<h1>Test Email</h1>",
            )

            assert len(result) == 1
            assert result[0] == {"messageId": "test-123"}

            # Verify request was called with correct payload
            mock_request.assert_called_once()
            call_args = mock_request.call_args
            # Access kwargs directly
            assert call_args.kwargs["method"] == "POST"
            assert call_args.kwargs["endpoint"] == "/smtp/email"
            json_data = call_args.kwargs["json"]
            assert json_data["subject"] == "Test Subject"
            assert json_data["htmlContent"] == "<h1>Test Email</h1>"
            assert "to" in json_data

    @pytest.mark.asyncio
    async def test_send_email_with_text_content(self):
        """Test sending email with text content."""
        with patch.object(
            BrevoService, "_request", new_callable=AsyncMock
        ) as mock_request:
            mock_request.return_value = {"messageId": "test-456"}

            result = await BrevoService.send_transactional_email(
                subject="Test Subject",
                to=ListContact(to=[Contact(email="recipient@example.com")]),
                textContent="Plain text email",
            )

            assert len(result) == 1
            json_data = mock_request.call_args[1]["json"]
            assert json_data["textContent"] == "Plain text email"

    @pytest.mark.asyncio
    async def test_send_email_with_custom_sender(self):
        """Test sending email with custom sender."""
        custom_sender = Contact(email="custom@example.com", name="Custom Sender")

        with patch.object(
            BrevoService, "_request", new_callable=AsyncMock
        ) as mock_request:
            mock_request.return_value = {"messageId": "test-789"}

            await BrevoService.send_transactional_email(
                subject="Test",
                sender=custom_sender,
                to=ListContact(to=[Contact(email="recipient@example.com")]),
                htmlContent="<p>Test</p>",
            )

            json_data = mock_request.call_args[1]["json"]
            assert json_data["sender"]["email"] == "custom@example.com"
            assert json_data["sender"]["name"] == "Custom Sender"

    @pytest.mark.asyncio
    async def test_send_email_uses_default_sender(self):
        """Test that email uses default sender when not provided."""
        with patch.object(
            BrevoService, "_request", new_callable=AsyncMock
        ) as mock_request:
            mock_request.return_value = {"messageId": "test"}

            await BrevoService.send_transactional_email(
                subject="Test",
                to=ListContact(to=[Contact(email="recipient@example.com")]),
                htmlContent="<p>Test</p>",
            )

            json_data = mock_request.call_args[1]["json"]
            assert json_data["sender"]["email"] == BrevoService._sender_email
            assert json_data["sender"]["name"] == BrevoService._sender_name

    @pytest.mark.asyncio
    async def test_send_email_with_message_versions(self):
        """Test sending email with message versions."""
        message_versions = ListMessageVersion(
            messageVersions=[
                MessageVersion(
                    to=[Contact(email="user1@example.com")],
                    htmlContent="<p>Version 1</p>",
                ),
                MessageVersion(
                    to=[Contact(email="user2@example.com")],
                    htmlContent="<p>Version 2</p>",
                ),
            ]
        )

        with patch.object(
            BrevoService, "_handle_message_versions", new_callable=AsyncMock
        ) as mock_handle:
            mock_handle.return_value = [{"messageId": "1"}, {"messageId": "2"}]

            result = await BrevoService.send_transactional_email(
                subject="Test",
                messageVersions=message_versions,
                htmlContent="<p>Default</p>",
            )

            assert len(result) == 2
            mock_handle.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_email_raises_error_without_content(self):
        """Test that sending email without content raises ValueError."""
        with pytest.raises(
            ValueError, match="Either htmlContent or textContent must be provided"
        ):
            await BrevoService.send_transactional_email(
                subject="Test",
                to=ListContact(to=[Contact(email="recipient@example.com")]),
            )

    @pytest.mark.asyncio
    async def test_send_email_raises_error_without_recipients(self):
        """Test that sending email without recipients raises ValueError."""
        with pytest.raises(
            ValueError, match="Either 'to' or 'messageVersions' must be provided"
        ):
            await BrevoService.send_transactional_email(
                subject="Test", htmlContent="<p>Test</p>"
            )

    @pytest.mark.asyncio
    async def test_send_email_with_both_html_and_text(self):
        """Test sending email with both HTML and text content."""
        with patch.object(
            BrevoService, "_request", new_callable=AsyncMock
        ) as mock_request:
            mock_request.return_value = {"messageId": "test"}

            await BrevoService.send_transactional_email(
                subject="Test",
                to=ListContact(to=[Contact(email="recipient@example.com")]),
                htmlContent="<h1>HTML</h1>",
                textContent="Plain text",
            )

            json_data = mock_request.call_args[1]["json"]
            assert json_data["htmlContent"] == "<h1>HTML</h1>"
            assert json_data["textContent"] == "Plain text"


class TestBrevoServiceModels:
    """Test suite for Pydantic models."""

    def test_contact_model_with_name(self):
        """Test Contact model with name."""
        contact = Contact(email="test@example.com", name="Test User")

        assert contact.email == "test@example.com"
        assert contact.name == "Test User"

    def test_contact_model_without_name(self):
        """Test Contact model without name (optional)."""
        contact = Contact(email="test@example.com")

        assert contact.email == "test@example.com"
        assert contact.name is None

    def test_list_contact_model(self):
        """Test ListContact model."""
        contacts = ListContact(
            to=[
                Contact(email="user1@example.com", name="User 1"),
                Contact(email="user2@example.com"),
            ]
        )

        assert len(contacts.to) == 2
        assert contacts.to[0].email == "user1@example.com"
        assert contacts.to[1].name is None

    def test_message_version_model_full(self):
        """Test MessageVersion model with all fields."""
        message = MessageVersion(
            to=[Contact(email="test@example.com")],
            htmlContent="<p>Test</p>",
            textContent="Test",
            subject="Subject",
            params={"key": "value"},
        )

        assert len(message.to) == 1
        assert message.htmlContent == "<p>Test</p>"
        assert message.textContent == "Test"
        assert message.subject == "Subject"
        assert message.params == {"key": "value"}

    def test_message_version_model_minimal(self):
        """Test MessageVersion model with minimal fields."""
        message = MessageVersion(to=[Contact(email="test@example.com")])

        assert len(message.to) == 1
        assert message.htmlContent is None
        assert message.textContent is None
        assert message.subject is None
        assert message.params is None

    def test_list_message_version_model(self):
        """Test ListMessageVersion model."""
        list_mv = ListMessageVersion(
            messageVersions=[
                MessageVersion(to=[Contact(email="user1@example.com")]),
                MessageVersion(to=[Contact(email="user2@example.com")]),
            ]
        )

        assert len(list_mv.messageVersions) == 2
