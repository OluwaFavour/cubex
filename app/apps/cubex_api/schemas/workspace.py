"""
Pydantic schemas for workspace endpoints.
"""

from datetime import datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    StringConstraints,
    computed_field,
    model_validator,
)

from app.shared.enums import (
    AccessStatus,
    FailureType,
    InvitationStatus,
    MemberRole,
    MemberStatus,
    WorkspaceStatus,
)


# ============================================================================
# Workspace Schemas
# ============================================================================


class WorkspaceCreate(BaseModel):
    """Schema for creating a new workspace."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "display_name": "My Startup",
                "description": "Workspace for our startup team",
            }
        }
    )

    display_name: Annotated[
        str,
        StringConstraints(min_length=1, max_length=128),
        Field(description="Workspace display name"),
    ]
    description: Annotated[
        str | None,
        StringConstraints(max_length=500),
        Field(description="Workspace description"),
    ] = None


class WorkspaceUpdate(BaseModel):
    """Schema for updating a workspace."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "display_name": "My Startup Renamed",
                "slug": "my-startup-renamed",
                "description": "Updated workspace description",
            }
        }
    )

    display_name: Annotated[
        str | None,
        StringConstraints(min_length=1, max_length=128),
        Field(description="Workspace display name"),
    ] = None
    slug: Annotated[
        str | None,
        StringConstraints(min_length=1, max_length=128, pattern=r"^[a-z0-9-]+$"),
        Field(description="URL-friendly workspace identifier"),
    ] = None
    description: Annotated[
        str | None,
        StringConstraints(max_length=500),
        Field(description="Workspace description"),
    ] = None


class WorkspaceMemberResponse(BaseModel):
    """Schema for workspace member response."""

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "user_id": "550e8400-e29b-41d4-a716-446655440001",
                "role": "admin",
                "status": "enabled",
                "joined_at": "2024-01-15T10:30:00Z",
                "user_email": "john@example.com",
                "user_name": "John Doe",
            }
        },
    )

    id: UUID
    user_id: UUID
    role: MemberRole
    status: MemberStatus
    joined_at: datetime
    user_email: str | None = None
    user_name: str | None = None


class WorkspaceResponse(BaseModel):
    """Schema for workspace response."""

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "display_name": "My Startup",
                "slug": "my-startup",
                "status": "active",
                "is_personal": False,
                "description": "Workspace for our startup team",
                "created_at": "2024-01-15T10:30:00Z",
                "owner_id": "550e8400-e29b-41d4-a716-446655440001",
                "enabled_member_count": 5,
                "total_member_count": 7,
                "client_id": "ws_550e8400e29b41d4a716446655440000",
            }
        },
    )

    id: UUID
    display_name: str
    slug: str
    status: WorkspaceStatus
    is_personal: bool
    description: str | None
    created_at: datetime
    owner_id: UUID
    enabled_member_count: int = 0
    total_member_count: int = 0

    @computed_field  # type: ignore[prop-decorator]
    @property
    def client_id(self) -> str:
        """Generate client ID from workspace ID (ws_<uuid_hex>)."""
        return f"ws_{self.id.hex}"


class WorkspaceDetailResponse(WorkspaceResponse):
    """Schema for detailed workspace response with members."""

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "display_name": "My Startup",
                "slug": "my-startup",
                "status": "active",
                "is_personal": False,
                "description": "Workspace for our startup team",
                "created_at": "2024-01-15T10:30:00Z",
                "owner_id": "550e8400-e29b-41d4-a716-446655440001",
                "enabled_member_count": 5,
                "total_member_count": 7,
                "client_id": "ws_550e8400e29b41d4a716446655440000",
                "members": [
                    {
                        "id": "550e8400-e29b-41d4-a716-446655440002",
                        "user_id": "550e8400-e29b-41d4-a716-446655440001",
                        "role": "owner",
                        "status": "enabled",
                        "joined_at": "2024-01-15T10:30:00Z",
                        "user_email": "owner@example.com",
                        "user_name": "Owner Name",
                    }
                ],
                "seat_count": 10,
                "available_seats": 3,
            }
        },
    )

    members: list[WorkspaceMemberResponse] = []
    seat_count: int = 0
    available_seats: int = 0


class WorkspaceListResponse(BaseModel):
    """Schema for list of workspaces."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "workspaces": [
                    {
                        "id": "550e8400-e29b-41d4-a716-446655440000",
                        "display_name": "My Startup",
                        "slug": "my-startup",
                        "status": "active",
                        "is_personal": False,
                        "description": "Workspace for our startup team",
                        "created_at": "2024-01-15T10:30:00Z",
                        "owner_id": "550e8400-e29b-41d4-a716-446655440001",
                        "enabled_member_count": 5,
                        "total_member_count": 7,
                        "client_id": "ws_550e8400e29b41d4a716446655440000",
                    }
                ]
            }
        }
    )

    workspaces: list[WorkspaceResponse]


# ============================================================================
# Member Schemas
# ============================================================================


class MemberStatusUpdate(BaseModel):
    """Schema for updating member status."""

    model_config = ConfigDict(json_schema_extra={"example": {"status": "disabled"}})

    status: Annotated[
        MemberStatus,
        Field(description="New member status: enabled or disabled"),
    ]


class MemberRoleUpdate(BaseModel):
    """Schema for updating member role."""

    model_config = ConfigDict(json_schema_extra={"example": {"role": "admin"}})

    role: Annotated[
        MemberRole,
        Field(description="New member role: admin or member"),
    ]


# ============================================================================
# Invitation Schemas
# ============================================================================


class InvitationCreate(BaseModel):
    """Schema for creating an invitation."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "email": "newmember@example.com",
                "role": "member",
                "callback_url": "https://app.example.com/invites/accept",
            }
        }
    )

    email: Annotated[EmailStr, Field(description="Email address to invite")]
    role: Annotated[
        MemberRole,
        Field(description="Role to assign: admin or member"),
    ] = MemberRole.MEMBER
    callback_url: Annotated[
        str,
        Field(
            description="Frontend URL where user will be redirected to accept invite. "
            "Token will be appended as query param. Must be in allowed CORS origins."
        ),
    ]


class InvitationResponse(BaseModel):
    """Schema for invitation response."""

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "email": "newmember@example.com",
                "role": "member",
                "status": "pending",
                "expires_at": "2024-01-22T10:30:00Z",
                "created_at": "2024-01-15T10:30:00Z",
                "inviter_email": "admin@example.com",
            }
        },
    )

    id: UUID
    email: str
    role: MemberRole
    status: InvitationStatus
    expires_at: datetime
    created_at: datetime
    inviter_email: str | None = None


class InvitationListResponse(BaseModel):
    """Schema for list of invitations."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "invitations": [
                    {
                        "id": "550e8400-e29b-41d4-a716-446655440000",
                        "email": "newmember@example.com",
                        "role": "member",
                        "status": "pending",
                        "expires_at": "2024-01-22T10:30:00Z",
                        "created_at": "2024-01-15T10:30:00Z",
                        "inviter_email": "admin@example.com",
                    }
                ]
            }
        }
    )

    invitations: list[InvitationResponse]


class InvitationAccept(BaseModel):
    """Schema for accepting an invitation."""

    model_config = ConfigDict(
        json_schema_extra={"example": {"token": "abc123def456ghi789jkl012mno345pqr678"}}
    )

    token: str


class InvitationCreatedResponse(BaseModel):
    """Schema for invitation created response."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "invitation": {
                    "id": "550e8400-e29b-41d4-a716-446655440000",
                    "email": "newmember@example.com",
                    "role": "member",
                    "status": "pending",
                    "expires_at": "2024-01-22T10:30:00Z",
                    "created_at": "2024-01-15T10:30:00Z",
                    "inviter_email": "admin@example.com",
                },
                "invitation_url": "https://app.cubex.com/invite/abc123def456",
            }
        }
    )

    invitation: InvitationResponse
    invitation_url: str


# ============================================================================
# Message Schemas
# ============================================================================


class MessageResponse(BaseModel):
    """Generic message response."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {"message": "Operation completed successfully", "success": True}
        }
    )

    message: str
    success: bool = True


# ============================================================================
# API Key Schemas
# ============================================================================


class APIKeyCreate(BaseModel):
    """Schema for creating an API key."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "Production API Key",
                "expires_in_days": 90,
            }
        }
    )

    name: Annotated[
        str,
        StringConstraints(min_length=1, max_length=128),
        Field(description="User-defined label for the API key"),
    ]
    expires_in_days: Annotated[
        int,
        Field(
            description="Number of days until the key expires. Must be between 1 and 365.",
            ge=1,
            le=365,
        ),
    ] = 90


class APIKeyResponse(BaseModel):
    """Schema for API key response (without the actual key)."""

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "name": "Production API Key",
                "key_prefix": "cbx_live_abc12",
                "is_active": True,
                "created_at": "2024-01-15T10:30:00Z",
                "expires_at": "2024-04-15T10:30:00Z",
                "last_used_at": "2024-02-01T15:45:00Z",
                "revoked_at": None,
            }
        },
    )

    id: UUID
    name: str
    key_prefix: str
    is_active: bool
    created_at: datetime
    expires_at: datetime | None
    last_used_at: datetime | None
    revoked_at: datetime | None


class APIKeyCreatedResponse(BaseModel):
    """Schema for newly created API key (includes the full key once)."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "api_key": "cbx_live_abc123def456ghi789jkl012mno345pqr678stu901",
                "key": {
                    "id": "550e8400-e29b-41d4-a716-446655440000",
                    "name": "Production API Key",
                    "key_prefix": "cbx_live_abc12",
                    "is_active": True,
                    "created_at": "2024-01-15T10:30:00Z",
                    "expires_at": "2024-04-15T10:30:00Z",
                    "last_used_at": None,
                    "revoked_at": None,
                },
                "message": "Store this API key securely. It will not be shown again.",
            }
        }
    )

    api_key: Annotated[
        str,
        Field(description="The full API key. Store securely - shown only once!"),
    ]
    key: APIKeyResponse
    message: str = "Store this API key securely. It will not be shown again."


class APIKeyListResponse(BaseModel):
    """Schema for list of API keys."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "api_keys": [
                    {
                        "id": "550e8400-e29b-41d4-a716-446655440000",
                        "name": "Production API Key",
                        "key_prefix": "cbx_live_abc12",
                        "is_active": True,
                        "created_at": "2024-01-15T10:30:00Z",
                        "expires_at": "2024-04-15T10:30:00Z",
                        "last_used_at": "2024-02-01T15:45:00Z",
                        "revoked_at": None,
                    }
                ]
            }
        }
    )

    api_keys: list[APIKeyResponse]


# ============================================================================
# Usage Validation Schemas (Internal API)
# ============================================================================


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
                "client_id": "ws_550e8400e29b41d4a716446655440000",
                "api_key": "cbx_live_abc123def456ghi789jkl012mno345pqr678stu901",
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
    client_id: Annotated[
        str,
        Field(
            description="Workspace client ID in format ws_<workspace_uuid_hex>",
            pattern=r"^ws_[a-f0-9]{32}$",
        ),
    ]
    api_key: Annotated[
        str,
        Field(description="The full API key to validate"),
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


class UsageValidateResponse(BaseModel):
    """Schema for usage validation response."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "access": "denied",
                "usage_id": None,
                "message": "Quota system is not yet implemented. Please try again later.",
                "credits_reserved": "1.5000",
            }
        }
    )

    access: AccessStatus
    usage_id: UUID | None
    message: str
    credits_reserved: Annotated[
        Decimal | None,
        Field(description="The credits reserved/charged for this request"),
    ] = None


class UsageCommitRequest(BaseModel):
    """Schema for committing API usage (internal endpoint).

    When success=True, optionally provide metrics (model, tokens, latency).
    When success=False, failure details are REQUIRED.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "api_key": "cbx_live_abc123def456ghi789jkl012mno345pqr678stu901",
                "usage_id": "550e8400-e29b-41d4-a716-446655440000",
                "success": True,
                "metrics": {
                    "model_used": "gpt-4o",
                    "input_tokens": 1500,
                    "output_tokens": 500,
                    "latency_ms": 1200,
                },
            }
        }
    )

    api_key: Annotated[
        str,
        Field(description="The API key that made the original request"),
    ]
    usage_id: Annotated[
        UUID,
        Field(description="The usage log ID to commit"),
    ]
    success: Annotated[
        bool,
        Field(description="True if request succeeded, False if failed"),
    ]
    metrics: Annotated[
        "UsageMetrics | None",
        Field(description="Optional metrics for successful requests"),
    ] = None
    failure: Annotated[
        "FailureDetails | None",
        Field(description="Required failure details when success=False"),
    ] = None

    @model_validator(mode="after")
    def failure_required_when_not_success(self) -> "UsageCommitRequest":
        """Ensure failure details are provided when success=False."""
        if not self.success and self.failure is None:
            raise ValueError("failure details are required when success=False")
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
    "WorkspaceCreate",
    "WorkspaceUpdate",
    "WorkspaceMemberResponse",
    "WorkspaceResponse",
    "WorkspaceDetailResponse",
    "WorkspaceListResponse",
    "MemberStatusUpdate",
    "MemberRoleUpdate",
    "InvitationCreate",
    "InvitationResponse",
    "InvitationListResponse",
    "InvitationAccept",
    "InvitationCreatedResponse",
    "MessageResponse",
    # API Key schemas
    "APIKeyCreate",
    "APIKeyResponse",
    "APIKeyCreatedResponse",
    "APIKeyListResponse",
    # Usage schemas
    "ClientInfo",
    "UsageEstimate",
    "UsageValidateRequest",
    "UsageValidateResponse",
    "UsageCommitRequest",
    "UsageCommitResponse",
    "UsageMetrics",
    "FailureDetails",
]
