from decimal import Decimal
from typing import Annotated, Any
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
    StringConstraints,
)

from app.core.enums import AccessStatus, FailureType, FeatureKey


class ClientInfo(BaseModel):
    """Schema for client information in usage validation."""

    ip: Annotated[
        str | None,
        Field(description="Client IP address"),
    ] = None
    user_agent: Annotated[
        str | None,
        Field(description="Client user agent string"),
    ] = None


class UsageEstimate(BaseModel):
    """Schema for usage estimation in usage validation.

    If provided, at least one field must be set.
    """

    input_chars: Annotated[
        int | None,
        Field(ge=0, le=10_000_000, description="Number of input characters"),
    ] = None
    max_output_tokens: Annotated[
        int | None,
        Field(ge=0, le=2_000_000, description="Maximum output tokens expected"),
    ] = None
    model: Annotated[
        str | None,
        StringConstraints(max_length=100),
        Field(description="Model identifier being used"),
    ] = None

    @model_validator(mode="after")
    def at_least_one_field_required(self) -> "UsageEstimate":
        """Ensure at least one field is provided."""
        if (
            self.input_chars is None
            and self.max_output_tokens is None
            and self.model is None
        ):
            raise ValueError(
                "At least one field must be provided in usage_estimate "
                "(input_chars, max_output_tokens, or model)"
            )
        return self


class UsageValidateRequest(BaseModel):
    """Schema for validating API usage (internal endpoint)."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "request_id": "req_9f0c2a7e-acde-4b9a-8b2f-83cc71a3c9a2",
                "feature_key": "career.career_path",
                "endpoint": "/v1/extract-cues/resume",
                "method": "POST",
                "payload_hash": "a1b2c3d4e5f6789012345678901234567890abcdef1234567890abcdef123456",
                "client": {"ip": "102.89.1.22", "user_agent": "Mozilla/5.0"},
                "usage_estimate": {
                    "input_chars": 22000,
                    "max_output_tokens": 700,
                    "model": "gpt-4o-mini",
                },
            }
        }
    )

    request_id: Annotated[
        str,
        Field(description="Globally unique request ID for idempotency"),
    ]
    feature_key: Annotated[
        FeatureKey,
        Field(description="The feature key identifying the career feature being used"),
    ]
    endpoint: Annotated[
        str,
        Field(description="The API endpoint path being called"),
    ]
    method: Annotated[
        str,
        Field(description="HTTP method (GET, POST, etc.)"),
    ]
    payload_hash: Annotated[
        str,
        Field(
            description="SHA-256 hash of the request payload for fingerprinting",
            min_length=64,
            max_length=64,
            pattern=r"^[a-f0-9]{64}$",
        ),
    ]
    client: Annotated[
        ClientInfo | None,
        Field(description="Optional client information"),
    ] = None
    usage_estimate: Annotated[
        UsageEstimate | None,
        Field(description="Optional usage estimation for the request"),
    ] = None

    @field_validator("endpoint")
    @classmethod
    def normalize_endpoint(cls, v: str) -> str:
        """Normalize endpoint to lowercase for consistent idempotency."""
        return v.lower()

    @field_validator("method")
    @classmethod
    def normalize_method(cls, v: str) -> str:
        """Normalize HTTP method to uppercase for consistent idempotency."""
        return v.upper()


class UsageValidateResponse(BaseModel):
    """Schema for usage validation response."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "access": "granted",
                "user_id": "550e8400-e29b-41d4-a716-446655440000",
                "usage_id": "550e8400-e29b-41d4-a716-446655440000",
                "message": "Access granted. 98.50 credits remaining after this request.",
                "credits_reserved": "1.5000",
            }
        }
    )

    access: AccessStatus
    user_id: UUID | None
    usage_id: UUID | None
    message: str
    credits_reserved: Annotated[
        Decimal | None,
        Field(description="The credits reserved/charged for this request"),
    ] = None


class UsageCommitRequest(BaseModel):
    """Schema for committing career API usage (internal endpoint).

    Cross-field rules:

    * **success=True** — ``metrics`` and ``result_data`` are accepted;
      ``failure`` must be absent. If ``result_data`` is provided, a
      ``CareerAnalysisResult`` row is created for the user's history.
    * **success=False** — ``failure`` is **required**; ``result_data``
      is silently discarded; ``metrics`` is ignored.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "user_id": "550e8400-e29b-41d4-a716-446655440000",
                    "usage_id": "550e8400-e29b-41d4-a716-446655440001",
                    "success": True,
                    "metrics": {
                        "model_used": "gpt-4o",
                        "input_tokens": 1500,
                        "output_tokens": 500,
                        "latency_ms": 1200,
                    },
                    "result_data": {
                        "match_score": 0.85,
                        "strengths": ["Python", "FastAPI"],
                        "gaps": ["Kubernetes"],
                    },
                },
                {
                    "user_id": "550e8400-e29b-41d4-a716-446655440000",
                    "usage_id": "550e8400-e29b-41d4-a716-446655440001",
                    "success": False,
                    "failure": {
                        "failure_type": "internal_error",
                        "reason": "Model API returned 500 Internal Server Error",
                    },
                },
            ]
        }
    )

    user_id: Annotated[
        UUID,
        Field(
            description=(
                "The ID of the user that made the original request. "
                "Returned in the `UsageValidateResponse`."
            ),
        ),
    ]
    usage_id: Annotated[
        UUID,
        Field(
            description=(
                "The usage log ID obtained from " "`POST /internal/usage/validate`."
            ),
        ),
    ]
    success: Annotated[
        bool,
        Field(
            description=(
                "True if the AI analysis completed successfully, "
                "False if it failed. Controls which optional fields "
                "are required or ignored."
            ),
        ),
    ]
    metrics: Annotated[
        "UsageMetrics | None",
        Field(
            description=(
                "Optional performance metrics for successful requests. "
                "Ignored when `success` is false."
            ),
        ),
    ] = None
    failure: Annotated[
        "FailureDetails | None",
        Field(
            description=(
                "Failure details — **required** when `success` is false. "
                "Must be null or omitted when `success` is true."
            ),
        ),
    ] = None
    result_data: Annotated[
        dict[str, Any] | None,
        Field(
            description=(
                "Structured JSON output from a successful AI analysis. "
                "When provided on a successful commit, a "
                "`CareerAnalysisResult` row is created so the user "
                "can view and manage their analysis history via "
                "`GET /career/history`. "
                "Silently ignored when `success` is false."
            ),
        ),
    ] = None

    @model_validator(mode="after")
    def validate_success_fields(self) -> "UsageCommitRequest":
        """Cross-field validation for success/failure/result_data.

        * ``success=False`` → ``failure`` is required, ``result_data`` is
          cleared (silently ignored).
        * ``success=True`` → ``failure`` must not be provided.
        """
        if not self.success:
            if self.failure is None:
                raise ValueError("failure details are required when success=False")
            # Silently discard result_data on failed commits
            self.result_data = None
        else:
            if self.failure is not None:
                raise ValueError(
                    "failure details must not be provided when success=True"
                )
        return self


class UsageMetrics(BaseModel):
    """Schema for usage metrics when committing successful requests."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "model_used": "gpt-4o",
                "input_tokens": 1500,
                "output_tokens": 500,
                "latency_ms": 1200,
            }
        }
    )

    model_used: Annotated[
        str | None,
        StringConstraints(max_length=100),
        Field(description="Model identifier used (e.g., 'gpt-4o')"),
    ] = None
    input_tokens: Annotated[
        int | None,
        Field(ge=0, le=2_000_000, description="Actual input tokens used"),
    ] = None
    output_tokens: Annotated[
        int | None,
        Field(ge=0, le=2_000_000, description="Actual output tokens generated"),
    ] = None
    latency_ms: Annotated[
        int | None,
        Field(
            ge=0, le=3_600_000, description="Request latency in milliseconds (max 1hr)"
        ),
    ] = None


class FailureDetails(BaseModel):
    """Schema for failure details when committing failed requests."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "failure_type": "internal_error",
                "reason": "Model API returned 500 Internal Server Error",
            }
        }
    )

    failure_type: Annotated[
        FailureType,
        Field(description="Category of the failure"),
    ]
    reason: Annotated[
        str,
        StringConstraints(min_length=1, max_length=1000),
        Field(description="Human-readable failure description"),
    ]


class UsageCommitResponse(BaseModel):
    """Schema for usage commit response."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "success": True,
                "message": "Usage committed as SUCCESS.",
            }
        }
    )

    success: bool
    message: str


__all__ = [
    "ClientInfo",
    "UsageEstimate",
    "UsageValidateRequest",
    "UsageValidateResponse",
    "UsageCommitRequest",
    "UsageCommitResponse",
    "UsageMetrics",
    "FailureDetails",
]
