import asyncio
from decimal import Decimal
import os
import random
from typing import Any, Literal

import httpx
import stripe as stripe_sdk
from fastapi import status as http_status


from app.shared.config import settings, stripe_logger
from app.shared.exceptions.types import (
    AppException,
    IdempotencyException,
    RateLimitException,
    StripeAPIException,
    StripeCardException,
)
from app.shared.services.payment.stripe.types import (
    BillingPortalSession,
    CheckoutSession,
    CreatedParams,
    CurrencyOptionsCustomUnitAmountEnabled,
    Customer,
    CustomUnitAmountEnabled,
    DeleteResponse,
    Invoice,
    InvoiceListResponse,
    LineItem,
    PaymentIntentData,
    Price,
    PriceListResponse,
    Product,
    ProductData,
    ProductListResponse,
    Recurring,
    RecurringWithoutCount,
    Subscription,
    SubscriptionData,
    Tier,
)


class Stripe:
    _api_key: str = settings.STRIPE_API_KEY or os.getenv("STRIPE_API_KEY") or ""
    _base_url: str = settings.STRIPE_API_BASE_URL or "https://api.stripe.com"
    _webhook_secret: str = (
        settings.STRIPE_WEBHOOK_SECRET or os.getenv("STRIPE_WEBHOOK_SECRET") or ""
    )
    _client: httpx.AsyncClient | None = None

    # Bounded retries + backoff
    _BACKOFF_BASE: float = 10.0  # start with 10s
    _BACKOFF_MAX: float = 60.0  # cap at 60s
    _JITTER: float = 0.2  # +/-20%

    @staticmethod
    def _flatten_to_payload(
        payload: dict[str, Any],
        prefix: str,
        data: dict[str, Any],
        *,
        max_depth: int = 3,
        _current_depth: int = 0,
    ) -> None:
        """
        Flatten a nested dict into Stripe's form-encoded format.

        Recursively converts nested dictionaries into bracket notation keys
        that Stripe's API expects for form-encoded requests.

        Example:
            data = {"metadata": {"user_id": "123", "plan_id": "456"}}
            prefix = "subscription_data"
            Result: payload["subscription_data[metadata][user_id]"] = "123"
                    payload["subscription_data[metadata][plan_id]"] = "456"

        Parameters
        ----------
        payload : dict[str, Any]
            The payload dict to add flattened keys to.
        prefix : str
            The base key prefix (e.g., "subscription_data", "metadata").
        data : dict[str, Any]
            The dict to flatten.
        max_depth : int, optional
            Maximum nesting depth to prevent infinite recursion. Defaults to 3.
        _current_depth : int
            Internal counter for recursion depth. Do not set manually.
        """
        if _current_depth >= max_depth:
            # Safety limit reached, convert remaining value to string
            for key, value in data.items():
                payload[f"{prefix}[{key}]"] = str(value) if value is not None else ""
            return

        for key, value in data.items():
            full_key = f"{prefix}[{key}]"
            if isinstance(value, dict):
                # Recurse into nested dict
                Stripe._flatten_to_payload(
                    payload,
                    full_key,
                    value,
                    max_depth=max_depth,
                    _current_depth=_current_depth + 1,
                )
            elif isinstance(value, list):
                # Handle lists (e.g., line_items, tiers)
                for idx, item in enumerate(value):
                    if isinstance(item, dict):
                        Stripe._flatten_to_payload(
                            payload,
                            f"{full_key}[{idx}]",
                            item,
                            max_depth=max_depth,
                            _current_depth=_current_depth + 1,
                        )
                    else:
                        payload[f"{full_key}[{idx}]"] = (
                            str(item) if item is not None else ""
                        )
            else:
                payload[full_key] = str(value) if value is not None else ""

    @classmethod
    def _check_api_key(cls) -> None:
        """Validate that a Stripe API key has been configured.

        This helper checks that the class attribute `cls._api_key` is a non-empty,
        non-whitespace string. It performs no network calls; it only ensures the
        configuration value is present and appears valid.

        Raises
        ------
            ValueError
                If the API key is missing or contains only whitespace. The API
                key is expected to be provided via the STRIPE_API_KEY environment
                variable or a .env file.
        """
        if not cls._api_key.strip():
            raise ValueError(
                "Stripe API key is not set. Please set STRIPE_API_KEY in the environment variables or .env file."
            )

    @classmethod
    def _check_webhook_secret(cls) -> None:
        if not cls._webhook_secret.strip():
            raise ValueError(
                "Stripe Webhook Secret is not set. Please set STRIPE_WEBHOOK_SECRET in the environment variables or .env file."
            )

    @classmethod
    def _init_client(cls) -> None:
        """Initialize the asynchronous HTTP client used to communicate with Stripe.

        This method ensures an API key is present by calling cls._check_api_key() and
        lazily constructs an httpx.AsyncClient configured for the Stripe API. If an
        HTTP client has already been created (cls._client is not None), the method
        is a no-op (idempotent).

        Side effects
        ------
        - May raise whatever exception(s) cls._check_api_key() raises when the API key
          is missing or invalid.
        - Sets cls._client to a newly created httpx.AsyncClient with:
                - base_url from cls._base_url
                - timeout of 100 seconds
                - BasicAuth using cls._api_key and an empty password
        - Logs an informational message that the client was initialized.

        Notes
        -----
        - The caller is responsible for closing the AsyncClient (e.g., await cls._client.aclose())
          when it is no longer needed.
        - This method is not inherently thread-safe; synchronize externally if it may be
          raced by concurrent callers.
        """
        cls._check_api_key()
        cls._check_webhook_secret()
        if cls._client is None:
            cls._client = httpx.AsyncClient(
                base_url=cls._base_url,
                timeout=httpx.Timeout(100.0),
                auth=httpx.BasicAuth(cls._api_key, ""),
            )
            stripe_logger.info("Stripe HTTP client initialized")

    @classmethod
    def _compute_backoff(cls, attempt: int) -> float:
        """
        Compute the backoff time with jitter for a given retry attempt.

        This method calculates an exponential backoff time with a capped maximum
        value and applies a random jitter to avoid synchronized retries.

        Parameters
        ----------
            attempt : int
                The current retry attempt number (1-based).

        Returns
        -------
            float
                The computed backoff time in seconds.
        """
        base = min(cls._BACKOFF_BASE * (2 ** (attempt - 1)), cls._BACKOFF_MAX)
        jitter = random.uniform(1 - cls._JITTER, 1 + cls._JITTER)
        return base * jitter

    @classmethod
    async def _request(
        cls,
        method: str,
        endpoint: str,
        headers: dict[str, str] | None = None,
        *,
        data: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        max_attempts: int = 3,
    ) -> dict[str, Any] | str:
        """
        Makes an asynchronous HTTP request to the Stripe API with retry logic.

        Implements production-grade error handling following Stripe's best practices:
        - Retries 5xx errors (server errors) with exponential backoff
        - Retries 429 (rate limiting) with exponential backoff
        - Does NOT retry 4xx errors (except 429) as they indicate client errors
        - Extracts and logs Request-Id for debugging with Stripe support
        - Maps Stripe error types to appropriate exception classes
        - Handles idempotency conflicts (409) separately

        Parameters
        ----------
            method : str
                The HTTP method to use (e.g., 'GET', 'POST', 'DELETE').
            endpoint : str
                The API endpoint to send the request to.
            data : dict[str, Any] | None, optional
                Form-encoded payload to include in the request body. Defaults to None.
            headers : dict[str, str] | None, optional
                Additional headers to include in the request. Defaults to None.
            params : dict[str, Any] | None, optional
                Query parameters for GET requests. Defaults to None.
            max_attempts : int, optional
                The maximum number of retry attempts for retryable errors. Defaults to 3.

        Returns
        -------
            dict[str, Any] | str
                The response body as a dictionary if JSON-decoded successfully, otherwise as a string.

        Raises
        ------
            StripeCardException
                For card_error type errors (declined cards, etc.)
            IdempotencyException
                For idempotency_error type errors (409 conflicts)
            RateLimitException
                For rate limiting errors after all retries exhausted
            StripeAPIException
                For other Stripe API errors with structured error details
            AppException
                For network errors or 5xx errors after all retries exhausted

        Notes
        -----
            - Request-Id is extracted from response headers for debugging
            - Stripe error structure: {error: {type, code, message, param, ...}}
            - Only 5xx and 429 errors are retried; all 4xx errors fail immediately
            - Idempotency keys should be provided by callers for safe retries
        """
        if cls._client is None:
            cls._init_client()

        # Assert client is initialized (for type checker)
        assert cls._client is not None, "HTTP client should be initialized"

        for attempt in range(1, max_attempts + 1):
            try:
                resp: httpx.Response = await cls._client.request(
                    method, endpoint, data=data, headers=headers, params=params
                )
                resp.raise_for_status()

                # Parse response body
                try:
                    body = resp.json()
                except ValueError:
                    body = resp.text

                stripe_logger.info(
                    f"Stripe {method} {endpoint} succeeded (Request-Id: {resp.headers.get('Request-Id', 'N/A')})"
                )
                return body

            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                request_id = exc.response.headers.get("Request-Id")

                # Safely extract error body
                try:
                    err_body = exc.response.json()
                except ValueError:
                    err_body = {"error": {"message": exc.response.text}}

                # Extract Stripe error details
                error_data = err_body.get("error", {})
                error_type = error_data.get("type")
                error_code = error_data.get("code")
                error_message = error_data.get("message", f"Stripe API error {status}")
                error_param = error_data.get("param")
                decline_code = error_data.get("decline_code")

                # Log with Request-Id for Stripe support debugging
                stripe_logger.error(
                    f"Stripe error: {status} {error_type or 'unknown'} | "
                    f"Code: {error_code or 'N/A'} | Request-Id: {request_id or 'N/A'} | "
                    f"Message: {error_message}"
                )

                # Handle retryable errors: 5xx and 429
                if 500 <= status < 600:
                    # Server errors - retry with exponential backoff
                    wait = cls._compute_backoff(attempt)
                    stripe_logger.warning(
                        f"5xx from Stripe; attempt {attempt}/{max_attempts}; "
                        f"wait={wait:.1f}s; Request-Id={request_id}"
                    )
                    if attempt < max_attempts:
                        await asyncio.sleep(wait)
                        continue

                    # Exhausted retries
                    stripe_logger.error(
                        f"5xx error after {max_attempts} attempts. Request-Id: {request_id}"
                    )
                    raise StripeAPIException(
                        message=error_message,
                        status_code=status,
                        stripe_code=error_code,
                        error_type=error_type or "api_error",
                        request_id=request_id,
                        details=err_body,
                    ) from exc

                elif status == 429:
                    # Rate limiting - retry with exponential backoff
                    wait = cls._compute_backoff(attempt)
                    stripe_logger.warning(
                        f"Rate limited by Stripe; attempt {attempt}/{max_attempts}; "
                        f"wait={wait:.1f}s; Request-Id={request_id}"
                    )
                    if attempt < max_attempts:
                        await asyncio.sleep(wait)
                        continue

                    # Exhausted retries
                    stripe_logger.error(
                        f"Rate limit exceeded after {max_attempts} attempts. Request-Id: {request_id}"
                    )
                    raise RateLimitException(
                        message=error_message or "Too many requests to Stripe API",
                        details={
                            "code": error_code,
                            "type": error_type or "rate_limit_error",
                            "request_id": request_id,
                            **err_body,
                        },
                    ) from exc

                # Non-retryable 4xx errors - handle based on error type
                # https://docs.stripe.com/api/errors

                if status == 409 or error_type == "idempotency_error":
                    # Idempotency conflict - caller reused key with different params
                    raise IdempotencyException(
                        message=error_message
                        or "Idempotency key was used with different parameters",
                        request_id=request_id,
                        details={
                            "code": error_code,
                            "type": error_type,
                            "param": error_param,
                            **err_body,
                        },
                    ) from exc

                elif error_type == "card_error":
                    # Card was declined or invalid
                    # These are user-facing errors that can be shown to customers
                    raise StripeCardException(
                        message=error_message,
                        stripe_code=error_code,
                        decline_code=decline_code,
                        param=error_param,
                        request_id=request_id,
                        details=err_body,
                    ) from exc

                elif error_type == "invalid_request_error":
                    # Invalid parameters, authentication, or resource not found
                    # 400: Bad Request - missing required parameter
                    # 401: Unauthorized - invalid API key
                    # 404: Not Found - resource doesn't exist
                    raise StripeAPIException(
                        message=error_message,
                        status_code=status,
                        stripe_code=error_code,
                        error_type=error_type,
                        param=error_param,
                        request_id=request_id,
                        details=err_body,
                    ) from exc

                elif status == 402:
                    # Request Failed - parameters valid but request failed
                    # Common for failed charges
                    raise StripeAPIException(
                        message=error_message,
                        status_code=status,
                        stripe_code=error_code,
                        error_type=error_type or "request_failed",
                        param=error_param,
                        request_id=request_id,
                        details=err_body,
                    ) from exc

                elif status == 403:
                    # Forbidden - API key lacks permissions
                    raise StripeAPIException(
                        message=error_message
                        or "API key doesn't have permission for this operation",
                        status_code=status,
                        stripe_code=error_code,
                        error_type=error_type or "permission_error",
                        request_id=request_id,
                        details=err_body,
                    ) from exc

                elif status == 424:
                    # External Dependency Failed - rare, failure in external system
                    stripe_logger.error(
                        f"External dependency failed. Request-Id: {request_id}"
                    )
                    raise StripeAPIException(
                        message=error_message or "External dependency failed",
                        status_code=status,
                        stripe_code=error_code,
                        error_type=error_type or "external_dependency_failed",
                        request_id=request_id,
                        details=err_body,
                    ) from exc

                else:
                    # Generic 4xx or unknown error
                    raise StripeAPIException(
                        message=error_message,
                        status_code=status,
                        stripe_code=error_code,
                        error_type=error_type or "api_error",
                        param=error_param,
                        request_id=request_id,
                        details=err_body,
                    ) from exc

            except (httpx.TimeoutException, httpx.TransportError) as exc:
                # Network/connectivity errors - retry with exponential backoff
                wait = cls._compute_backoff(attempt)
                stripe_logger.warning(
                    f"Network error; attempt {attempt}/{max_attempts}; "
                    f"wait={wait:.1f}s; error={exc.__class__.__name__}: {exc}"
                )
                if attempt < max_attempts:
                    await asyncio.sleep(wait)
                    continue

                # Exhausted retries
                stripe_logger.error(
                    f"Network error after {max_attempts} attempts: {exc}"
                )
                raise AppException(
                    message="Unable to connect to Stripe. Please try again later.",
                    status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE,
                    details={"error": str(exc), "type": "network_error"},
                ) from exc

        # This should never be reached due to the logic above
        raise AppException(
            message="Unexpected error in Stripe request loop",
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    @classmethod
    async def aclose(cls) -> None:
        """Asynchronously close the underlying HTTP client.

        This method checks if the class-level HTTP client (cls._client) has been
        initialized. If it has, it calls the client's aclose() coroutine to properly
        close any open connections and release resources. After closing, it sets
        cls._client to None.

        Side effects
        ------
        - Closes the httpx.AsyncClient if it was initialized.
        - Sets cls._client to None.

        Notes
        -----
        - This method should be called when the Stripe service is no longer needed
          to ensure proper cleanup of resources.
        """
        if cls._client is not None:
            await cls._client.aclose()
            cls._client = None
            stripe_logger.info("Stripe HTTP client closed")

    @classmethod
    def verify_webhook_signature(
        cls, body: bytes, headers: dict[str, str]
    ) -> stripe_sdk.Event:
        """Verify the signature of a Stripe webhook event.

        This method uses the Stripe SDK to verify the signature of a webhook event
        received from Stripe. It checks the provided request body and headers against
        the configured webhook secret.

        Parameters
        ----------
        body : bytes
            The raw request body of the webhook event.
        headers : dict[str, str]
            The headers of the webhook request, which should include the 'Stripe-Signature'.

        Returns
        -------
        stripe_sdk.Event
            The verified Stripe Event object.

        Raises
        ------
        ValueError
            If the webhook secret is not configured.
        AppException
            If verification fails.
        """
        cls._check_webhook_secret()
        try:
            event = stripe_sdk.Webhook.construct_event(
                payload=body,
                sig_header=headers.get("Stripe-Signature", ""),
                secret=cls._webhook_secret,
            )
            return event
        except stripe_sdk.SignatureVerificationError as exc:
            stripe_logger.error(f"Webhook signature verification failed: {exc}")
            raise AppException(
                message="Invalid Stripe webhook signature.",
                status_code=http_status.HTTP_400_BAD_REQUEST,
            ) from exc

    @classmethod
    async def get_product(cls, product_id: str) -> Product:
        """Asynchronously retrieve a Stripe Product by ID.

        Fetches the product resource from Stripe's API (GET /v1/products/{product_id})
        using the class' _request coroutine, and returns a validated Product model.

        Parameters
        ----------
        product_id : str
            The Stripe product identifier (e.g. "prod_ABC123").

        Returns
        -------
        Product
            A Product model instance validated via Product.model_validate().

        Raises
        ------
        Any exception raised by the underlying _request coroutine (e.g. network or
        API errors). Model validation errors may also be raised if the response
        cannot be converted into a Product instance.
        """
        endpoint = f"/v1/products/{product_id}"
        body = await cls._request("GET", endpoint)
        return Product.model_validate(body)

    @classmethod
    async def list_products(
        cls,
        *,
        active: bool | None = None,
        created: CreatedParams | dict[str, int] | None = None,
        ending_before: str | None = None,
        ids: list[str] | None = None,
        limit: int = 10,
        shippable: bool | None = None,
        starting_after: str | None = None,
        url: str | None = None,
    ) -> ProductListResponse:
        """
        Asynchronously retrieve a list of products from the Stripe API.

        This method issues a GET request to the "/v1/products" endpoint using the
        provided query parameters, validates the response using ProductListResponse,
        and returns the validated model.

        Parameters
        ----------
        active : bool | None
            If set, filter products by their active status.
        created : CreatedParams | dict[str, int] | None
            A map of filters for the product creation timestamp (e.g. {"gte": 1609459200}).
            Possible keys: "gt", "gte", "lt", "lte".
        ending_before : str | None
            A cursor for pagination. Return objects occurring before this ID.
        ids : list[str] | None
            A list of specific product IDs to include in the response.
        limit : int
            Maximum number of products to return (pagination limit).
            Default is 10 and valid range is 1 to 100.
        shippable : bool | None
            If set, filter products by their shippable property.
        starting_after : str | None
            A cursor for pagination. Return objects occurring after this ID.
        url : str | None
            Filter products that have the given URL.

        Returns
        -------
        ProductListResponse
            A validated response model containing the list of products and pagination metadata.

        Raises
        ------
        Exception
            Propagates exceptions raised by the underlying HTTP request or by model validation.
        """
        endpoint = "/v1/products"
        params: dict[str, Any] = {"limit": limit}
        if active is not None:
            params["active"] = active
        if created is not None:
            if isinstance(created, CreatedParams):
                created = created.model_dump(exclude_unset=True)
            params["created"] = created
        if ending_before is not None:
            params["ending_before"] = ending_before
        if ids is not None:
            params["ids"] = ids
        if shippable is not None:
            params["shippable"] = shippable
        if starting_after is not None:
            params["starting_after"] = starting_after
        if url is not None:
            params["url"] = url
        body = await cls._request("GET", endpoint, params=params)
        return ProductListResponse.model_validate(body)

    @classmethod
    async def create_product(
        cls,
        name: str,
        *,
        idempotency_key: str | None = None,
        id: str | None = None,
        active: bool = True,
        description: str | None = None,
        metadata: dict[str, Any] | None = None,
        tax_code: str | None = None,
    ) -> Product:
        """
        Asynchronously create a Stripe Product by sending a POST request to the Stripe
        API (/v1/products) and return the validated Product model.
        This method builds the request payload from the provided arguments and, if an
        idempotency key is supplied, includes it in the request headers to ensure safe
        retries. The response body is validated and converted to a Product instance by
        Product.model_validate before being returned.

        Parameters
        ----------
        name : str
            The name of the product to create (required).
        idempotency_key : str | None, optional
            Idempotency key to include in the request headers. When provided, the
            Stripe API will use this key to make the request idempotent.
        id : str | None, optional
            Optional custom identifier for the product.
        active : bool, optional
            Whether the product should be created as active. Defaults to True.
        description : str | None, optional
            Short description of the product.
        metadata : dict[str, Any] | None, optional
            Additional key/value metadata to attach to the product.
        tax_code : str | None, optional
            Tax code identifier to associate with the product.

        Returns
        -------
        Product
            A Product model instance representing the created Stripe product as
            validated by Product.model_validate.

        Raises
        ------
        Exception
            Propagates exceptions raised by cls._request (e.g., network/HTTP or Stripe
            API errors) and by Product.model_validate (validation errors). The exact
            exception types depend on the underlying HTTP client and model validation
            implementation.
        """
        endpoint = "/v1/products"
        payload: dict[str, Any] = {
            "name": name,
            "active": active,
        }
        if id is not None:
            payload["id"] = id
        if description is not None:
            payload["description"] = description
        if metadata is not None:
            cls._flatten_to_payload(payload, "metadata", metadata)
        if tax_code is not None:
            payload["tax_code"] = tax_code

        headers: dict[str, str] = {}
        if idempotency_key is not None:
            headers["Idempotency-Key"] = idempotency_key

        body = await cls._request("POST", endpoint, data=payload, headers=headers)
        return Product.model_validate(body)

    @classmethod
    async def update_product(
        cls,
        product_id: str,
        *,
        idempotency_key: str | None = None,
        name: str | None = None,
        active: bool | None = None,
        description: str | None = None,
        default_price: str | None = None,
        metadata: dict[str, Any] | None = None,
        tax_code: str | None = None,
    ) -> Product:
        """
        Update a Stripe Product.

        Sends a POST request to the Stripe API to update the product with the given
        product_id. Only parameters that are provided and evaluate to truthy values
        will be included in the request payload. If an idempotency_key is provided,
        it will be sent in the "Idempotency-Key" request header.

        Parameters
        ----------
        product_id : str
            The Stripe product ID to update (used in the endpoint path).
        idempotency_key : str | None, optional
            Idempotency key to ensure the operation is performed only once by Stripe.
        name : str | None, optional
            New name for the product.
        active : bool | None, optional
            Whether the product should be active.
        description : str | None, optional
            Product description.
        default_price : str | None, optional
            ID of an existing Price object to set as the product's default price.
        metadata : dict[str, Any] | None, optional
            A dictionary of key/value pairs to attach to the product as metadata.
        tax_code : str | None, optional
            The tax code ID to associate with the product.

        Returns
        -------
        Product
            A validated Product model instance created from the Stripe API response.

        Raises
        ------
        Exception
            Propagates exceptions raised by cls._request for HTTP/transport errors,
            and by Product.model_validate if the response cannot be validated into
            a Product instance.

        Notes
        -----
        - The request is performed against the endpoint: /v1/products/{product_id}
          using HTTP POST.
        """
        endpoint = f"/v1/products/{product_id}"
        payload: dict[str, Any] = {}
        if name is not None:
            payload["name"] = name
        if active is not None:
            payload["active"] = active
        if description is not None:
            payload["description"] = description
        if default_price is not None:
            payload["default_price"] = default_price
        if metadata is not None:
            cls._flatten_to_payload(payload, "metadata", metadata)
        if tax_code is not None:
            payload["tax_code"] = tax_code

        headers: dict[str, str] = {}
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key

        body = await cls._request("POST", endpoint, data=payload, headers=headers)
        return Product.model_validate(body)

    @classmethod
    async def delete_product(cls, product_id: str) -> DeleteResponse:
        """
        Delete a Stripe product by ID.

        Sends a DELETE request to the Stripe API for the product identified by
        `product_id` and returns a parsed DeleteResponse model representing the
        result of the deletion. Deleting a product is only possible if it has no
        prices associated with it. Additionally, deleting a product with type=good
        is only possible if it has no SKUs associated with it.

        Parameters
        ----------
        product_id : str
            The Stripe product identifier (e.g. "prod_...").

        Returns
        -------
        DeleteResponse
            A validated model containing the deletion status and any
            additional data returned by Stripe.

        Raises
        ------
        Exception
            Propagates exceptions raised by the underlying request helper
            (e.g., network errors, HTTP errors) and validation errors if the response
            cannot be parsed into DeleteResponse.

        Example
        -------
        ```python
        await SomeService.delete_product("prod_ABC123")
        ```
        """
        endpoint = f"/v1/products/{product_id}"
        body = await cls._request("DELETE", endpoint)
        return DeleteResponse.model_validate(body)

    @classmethod
    async def get_price(cls, price_id: str) -> Price:
        """Asynchronously retrieve a Stripe Price by ID.

        Fetches the price resource from Stripe's API (GET /v1/prices/{price_id})
        using the class' _request coroutine, and returns a validated Price model.

        Parameters
        ----------
        price_id : str
            The Stripe price identifier (e.g. "price_ABC123").

        Returns
        -------
        Price
            A Price model instance validated via Price.model_validate().

        Raises
        ------
        Any exception raised by the underlying _request coroutine (e.g. network or
        API errors). Model validation errors may also be raised if the response
        cannot be converted into a Price instance.
        """
        endpoint = f"/v1/prices/{price_id}"
        body = await cls._request("GET", endpoint)
        return Price.model_validate(body)

    @classmethod
    async def list_prices(
        cls,
        *,
        active: bool | None = None,
        currency: str | None = None,
        product: str | None = None,
        type: Literal["one_time", "recurring"] | None = None,
        created: CreatedParams | dict[str, int] | None = None,
        ending_before: str | None = None,
        limit: int = 10,
        lookup_keys: list[str] | None = None,
        recurring: RecurringWithoutCount | dict[str, Any] | None = None,
        starting_after: str | None = None,
    ) -> PriceListResponse:
        """
        Asynchronously retrieve a list of prices from the Stripe API.

        This method issues a GET request to the "/v1/prices" endpoint using the
        provided query parameters, validates the response using Price,
        and returns the validated models.

        Parameters
        ----------
        active : bool | None
            If set, filter prices by their active status.
        currency : str | None
            If set, filter prices by the specified currency (e.g. "usd").
        product : str | None
            If set, filter prices by the associated product ID.
        type : Literal["one_time", "recurring"] | None
            If set, filter prices by their type.
        created : CreatedParams | dict[str, int] | None
            A map of filters for the price creation timestamp (e.g. {"gte": 1609459200}).
            Possible keys: "gt", "gte", "lt", "lte".
        ending_before : str | None
            A cursor for pagination. Return objects occurring before this ID.
        limit : int
            Maximum number of prices to return (pagination limit).
            Default is 10 and valid range is 1 to 100.
        lookup_keys : list[str] | None
            A list of lookup keys to filter prices by. Maximum of 10 keys.
        recurring : RecurringWithoutCount | dict[str, Any] | None
            A map of filters for the recurring price attributes.
            Possible keys: "interval", "meter", "usage_type".
        starting_after : str | None
            A cursor for pagination. Return objects occurring after this ID.

        Returns
        -------
        PriceListResponse
            A list of validated Price model instances.

        Raises
        ------
        Exception
            Propagates exceptions raised by the underlying HTTP request or by model validation.
        """
        endpoint = "/v1/prices"
        params: dict[str, Any] = {"limit": limit}
        if active is not None:
            params["active"] = active
        if currency is not None:
            params["currency"] = currency
        if type is not None:
            params["type"] = type
        if created is not None:
            if isinstance(created, CreatedParams):
                created = created.model_dump(exclude_unset=True)
            params["created"] = created
        if ending_before is not None:
            params["ending_before"] = ending_before
        if lookup_keys is not None:
            params["lookup_keys"] = lookup_keys
        if recurring is not None:
            if isinstance(recurring, RecurringWithoutCount):
                recurring = recurring.model_dump(exclude_unset=True)
            params["recurring"] = recurring
        if product is not None:
            params["product"] = product
        if starting_after is not None:
            params["starting_after"] = starting_after
        body = await cls._request("GET", endpoint, params=params)
        return PriceListResponse.model_validate(body)

    @classmethod
    async def create_price(
        cls,
        product: str,
        currency: str,
        *,
        idempotency_key: str | None = None,
        active: bool = True,
        product_data: ProductData | dict[str, Any] | None = None,
        billing_scheme: Literal["per_unit", "tiered"] | None = None,
        tiers: list[Tier] | list[dict[str, Any]] | None = None,
        tiers_mode: Literal["graduated", "volume"] | None = None,
        unit_amount: int | None = None,
        unit_amount_decimal: Decimal | None = None,
        custom_unit_amount: CustomUnitAmountEnabled | dict[str, Any] | None = None,
        nickname: str | None = None,
        recurring: Recurring | dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        tax_behavior: Literal["inclusive", "exclusive", "unspecified"] | None = None,
    ) -> Price:
        """
        Asynchronously create a Stripe Price by sending a POST request to the Stripe
        API (/v1/prices) and return the validated Price model.
        This method builds the request payload from the provided arguments and, if an
        idempotency key is supplied, includes it in the request headers to ensure safe
        retries. The response body is validated and converted to a Price instance by
        Price.model_validate before being returned.

        Parameters
        ----------
        product : str
            The ID of the product this price belongs to (required).
        currency : str
            Three-letter ISO currency code (e.g., "usd") (required).
        idempotency_key : str | None, optional
            Idempotency key to include in the request headers. When provided, the
            Stripe API will use this key to make the request idempotent.
        active : bool, optional
            Whether the price should be created as active. Defaults to True.
        product_data : ProductData | dict[str, Any] | None, optional
            A map of product data to create a new product when creating the price.
        billing_scheme : Literal["per_unit", "tiered"] | None, optional
            Describes how to compute the price per period. Either 'per_unit' or 'tiered'.
        tiers : list[Tier] | list[dict[str, Any]] | None, optional
            A list of tiers for tiered pricing.
        tiers_mode : Literal["graduated", "volume"] | None, optional
            Specifies the type of tiering price calculation to use.
        unit_amount : int
            The amount to be charged, in the smallest currency unit (e.g., cents) (required).
        unit_amount_decimal : Decimal | None, optional
            The amount to be charged, in decimal format.
        custom_unit_amount : CustomUnitAmountEnabled | dict[str, Any] | None, optional
            Configure custom unit amounts for this price.
        nickname : str | None, optional
            A brief description of the price.
        recurring : Recurring | None, optional
            The recurring billing details for this price. Required if type is 'recurring'.
        metadata : dict[str, Any] | None, optional
            Additional key/value metadata to attach to the price.
        tax_behavior : Literal["inclusive", "exclusive", "unspecified"] | None, optional
            Specifies whether the price is considered inclusive of taxes or exclusive of taxes.

        Returns
        -------
        Price
            A Price model instance representing the created Stripe price as
            validated by Price.model_validate.

        Raises
        ------
        Exception
            Propagates exceptions raised by the underlying _request (e.g., network/HTTP
            or Stripe API errors) and by Price.model_validate (validation errors).
        """
        endpoint = "/v1/prices"
        payload: dict[str, Any] = {
            "product": product,
            "currency": currency,
            "active": active,
        }
        if product_data is not None:
            if isinstance(product_data, ProductData):
                product_data = product_data.model_dump(exclude_unset=True)
            cls._flatten_to_payload(payload, "product_data", product_data)
        if billing_scheme is not None:
            payload["billing_scheme"] = billing_scheme
        if tiers is not None:
            # Convert Tier objects to dicts
            tiers_list: list[dict[str, Any]] = [
                tier.model_dump(exclude_unset=True) if isinstance(tier, Tier) else tier
                for tier in tiers
            ]
            for idx, tier in enumerate(tiers_list):
                cls._flatten_to_payload(payload, f"tiers[{idx}]", tier)
        if tiers_mode is not None:
            payload["tiers_mode"] = tiers_mode
        if unit_amount is not None:
            payload["unit_amount"] = unit_amount
        if unit_amount_decimal is not None:
            payload["unit_amount_decimal"] = str(unit_amount_decimal)
        if custom_unit_amount is not None:
            if isinstance(custom_unit_amount, CustomUnitAmountEnabled):
                custom_unit_amount = custom_unit_amount.model_dump(exclude_unset=True)
            cls._flatten_to_payload(payload, "custom_unit_amount", custom_unit_amount)
        if nickname is not None:
            payload["nickname"] = nickname
        if recurring is not None:
            if isinstance(recurring, Recurring):
                recurring = recurring.model_dump(exclude_unset=True)
            cls._flatten_to_payload(payload, "recurring", recurring)
        if metadata is not None:
            cls._flatten_to_payload(payload, "metadata", metadata)
        if tax_behavior is not None:
            payload["tax_behavior"] = tax_behavior

        headers: dict[str, str] = {}
        if idempotency_key is not None:
            headers["Idempotency-Key"] = idempotency_key

        body = await cls._request("POST", endpoint, data=payload, headers=headers)
        return Price.model_validate(body)

    @classmethod
    async def update_price(
        cls,
        price_id: str,
        *,
        idempotency_key: str | None = None,
        active: bool | None = None,
        nickname: str | None = None,
        metadata: dict[str, Any] | None = None,
        tax_behavior: Literal["inclusive", "exclusive", "unspecified"] | None = None,
        currency_options: (
            dict[str, CurrencyOptionsCustomUnitAmountEnabled | Any] | None
        ) = None,
    ) -> Price:
        """
        Update a Stripe Price.

        Sends a POST request to the Stripe API to update the price with the given
        price_id. Only parameters that are provided and evaluate to truthy values
        will be included in the request payload. If an idempotency_key is provided,
        it will be sent in the "Idempotency-Key" request header.

        Parameters
        ----------
        price_id : str
            The Stripe price ID to update (used in the endpoint path).
        idempotency_key : str | None, optional
            Idempotency key to ensure the operation is performed only once by Stripe.
        active : bool | None, optional
            Whether the price should be active.
        nickname : str | None, optional
            Price nickname.
        metadata : dict[str, Any] | None, optional
            A dictionary of key/value pairs to attach to the price as metadata.
        tax_behavior : Literal["inclusive", "exclusive", "unspecified"] | None, optional
            Specifies whether the price is considered inclusive of taxes or exclusive of taxes.
        currency_options : dict[str, CurrencyOptionsCustomUnitAmountEnabled | Any] | None, optional
            A map of currency-specific options for the price.

        Returns
        -------
        Price
            A validated Price model instance created from the Stripe API response.

        Raises
        ------
        Exception
            Propagates exceptions raised by cls._request for HTTP/transport errors,
            and by Price.model_validate if the response cannot be validated into
            a Price instance.

        Notes
        -----
        - The request is performed against the endpoint: /v1/prices/{price_id}
          using HTTP POST.
        """
        endpoint = f"/v1/prices/{price_id}"
        payload: dict[str, Any] = {}
        if active is not None:
            payload["active"] = active
        if nickname is not None:
            payload["nickname"] = nickname
        if metadata is not None:
            cls._flatten_to_payload(payload, "metadata", metadata)
        if tax_behavior is not None:
            payload["tax_behavior"] = tax_behavior
        if currency_options is not None:
            # Flatten currency_options for form-encoded request
            for currency, options in currency_options.items():
                options_dict: dict[str, Any]
                if isinstance(options, CurrencyOptionsCustomUnitAmountEnabled):
                    options_dict = options.model_dump(exclude_unset=True)
                elif isinstance(options, dict):
                    options_dict = options
                else:
                    continue
                cls._flatten_to_payload(
                    payload, f"currency_options[{currency}]", options_dict
                )

        headers: dict[str, str] = {}
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        body = await cls._request("POST", endpoint, data=payload, headers=headers)
        return Price.model_validate(body)

    @classmethod
    async def create_checkout_session(
        cls,
        success_url: str,
        cancel_url: str,
        line_items: list[LineItem] | list[dict[str, Any]],
        *,
        idempotency_key: str | None = None,
        mode: Literal["payment", "setup", "subscription"] = "payment",
        customer: str | None = None,
        customer_email: str | None = None,
        payment_method_types: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        subscription_data: SubscriptionData | dict[str, Any] | None = None,
        payment_intent_data: PaymentIntentData | dict[str, Any] | None = None,
    ) -> CheckoutSession:
        """
        Create a Stripe Checkout Session.

        Sends a POST request to the Stripe API to create a new checkout session
        with the specified parameters. If an idempotency_key is provided, it will
        be included in the request headers to ensure the operation is idempotent.

        Parameters
        ----------
        success_url : str
            The URL to which the customer will be redirected after a successful payment.
        cancel_url : str
            The URL to which the customer will be redirected if they cancel the payment.
        line_items : list[LineItem] | list[dict[str, Any]]
            A list of line items to be included in the checkout session.
        idempotency_key : str | None, optional
            Idempotency key to ensure the operation is performed only once by Stripe.
        mode : Literal["payment", "setup", "subscription"], optional
            The mode of the checkout session. Defaults to "payment".
        customer : str | None, optional
            The ID of an existing customer to associate with the session.
        customer_email : str | None, optional
            The email address of the customer.
        payment_method_types : list[str] | None, optional
            A list of payment method types to be used in the session.
        metadata : dict[str, Any] | None, optional
            A dictionary of key/value pairs to attach to the session as metadata.
        subscription_data : SubscriptionData | dict[str, Any] | None, optional
            Additional data for subscription mode sessions.
        payment_intent_data : PaymentIntentData | dict[str, Any] | None, optional
            Additional data for payment intent creation.

        Returns
        -------
        CheckoutSession
            A validated CheckoutSession model instance created from the Stripe API response.

        Raises
        ------
        Exception
            Propagates exceptions raised by cls._request for HTTP/transport errors,
            and by CheckoutSession.model_validate if the response cannot be validated
            into a CheckoutSession instance.
        """
        endpoint = "/v1/checkout/sessions"
        payload: dict[str, Any] = {
            "success_url": success_url,
            "cancel_url": cancel_url,
            "mode": mode,
        }

        # Flatten line_items for form-encoded request
        for idx, item in enumerate(line_items):
            if isinstance(item, LineItem):
                item = item.model_dump(exclude_unset=True)
            if isinstance(item, dict):
                cls._flatten_to_payload(payload, f"line_items[{idx}]", item)

        if customer is not None:
            payload["customer"] = customer
        if customer_email is not None:
            payload["customer_email"] = customer_email
        if payment_method_types is not None:
            payload["payment_method_types"] = payment_method_types
        if metadata is not None:
            cls._flatten_to_payload(payload, "metadata", metadata)
        if subscription_data is not None:
            if isinstance(subscription_data, SubscriptionData):
                subscription_data = subscription_data.model_dump(exclude_unset=True)
            cls._flatten_to_payload(payload, "subscription_data", subscription_data)
        if payment_intent_data is not None:
            if isinstance(payment_intent_data, PaymentIntentData):
                payment_intent_data = payment_intent_data.model_dump(exclude_unset=True)
            cls._flatten_to_payload(payload, "payment_intent_data", payment_intent_data)
        headers: dict[str, str] = {}
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        body = await cls._request("POST", endpoint, data=payload, headers=headers)
        return CheckoutSession.model_validate(body)

    @classmethod
    async def get_subscription(cls, subscription_id: str) -> Subscription:
        """Asynchronously retrieve a Stripe Subscription by ID.

        Fetches the subscription resource from Stripe's API (GET /v1/subscriptions/{subscription_id})
        using the class' _request coroutine, and returns a validated Subscription model.

        Parameters
        ----------
        subscription_id : str
            The Stripe subscription identifier (e.g. "sub_ABC123").

        Returns
        -------
        Subscription
            A Subscription model instance validated via Subscription.model_validate().

        Raises
        ------
        Any exception raised by the underlying _request coroutine (e.g. network or
        API errors). Model validation errors may also be raised if the response
        cannot be converted into a Subscription instance.
        """
        endpoint = f"/v1/subscriptions/{subscription_id}"
        body = await cls._request("GET", endpoint)
        return Subscription.model_validate(body)

    @classmethod
    async def cancel_subscription(
        cls,
        subscription_id: str,
        *,
        cancel_at_period_end: bool = False,
        prorate: bool = False,
        invoice_now: bool = False,
    ) -> Subscription:
        """Cancel a Stripe subscription immediately or at period end.

        This method cancels an active subscription. By default, it cancels immediately,
        but you can configure it to cancel at the end of the current billing period.

        Parameters
        ----------
        subscription_id : str
            The Stripe subscription identifier to cancel.
        cancel_at_period_end : bool, optional
            If True, the subscription will remain active until the end of the current
            billing period. If False (default), cancels immediately.
        prorate : bool, optional
            Whether to prorate the cancellation. If True, creates a proration invoice item.
            Default is False.
        invoice_now : bool, optional
            Whether to immediately generate an invoice for any outstanding charges.
            Default is False.

        Returns
        -------
        Subscription
            The updated Subscription object with canceled status.

        Raises
        ------
        Any exception raised by the underlying _request coroutine.
        """
        endpoint = f"/v1/subscriptions/{subscription_id}"

        if cancel_at_period_end:
            # Update subscription to cancel at period end
            payload = {
                "cancel_at_period_end": True,
                "proration_behavior": "create_prorations" if prorate else "none",
            }
            body = await cls._request("POST", endpoint, data=payload)
        else:
            # Cancel immediately
            payload = {
                "prorate": prorate,
                "invoice_now": invoice_now,
            }
            body = await cls._request("DELETE", endpoint, data=payload)

        return Subscription.model_validate(body)

    @classmethod
    async def update_subscription(
        cls,
        subscription_id: str,
        *,
        idempotency_key: str | None = None,
        new_price_id: str | None = None,
        quantity: int | None = None,
        seat_price_id: str | None = None,
        new_seat_price_id: str | None = None,
        metadata: dict[str, str] | None = None,
        default_payment_method: str | None = None,
        trial_end: int | Literal["now"] | None = None,
        cancel_at_period_end: bool | None = None,
        proration_behavior: Literal[
            "create_prorations", "none", "always_invoice"
        ] = "create_prorations",
        proration_date: int | None = None,
    ) -> Subscription:
        """Update a Stripe subscription.

        Modifies an existing subscription with new properties like metadata,
        payment method, trial period, cancellation settings, price/plan, or quantity.

        Parameters
        ----------
        subscription_id : str
            The Stripe subscription identifier to update.
        idempotency_key : str, optional
            Idempotency key to ensure the operation is performed only once by Stripe.
        new_price_id : str, optional
            New price ID to change the subscription plan/price.
            This will update the subscription items to use the new price.
        quantity : int, optional
            New quantity (seat count) for the subscription item.
            Updates the quantity on the seat item if seat_price_id is provided,
            otherwise updates the first subscription item.
        seat_price_id : str, optional
            Price ID of the seat item to update quantity for.
            Use this for subscriptions with base + seat pricing (dual line items).
            If provided, quantity updates will target the item matching this price ID.
        new_seat_price_id : str, optional
            New price ID for the seat item during plan upgrades.
            Use this when upgrading plans to change the seat pricing along with the base plan.
            The seat item is identified by seat_price_id and updated to new_seat_price_id.
        metadata : dict[str, str], optional
            Custom key-value pairs to attach to the subscription.
        default_payment_method : str, optional
            ID of the payment method to set as default.
        trial_end : int | Literal["now"], optional
            Unix timestamp for when the trial should end, or "now" to end immediately.
        cancel_at_period_end : bool, optional
            Whether to cancel at the end of the current period.
        proration_behavior : Literal["create_prorations", "none", "always_invoice"], optional
            How to handle proration when changes affect billing.
            Default is "create_prorations".
        proration_date : int, optional
            Unix timestamp for backdating the proration calculation.
            If not provided, uses current time.

        Returns
        -------
        Subscription
            The updated Subscription object.

        Raises
        ------
        StripeAPIException
            If the Stripe API request fails.
        Any exception raised by the underlying _request coroutine.
        """
        # If changing price or quantity, need to update subscription items
        if (
            new_price_id is not None
            or quantity is not None
            or new_seat_price_id is not None
        ):
            # First, get the current subscription to find the subscription item ID
            subscription = await cls.get_subscription(subscription_id)

            items = subscription.items
            items_data = items.data

            payload: dict[str, Any] = {
                "proration_behavior": proration_behavior,
            }

            item_index = 0

            # Handle base plan price change (first item or item not matching seat_price_id)
            if new_price_id is not None:
                # Find the base plan item (not the seat item)
                base_item = None
                for item in items_data:
                    if seat_price_id is None or item.price.id != seat_price_id:
                        base_item = item
                        break
                if base_item is None:
                    base_item = items_data[0]

                payload[f"items[{item_index}][id]"] = base_item.id
                payload[f"items[{item_index}][price]"] = new_price_id
                item_index += 1

            # Handle seat item updates (quantity change or price change)
            if (
                seat_price_id is not None and quantity is not None
            ) or new_seat_price_id is not None:
                # Find the seat item by current seat_price_id
                seat_item = None
                for item in items_data:
                    if seat_price_id is not None and item.price.id == seat_price_id:
                        seat_item = item
                        break

                if seat_item is not None:
                    payload[f"items[{item_index}][id]"] = seat_item.id
                    if new_seat_price_id is not None:
                        payload[f"items[{item_index}][price]"] = new_seat_price_id
                    if quantity is not None:
                        payload[f"items[{item_index}][quantity]"] = quantity
                    item_index += 1
                elif quantity is not None and new_price_id is None:
                    # Fallback: if no seat item found and only updating quantity, use first item
                    payload[f"items[{item_index}][id]"] = items_data[0].id
                    payload[f"items[{item_index}][quantity]"] = quantity
                    item_index += 1

            # Handle quantity-only updates (no seat_price_id provided)
            elif (
                quantity is not None and seat_price_id is None and new_price_id is None
            ):
                # Update quantity on first item when no specific seat item is targeted
                payload[f"items[{item_index}][id]"] = items_data[0].id
                payload[f"items[{item_index}][quantity]"] = quantity
                item_index += 1

            if proration_date is not None:
                payload["proration_date"] = proration_date
        else:
            # Regular update without price/quantity change
            payload: dict[str, Any] = {
                "proration_behavior": proration_behavior,
            }

        if metadata is not None:
            payload["metadata"] = metadata
        if default_payment_method is not None:
            payload["default_payment_method"] = default_payment_method
        if trial_end is not None:
            payload["trial_end"] = trial_end
        if cancel_at_period_end is not None:
            payload["cancel_at_period_end"] = cancel_at_period_end

        endpoint = f"/v1/subscriptions/{subscription_id}"
        headers = {}
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        body = await cls._request("POST", endpoint, data=payload, headers=headers)
        return Subscription.model_validate(body)

    @classmethod
    async def pause_subscription(
        cls,
        subscription_id: str,
        *,
        resumes_at: int | None = None,
    ) -> Subscription:
        """Pause a Stripe subscription.

        Pauses the subscription and optionally schedules when it should resume.

        Parameters
        ----------
        subscription_id : str
            The Stripe subscription identifier to pause.
        resumes_at : int, optional
            Unix timestamp when the subscription should automatically resume.
            If None, the subscription remains paused indefinitely.

        Returns
        -------
        Subscription
            The updated Subscription object with paused status.

        Raises
        ------
        Any exception raised by the underlying _request coroutine.
        """
        endpoint = f"/v1/subscriptions/{subscription_id}"

        payload: dict[str, Any] = {
            "pause_collection": {
                "behavior": "void",
            }
        }

        if resumes_at is not None:
            payload["pause_collection"]["resumes_at"] = resumes_at

        body = await cls._request("POST", endpoint, data=payload)
        return Subscription.model_validate(body)

    @classmethod
    async def resume_subscription(cls, subscription_id: str) -> Subscription:
        """Resume a paused Stripe subscription.

        Removes the pause collection setting to resume normal billing.

        Parameters
        ----------
        subscription_id : str
            The Stripe subscription identifier to resume.

        Returns
        -------
        Subscription
            The updated Subscription object with active status.

        Raises
        ------
        Any exception raised by the underlying _request coroutine.
        """
        endpoint = f"/v1/subscriptions/{subscription_id}"

        payload = {
            "pause_collection": "",  # Empty string clears the pause
        }

        body = await cls._request("POST", endpoint, data=payload)
        return Subscription.model_validate(body)

    @classmethod
    async def preview_invoice(
        cls,
        subscription_id: str,
        new_price_id: str,
        *,
        proration_behavior: Literal[
            "create_prorations", "none", "always_invoice"
        ] = "create_prorations",
        proration_date: int | None = None,
    ) -> Invoice:
        """Preview the prorated invoice for a subscription plan change.

        Simulates changing a subscription's price without actually making the change,
        allowing you to see what the customer would be charged or credited.

        Parameters
        ----------
        subscription_id : str
            The Stripe subscription identifier.
        new_price_id : str
            The new price ID to preview.
        proration_behavior : Literal["create_prorations", "none", "always_invoice"], optional
            How to handle proration. Default is "create_prorations".
        proration_date : int, optional
            Unix timestamp for backdating the proration calculation.

        Returns
        -------
        Invoice
            Upcoming invoice preview with prorated amounts.

        Raises
        ------
        StripeAPIException
            If the preview request fails.
        """
        # Get the subscription to find the item ID
        subscription = await cls.get_subscription(subscription_id)

        subscription_item_id = subscription.items.data[0].id

        # Preview the upcoming invoice with the new price
        # Using subscription_details as per official Stripe API docs
        payload: dict[str, Any] = {
            "customer": subscription.customer,
            "subscription": subscription_id,
            "subscription_details[items][0][id]": subscription_item_id,
            "subscription_details[items][0][price]": new_price_id,
            "subscription_details[items][0][quantity]": 1,
            "subscription_details[proration_behavior]": proration_behavior,
        }

        if proration_date is not None:
            payload["subscription_details"]["proration_date"] = proration_date

        endpoint = "/v1/invoices/create_preview"
        body = await cls._request("POST", endpoint, data=payload)
        return Invoice.model_validate(body)

    @classmethod
    async def list_invoices(
        cls,
        customer_id: str,
        *,
        limit: int = 100,
    ) -> InvoiceListResponse:
        """List invoices for a Stripe customer.

        Parameters
        ----------
        customer_id : str
            The Stripe customer identifier.
        limit : int, optional
            Maximum number of invoices to retrieve (default: 100).

        Returns
        -------
        InvoiceListResponse
            Pydantic model containing invoice data with structure:
            - data: list[Invoice] - List of invoice objects
            - has_more: bool - Whether more invoices exist
            - url: str - API endpoint URL

        Raises
        ------
        StripeAPIException
            If the API request fails.
        """
        endpoint = "/v1/invoices"

        params = {
            "customer": customer_id,
            "limit": limit,
        }

        body = await cls._request("GET", endpoint, params=params)
        return InvoiceListResponse.model_validate(body)

    @classmethod
    async def create_customer(
        cls,
        email: str,
        *,
        name: str | None = None,
        metadata: dict[str, str] | None = None,
        payment_method: str | None = None,
    ) -> Customer:
        """Create a new Stripe customer.

        Parameters
        ----------
        email : str
            Customer's email address.
        name : str, optional
            Customer's full name.
        metadata : dict[str, str], optional
            Custom key-value pairs to attach to the customer.
        payment_method : str, optional
            ID of a payment method to attach to the customer.

        Returns
        -------
        Customer
            Pydantic model of the created customer.

        Raises
        ------
        StripeAPIException
            If the API request fails.
        """
        endpoint = "/v1/customers"

        payload: dict[str, Any] = {"email": email}

        if name is not None:
            payload["name"] = name
        if payment_method is not None:
            payload["payment_method"] = payment_method

        if metadata is not None:
            cls._flatten_to_payload(payload, "metadata", metadata)

        body = await cls._request("POST", endpoint, data=payload)
        return Customer.model_validate(body)

    @classmethod
    async def retry_invoice(
        cls,
        invoice_id: str,
        *,
        payment_method: str | None = None,
    ) -> Invoice:
        """Retry payment on a failed invoice.

        Attempts to collect payment again on an invoice that previously failed.

        Parameters
        ----------
        invoice_id : str
            The Stripe invoice identifier to retry.
        payment_method : str, optional
            ID of a payment method to use for this retry attempt.
            If None, uses the customer's default payment method.

        Returns
        -------
        Invoice
            Pydantic model of the invoice object after the payment attempt.

        Raises
        ------
        StripeAPIException
            If the API request fails.
        """
        endpoint = f"/v1/invoices/{invoice_id}/pay"

        payload: dict[str, Any] = {}
        if payment_method is not None:
            payload["payment_method"] = payment_method

        body = await cls._request("POST", endpoint, data=payload)
        return Invoice.model_validate(body)

    @classmethod
    async def update_customer_default_payment_method(
        cls,
        customer_id: str,
        payment_method_id: str,
    ) -> Customer:
        """Update a customer's default payment method.

        Sets a payment method as the default for future invoices and subscriptions.

        Parameters
        ----------
        customer_id : str
            The Stripe customer identifier.
        payment_method_id : str
            The payment method ID to set as default.

        Returns
        -------
        Customer
            Pydantic model of the updated customer object.

        Raises
        ------
        StripeAPIException
            If the API request fails.
        """
        endpoint = f"/v1/customers/{customer_id}"

        payload = {
            "invoice_settings": {
                "default_payment_method": payment_method_id,
            }
        }

        body = await cls._request("POST", endpoint, data=payload)
        return Customer.model_validate(body)

    @classmethod
    async def create_customer_portal_session(
        cls,
        customer_id: str,
        return_url: str,
    ) -> BillingPortalSession:
        """Create a Stripe Customer Portal session.

        Generates a portal URL where customers can manage their subscriptions,
        payment methods, and view billing history.

        Parameters
        ----------
        customer_id : str
            The Stripe customer identifier.
        return_url : str
            URL to redirect the customer to after they leave the portal.

        Returns
        -------
        BillingPortalSession
            Pydantic model of the portal session object containing the URL.

        Raises
        ------
        StripeAPIException
            If the API request fails.
        """
        endpoint = "/v1/billing_portal/sessions"

        payload = {
            "customer": customer_id,
            "return_url": return_url,
        }

        body = await cls._request("POST", endpoint, data=payload)
        return BillingPortalSession.model_validate(body)
