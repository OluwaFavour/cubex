import asyncio
import random
from typing import Any

from fastapi import status as http_status
import httpx
from pydantic import BaseModel

from app.core.config import brevo_logger, settings
from app.core.exceptions.types import AppException


class Contact(BaseModel):
    email: str
    name: str | None = None


class ListContact(BaseModel):
    to: list[Contact]


class MessageVersion(BaseModel):

    to: list[Contact]
    htmlContent: str | None = None
    textContent: str | None = None
    subject: str | None = None
    params: dict[str, Any] | None = None


class ListMessageVersion(BaseModel):
    messageVersions: list[MessageVersion]


class BrevoService:
    _base_url: str = settings.BREVO_BASE_URL
    _api_key: str = settings.BREVO_API_KEY
    _sender_email: str = settings.BREVO_SENDER_EMAIL
    _sender_name: str = settings.BREVO_SENDER_NAME
    _client: httpx.AsyncClient | None = None

    # Bounded retries + backoff
    _BACKOFF_BASE: float = 3.0  # start with 3s
    _BACKOFF_MAX: float = 60.0  # cap at 60s
    _JITTER: float = 0.2  # +/-20%

    # Brevo API limits
    _MESSAGE_VERSION_BATCH_SIZE: int = 1000

    @classmethod
    def get_message_version_batch_size(cls) -> int:
        """
        Returns the maximum number of MessageVersion instances that can be sent in a single batch request.

        Returns:
            int: The maximum batch size for MessageVersion instances.
        """

        return cls._MESSAGE_VERSION_BATCH_SIZE

    @classmethod
    def _init_client(cls) -> None:
        """
        Initializes the Brevo HTTP client if it has not already been initialized.

        This method creates an asynchronous HTTP client with a specified base URL
        and timeout configuration. It ensures that the client is only initialized
        once and logs the initialization process.

        Returns:
            None
        """
        if cls._client is None:
            cls._client = httpx.AsyncClient(
                base_url=cls._base_url,
                timeout=httpx.Timeout(100.0),
            )
            brevo_logger.info("Brevo HTTP client initialized")

    @classmethod
    async def aclose(cls) -> None:
        """
        Asynchronously closes the Brevo HTTP client if it is initialized.

        This method ensures that the HTTP client is properly closed to release
        resources. It sets the client instance to `None` after closing and logs
        the closure event.

        Raises:
            Any exception raised during the closing of the HTTP client will be
            propagated.
        """
        if cls._client is not None:
            try:
                await cls._client.aclose()
            finally:
                cls._client = None
                brevo_logger.info("Brevo HTTP client closed")

    @classmethod
    async def init(
        cls,
        api_key: str | None = None,
        sender_email: str | None = None,
        sender_name: str | None = None,
    ) -> None:
        """
        Initializes the Brevo service with the provided configuration.

        This method sets the API key, sender email, and sender name for the Brevo
        service. If any of these parameters are not provided, their values remain
        unchanged. It also ensures that any existing client session is closed
        before initializing a new client.

        Args:
            api_key (str | None): The API key for authenticating requests. Defaults to None.
            sender_email (str | None): The email address of the sender. Defaults to None.
            sender_name (str | None): The name of the sender. Defaults to None.

        Returns:
            None
        """
        if api_key is not None:
            cls._api_key = api_key
        if sender_email is not None:
            cls._sender_email = sender_email
        if sender_name is not None:
            cls._sender_name = sender_name
        await cls.aclose()
        cls._init_client()

    @classmethod
    def _compute_backoff(
        cls, attempt: int, err_headers: httpx.Headers | None = None
    ) -> float:
        """
        Compute the backoff delay (in seconds) to use before retrying an operation.

        Parameters
        ----------
        cls : type
            The class object (used to access class-level constants such as
            _BACKOFF_BASE, _BACKOFF_MAX and _JITTER).
        attempt : int
            1-based retry attempt number. The exponential backoff base is computed as
            _BACKOFF_BASE * (2 ** (attempt - 1)) and then capped at _BACKOFF_MAX.
        err_headers : dict[str, str] | None, optional
            Optional mapping of error/response headers. If this mapping contains the
            key 'x-sib-ratelimit-reset', the function will try to parse its value as
            a float and return that value directly (interpreted as seconds to wait).
            If parsing fails or the header is not present, the computed exponential
            backoff with jitter is used.

        Returns
        -------
        float
            Delay in seconds to wait before the next retry.

        Notes
        -----
        - Jitter is applied multiplicatively: final_delay = base * jitter, where
          jitter is sampled uniformly from [1 - _JITTER, 1 + _JITTER].
        - The header name check is case-sensitive and expects the exact key
          'x-sib-ratelimit-reset'.
        - Header parse errors are handled silently by falling back to the computed
          backoff; no exception is raised by this function for header parsing.
        - Uses random.uniform to generate jitter, so results are non-deterministic.
        """
        if err_headers and "x-sib-ratelimit-reset" in err_headers:
            try:
                return float(err_headers.get("x-sib-ratelimit-reset"))
            except ValueError:
                pass  # Fall back to computed backoff if parsing fails
        base = min(cls._BACKOFF_BASE * (2 ** (attempt - 1)), cls._BACKOFF_MAX)
        jitter = random.uniform(1 - cls._JITTER, 1 + cls._JITTER)
        return base * jitter

    @classmethod
    def _auth_headers(cls, extra: dict[str, str] | None = None) -> dict[str, str]:
        """
        Generates authentication headers for API requests.

        Args:
            extra (dict[str, str] | None): Additional headers to include.

        Returns:
            dict[str, str]: A dictionary containing the authorization and content-type headers, merged with any extra headers provided.
        """
        headers = {
            "api-key": cls._api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if extra:
            headers.update(extra)
        return headers

    @classmethod
    async def _request(
        cls,
        method: str,
        endpoint: str,
        *,
        json: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        max_attempts: int = 3,
    ) -> dict[str, Any] | str:
        """
        Asynchronous class helper to perform an HTTP request to the Brevo API with retry/backoff logic,
        error handling and logging.
        Parameters
        ----------
        method : str
            HTTP method to use (e.g. "GET", "POST").
        endpoint : str
            URL or endpoint path to call with the configured HTTP client.
        json : dict[str, Any] | None, optional
            Optional JSON body to send with the request, by default None.
        headers : dict[str, str] | None, optional
            Optional headers to merge with authentication headers, by default None.
        max_attempts : int, optional
            Maximum number of attempts (initial try + retries), by default 3.
        Returns
        -------
        dict[str, Any] | str
            Parsed JSON response body when the response is valid JSON, otherwise the raw response text.
        Behavior
        --------
        - Ensures the class HTTP client (cls._client) is initialized via cls._init_client().
        - Sends the request using cls._client.request(...), combining provided headers with authentication headers
          obtained from cls._auth_headers(headers).
        - Attempts to parse the response as JSON; falls back to resp.text when JSON decoding fails.
        - Logs successful responses at info level via brevo_logger.
        Retry and error handling
        ------------------------
        - 5xx responses:
          - Considered transient; method will retry up to max_attempts using a backoff computed by
            cls._compute_backoff(attempt). If all attempts fail, raises AppException with the server status code.
        - 429 (rate limit):
          - Uses cls._compute_backoff(attempt, err_headers) to compute wait intervals (may use response headers).
          - Retries up to max_attempts; if exhausted, raises AppException with HTTP 429 status.
        - 4xx (other client errors):
          - Treated as non-retriable: logs and raises AppException immediately with the response body and status.
        - Network errors/timeouts (httpx.TimeoutException, httpx.TransportError):
          - Treated as transient; retries with backoff. If exhausted, raises AppException with a 503 status code.
        - All error logging attempts to safely extract and log the response body (JSON when possible, otherwise text).
        Exceptions
        ----------
        AppException
            Raised for HTTP client errors (4xx), when retries are exhausted for 5xx/429/network errors, or other
            conditions where the request cannot be fulfilled. Original httpx exceptions are chained where appropriate.
        Notes
        -----
        - Relies on the class providing:
          - cls._client and cls._init_client()
          - cls._auth_headers(headers)
          - cls._compute_backoff(attempt[, headers])
          - brevo_logger for logging
        - Does not mutate external state beyond logging.
        """
        if cls._client is None:
            cls._init_client()
        assert cls._client is not None

        attempts = max_attempts
        for attempt in range(1, attempts + 1):
            try:
                resp: httpx.Response = await cls._client.request(
                    method, endpoint, headers=cls._auth_headers(headers), json=json
                )
                resp.raise_for_status()
                try:
                    body = resp.json()
                except ValueError:
                    body = resp.text

                brevo_logger.info(f"Brevo response: {body}")
                return body

            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                # Safely extract error body for logs
                try:
                    err_body = exc.response.json()
                except ValueError:
                    err_body = exc.response.text

                if 500 <= status < 600:
                    wait = cls._compute_backoff(attempt)
                    brevo_logger.warning(
                        f"5xx from Brevo; attempt {attempt}/{attempts}; wait={wait:.1f}s; body={err_body}"
                    )
                    if attempt < attempts:
                        await asyncio.sleep(wait)
                        continue
                    brevo_logger.error(f"5xx error after retries: {status}: {err_body}")
                    raise AppException(
                        message=f"Server error after retries: {status}",
                        status_code=status,
                    ) from exc
                elif status == 429:
                    err_headers = exc.response.headers
                    wait = cls._compute_backoff(attempt, err_headers)
                    brevo_logger.warning(
                        f"Rate limited by Brevo; attempt {attempt}/{attempts}; wait={wait:.1f}s; body={err_body}"
                    )
                    if attempt < attempts:
                        await asyncio.sleep(wait)
                        continue
                    brevo_logger.error(
                        f"Rate limit error after retries: {status}: {err_body}"
                    )
                    raise AppException(
                        message="Brevo rate limit exceeded after retries",
                        status_code=http_status.HTTP_429_TOO_MANY_REQUESTS,
                    ) from exc

                brevo_logger.error(f"4xx error {status}: {err_body}")
                raise AppException(
                    message=f"HTTP error {status}: {err_body}", status_code=status
                ) from exc

            except (httpx.TimeoutException, httpx.TransportError) as exc:
                wait = cls._compute_backoff(attempt)
                brevo_logger.warning(
                    f"Timeout/transport error; attempt {attempt}/{attempts}; wait={wait:.1f}s; err={exc}"
                )
                if attempt < attempts:
                    await asyncio.sleep(wait)
                    continue
                brevo_logger.error(f"Network error after retries: {exc}")
                raise AppException(
                    message="Brevo network error after retries",
                    status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE,
                ) from exc

        # This should never be reached as all paths either return or raise
        raise AppException(
            message="Unexpected state: no response after all attempts",
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    @classmethod
    async def _handle_message_versions(
        cls,
        payload: dict[str, Any],
        messageVersions: ListMessageVersion,
    ) -> list[dict[str, Any] | str]:
        """
        Batch and send message versions per Brevo API limits.

        Args:
            payload: Base payload containing sender/subject/content shared across versions.
            messageVersions: ListMessageVersion container with MessageVersion items.

        Returns:
            list of responses from Brevo API (one per batch).

        Raises:
            ValueError: if the list is empty.
        """
        if not messageVersions.messageVersions:
            raise ValueError("messageVersions list cannot be empty")

        batch_size = cls.get_message_version_batch_size()
        batches = [
            ListMessageVersion(
                messageVersions=messageVersions.messageVersions[i : i + batch_size]
            )
            for i in range(0, len(messageVersions.messageVersions), batch_size)
        ]

        responses = await asyncio.gather(
            *[
                cls._request(
                    "POST",
                    "/smtp/email",
                    json={
                        **payload,
                        **batch.model_dump(exclude_none=True, exclude_unset=True),
                    },
                )
                for batch in batches
            ]
        )
        return list(responses)

    @classmethod
    async def send_transactional_email(
        cls,
        subject: str,
        sender: Contact | None = None,
        to: ListContact | None = None,
        messageVersions: ListMessageVersion | None = None,
        textContent: str | None = None,
        htmlContent: str | None = None,
    ) -> list[dict[str, Any] | str]:
        """
        Sends a transactional email via the Brevo API.

        Args:
            subject (str): Subject of the email.
            sender (Contact): Sender contact information.
            to (ListContact | None): List of recipient contacts. Defaults to None.
            messageVersions (ListMessageVersion | None): List of message versions. Defaults to None.
            textContent (str | None): Plain text content of the email. Defaults to None.
            htmlContent (str | None): HTML content of the email. Defaults to None.

        Returns:
            list[dict[str, Any] | str]: The list of responses from the Brevo API.
        """
        if not htmlContent and not textContent:
            raise ValueError("Either htmlContent or textContent must be provided")
        if not to and not messageVersions:
            raise ValueError("Either 'to' or 'messageVersions' must be provided")
        sender = sender or Contact(email=cls._sender_email, name=cls._sender_name)
        sender_data = sender.model_dump(exclude_none=True, exclude_unset=True)
        payload = {
            "sender": sender_data,
            "subject": subject,
        }
        if textContent:
            payload["textContent"] = textContent
        if htmlContent:
            payload["htmlContent"] = htmlContent
        if to:
            payload.update(to.model_dump(exclude_none=True, exclude_unset=True))

        if messageVersions:
            return await cls._handle_message_versions(payload, messageVersions)

        response = await cls._request(
            method="POST",
            endpoint="/smtp/email",
            json=payload,
        )
        return [response]
