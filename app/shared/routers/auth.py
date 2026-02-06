"""
Authentication router for handling all auth-related endpoints.

This module provides endpoints for:
- Email signup with OTP verification
- Email signin with remember me
- Token refresh and revocation
- OAuth authentication (Google, GitHub)
- Password reset and change
- Profile management
- Session management (sign out, sign out all devices)

All endpoints are prefixed with /auth when mounted in the main app.
"""

from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.apps.cubex_api.services.workspace import WorkspaceService
from app.apps.cubex_career.services.subscription import CareerSubscriptionService
from app.core.dependencies import get_async_session
from app.shared.config import auth_logger, settings
from app.shared.db.crud import user_db
from app.shared.db.models import User
from app.shared.dependencies.auth import (
    CurrentActiveUser,
)
from app.shared.enums import OAuthProviders, OTPPurpose
from app.shared.exceptions.types import (
    AuthenticationException,
    BadRequestException,
    ConflictException,
    InvalidCredentialsException,
    InvalidStateException,
    OAuthException,
    OTPInvalidException,
    TooManyAttemptsException,
    UserNotFoundException,
)
from app.shared.schemas.auth import (
    AccessTokenResponse,
    ActiveSessionResponse,
    ActiveSessionsResponse,
    ChangePasswordRequest,
    LoginRequest,
    MessageResponse,
    OAuthInitResponse,
    PasswordResetConfirmRequest,
    PasswordResetRequest,
    ProfileResponse,
    ProfileUpdateRequest,
    RefreshTokenRequest,
    ResendOTPRequest,
    SignupRequest,
    SignupResponse,
    TokenResponse,
    OTPVerifyRequest,
)
from app.shared.services.auth import AuthService
from app.shared.services.cloudinary import (
    CloudinaryService,
    CloudinaryUploadCredentials,
)
from app.shared.services.oauth import OAuthStateManager
from app.shared.utils import get_device_info


router = APIRouter()

# Service instances for product setup
_workspace_service = WorkspaceService()
_career_subscription_service = CareerSubscriptionService()


# =============================================================================
# Helper Functions
# =============================================================================


def _get_device_info_from_request(request: Request) -> str | None:
    """Extract device info from request headers using shared utility."""
    user_agent = request.headers.get("User-Agent")
    return get_device_info(user_agent)


def _build_profile_response(user: User) -> ProfileResponse:
    """Build a ProfileResponse from a User object with computed fields."""
    return ProfileResponse(
        id=user.id,
        email=user.email,
        email_verified=user.email_verified,
        full_name=user.full_name,
        avatar_url=user.avatar_url,
        is_active=user.is_active,
        created_at=user.created_at,
        updated_at=user.updated_at,
        has_password=user.password_hash is not None,
        oauth_providers=(
            [acc.provider for acc in user.oauth_accounts] if user.oauth_accounts else []
        ),
    )


async def _setup_user_products(session: AsyncSession, user: User) -> None:
    """
    Set up product resources for a user (personal workspace + Career subscription).

    This is called after:
    - Email signup verification
    - OAuth signup/signin

    The operations are idempotent - they check for existing resources before creating.

    Args:
        session: Database session (should be within a transaction).
        user: User to set up products for.
    """
    try:
        # Create personal workspace with free API subscription
        await _workspace_service.create_personal_workspace(
            session, user, commit_self=False
        )
        auth_logger.debug(f"Personal workspace ensured for user {user.id}")
    except Exception as e:
        auth_logger.warning(f"Failed to create personal workspace for {user.id}: {e}")
        # Don't fail the signup flow - user can manually activate later

    try:
        # Create free Career subscription
        await _career_subscription_service.create_free_subscription(
            session, user, commit_self=False
        )
        auth_logger.debug(f"Career subscription ensured for user {user.id}")
    except Exception as e:
        auth_logger.warning(f"Failed to create Career subscription for {user.id}: {e}")
        # Don't fail the signup flow - user can manually activate later


# =============================================================================
# Email Signup Endpoints
# =============================================================================


@router.post(
    "/signup",
    response_model=SignupResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Sign up with email",
    description="""
## Create a New User Account

Register a new user with email and password credentials. Upon successful
registration, a **6-digit OTP verification code** is sent to the provided
email address.

### Authentication Flow

1. **Submit signup request** with email, password, and optional full name
2. **Receive OTP** via email (valid for 10 minutes)
3. **Verify email** using `POST /auth/signup/verify` with the OTP
4. **Receive tokens** upon successful verification

### Password Requirements

- Minimum **8 characters**
- At least **one uppercase letter** (A-Z)
- At least **one lowercase letter** (a-z)
- At least **one digit** (0-9)

### Request Body

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `email` | string | ✅ | Valid email address |
| `password` | string | ✅ | Password meeting complexity requirements |
| `full_name` | string | ❌ | User's display name (1-255 chars) |

### Success Response (201)

Returns confirmation that verification code was sent:

```json
{
  "message": "Verification code sent to your email",
  "email": "user@example.com",
  "requires_verification": true
}
```

### Error Responses

| Status | Reason |
|--------|--------|
| `409 Conflict` | Email already registered |
| `422 Unprocessable Entity` | Invalid email format or password requirements not met |

### Notes

- The user account is created in an **unverified state**
- Email verification is **required** before the user can sign in
- If the email fails to send, the account is still created (retry with `/signup/resend`)
""",
    responses={
        409: {
            "description": "Email already registered",
            "content": {
                "application/json": {
                    "example": {"detail": "User with this email already exists."}
                }
            },
        },
    },
)
async def signup(
    request_data: SignupRequest,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> SignupResponse:
    """
    Handle user signup and send email verification OTP.
    This endpoint creates a new unverified user account and sends a verification
    OTP to the provided email address. The entire operation is wrapped in a
    database transaction to ensure atomicity.

    Args:
        request_data (SignupRequest): The signup request containing user details
            including email, password, and full name.
        session (AsyncSession): The async database session injected via dependency
            injection.

    Returns:
        SignupResponse: A response object containing:
            - message: Confirmation that verification code was sent
            - email: The email address where OTP was sent
            - requires_verification: Boolean flag indicating verification is needed

    Raises:
        ConflictException: If the email is already registered or if there's an
            authentication-related error during user creation.

    Note:
        The user account will be created in an unverified state and will require
        email verification before full access is granted.
    """
    try:
        async with session.begin():
            # Create user (unverified)
            user = await AuthService.email_signup(
                session=session,
                email=request_data.email,
                password=request_data.password,
                full_name=request_data.full_name,
                commit_self=False,
            )

            # Send verification OTP
            await AuthService.send_otp(
                session=session,
                email=user.email,
                purpose=OTPPurpose.EMAIL_VERIFICATION,
                user_id=user.id,
                user_name=user.full_name,
                commit_self=False,
            )

        return SignupResponse(
            message="Verification code sent to your email",
            email=user.email,
            requires_verification=True,
        )

    except AuthenticationException as e:
        raise ConflictException(str(e))


@router.post(
    "/signup/verify",
    response_model=TokenResponse,
    summary="Verify email and complete signup",
    description="""
## Complete Email Verification

Verify the user's email address using the OTP code sent during signup.
On successful verification, the user receives authentication tokens and
can immediately access protected resources.

### Request Body

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `email` | string | ✅ | Email address the OTP was sent to |
| `otp_code` | string | ✅ | 6-digit verification code |

### Success Response (200)

Returns JWT tokens for authentication:

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "refresh_token": "dGhpcyBpcyBhIHJlZnJl...",
  "token_type": "bearer",
  "expires_in": 900
}
```

### Token Details

| Token | Lifetime | Purpose |
|-------|----------|--------|
| `access_token` | 15 minutes | Used in `Authorization: Bearer <token>` header |
| `refresh_token` | 7 days | Used to obtain new access tokens |

### Error Responses

| Status | Reason |
|--------|--------|
| `400 Bad Request` | Invalid OTP code or expired |
| `404 Not Found` | User with this email doesn't exist |
| `422 Unprocessable Entity` | Invalid OTP format (must be 6 digits) |
| `429 Too Many Requests` | Exceeded maximum verification attempts (5) |

### Notes

- OTP codes expire after **10 minutes**
- Maximum **5 verification attempts** per OTP
- After 5 failed attempts, request a new code via `/signup/resend`
- Device info is captured from `User-Agent` header for session tracking
""",
    responses={
        400: {
            "description": "Invalid or expired OTP code",
            "content": {
                "application/json": {"example": {"detail": "Invalid verification code"}}
            },
        },
        404: {
            "description": "User not found",
            "content": {"application/json": {"example": {"detail": "User not found."}}},
        },
        429: {
            "description": "Too many verification attempts",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Too many verification attempts. Please request a new code."
                    }
                }
            },
        },
    },
)
async def verify_signup(
    request_data: OTPVerifyRequest,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> TokenResponse:
    """
    Verify user email with OTP code and return authentication tokens.

    This endpoint completes the signup process by verifying the OTP sent to
    the user's email. Upon successful verification, the user account is
    activated and authentication tokens are issued.

    Args:
        request_data (OTPVerifyRequest): The verification request containing:
            - email: The email address to verify
            - otp_code: The 6-digit OTP code received via email
        request (Request): The FastAPI request object used to extract
            device information from User-Agent header.
        session (AsyncSession): The async database session injected via
            dependency injection.

    Returns:
        TokenResponse: A response object containing:
            - access_token: JWT for API authentication
            - refresh_token: Token for obtaining new access tokens
            - token_type: Always "bearer"
            - expires_in: Access token lifetime in seconds

    Raises:
        OTPInvalidException: If the OTP code is incorrect or has expired.
        TooManyAttemptsException: If the maximum OTP verification attempts
            (5 attempts) have been exceeded.
        UserNotFoundException: If no user exists with the provided email.

    Note:
        After 5 failed verification attempts, the user must request a new
        OTP code via the resend verification endpoint.
    """
    try:
        async with session.begin():
            # Verify OTP
            await AuthService.verify_otp(
                session=session,
                email=request_data.email,
                otp_code=request_data.otp_code,
                purpose=OTPPurpose.EMAIL_VERIFICATION,
                commit_self=False,
            )

            # Mark email as verified
            user = await user_db.get_one_by_conditions(
                session=session,
                conditions=[user_db.model.email == request_data.email],
                options=[user_db.oauth_accounts_loader],
            )

            if user is None:
                raise UserNotFoundException()

            await user_db.update(
                session=session,
                id=user.id,
                updates={"email_verified": True},
                commit_self=False,
            )

            # Set up product resources (workspace + Career subscription)
            # This is idempotent - safe to call on existing users
            await _setup_user_products(session, user)

            # Generate tokens
            device_info = _get_device_info_from_request(request)
            tokens = await AuthService.create_token_pair(
                session=session,
                user=user,
                remember_me=False,
                device_info=device_info,
                commit_self=False,
            )

        return TokenResponse(
            access_token=tokens.access_token,
            refresh_token=tokens.refresh_token,
            token_type=tokens.token_type,
            expires_in=tokens.expires_in,
        )

    except OTPInvalidException:
        raise OTPInvalidException("Invalid verification code")
    except TooManyAttemptsException:
        raise TooManyAttemptsException(
            "Too many verification attempts. Please request a new code."
        )


@router.post(
    "/signup/resend",
    response_model=MessageResponse,
    summary="Resend verification code",
    description="""
## Resend Email Verification Code

Request a new OTP verification code to be sent to the user's email.
Use this when the original code has expired or wasn't received.

### Request Body

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `email` | string | ✅ | Email address to send OTP to |

### Success Response (200)

```json
{
  "message": "Verification code sent to your email",
  "success": true
}
```

### Security Behavior

For security reasons, this endpoint **always returns success** even if:
- The email doesn't exist in the system
- The email is already verified

This prevents email enumeration attacks.

### Conditional Responses

| Scenario | Response |
|----------|----------|
| Email exists & unverified | New OTP sent, `success: true` |
| Email already verified | `success: false`, message indicates already verified |
| Email not found | `success: true` (security measure) |

### Notes

- Previous OTP codes are **invalidated** when a new one is sent
- Rate limiting may apply (check `429` responses)
- New OTP is valid for **10 minutes**
""",
)
async def resend_verification(
    request_data: ResendOTPRequest,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> MessageResponse:
    """
    Resend a new verification OTP code to the user's email.

    This endpoint generates and sends a new OTP code for users who haven't
    received or have lost their original verification code. It invalidates
    any previous OTP codes for security.

    Args:
        request_data (ResendOTPRequest): The resend request containing:
            - email: The email address to resend verification to
        session (AsyncSession): The async database session injected via
            dependency injection.

    Returns:
        MessageResponse: A response object containing:
            - message: Confirmation or status message
            - success: Boolean flag indicating the operation result

    Raises:
        None explicitly - returns success:false for already verified emails
            and always returns success:true for non-existent emails (security).

    Note:
        For security, this endpoint always returns a success-like response
        even if the email doesn't exist, preventing email enumeration attacks.
        Previous OTP codes are invalidated when a new one is generated.
    """
    async with session.begin():
        user = await user_db.get_one_by_conditions(
            session=session,
            conditions=[user_db.model.email == request_data.email],
        )

        if user is None:
            # Don't reveal if user exists
            return MessageResponse(
                message="If the email exists, a verification code has been sent"
            )

        if user.email_verified:
            return MessageResponse(message="Email is already verified", success=False)

        await AuthService.send_otp(
            session=session,
            email=user.email,
            purpose=OTPPurpose.EMAIL_VERIFICATION,
            user_id=user.id,
            user_name=user.full_name,
            commit_self=False,
        )

    return MessageResponse(message="Verification code sent to your email")


# =============================================================================
# Email Signin Endpoints
# =============================================================================


@router.post(
    "/signin",
    response_model=TokenResponse,
    summary="Sign in with email",
    description="""
## Sign In with Email & Password

Authenticate a user with their email and password credentials.
Returns JWT tokens for accessing protected resources.

### Request Body

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `email` | string | ✅ | - | User's registered email |
| `password` | string | ✅ | - | User's password |
| `remember_me` | boolean | ❌ | `false` | Extend session duration |

### Session Duration

| `remember_me` | Refresh Token Lifetime |
|---------------|------------------------|
| `false` | 7 days |
| `true` | 30 days |

### Success Response (200)

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "refresh_token": "dGhpcyBpcyBhIHJlZnJl...",
  "token_type": "bearer",
  "expires_in": 900
}
```

### Using the Tokens

Include the access token in the `Authorization` header:

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs...
```

### Error Responses

| Status | Reason |
|--------|--------|
| `401 Unauthorized` | Invalid email/password, unverified email, or disabled account |
| `422 Unprocessable Entity` | Invalid request format |

### Prerequisites

- User must have **verified their email** via OTP
- Account must be **active** (not soft-deleted)

### Notes

- Device info captured from `User-Agent` for session management
- Each sign-in creates a new session (viewable via `/auth/sessions`)
- OAuth-only users (no password) cannot use this endpoint
""",
    responses={
        401: {
            "description": "Invalid credentials or unverified email",
            "content": {
                "application/json": {
                    "examples": {
                        "invalid_credentials": {
                            "summary": "Invalid email or password",
                            "value": {"detail": "Invalid email or password"},
                        },
                        "email_not_verified": {
                            "summary": "Email not verified",
                            "value": {
                                "detail": "Email not verified. Please verify your email first."
                            },
                        },
                        "account_disabled": {
                            "summary": "Account disabled",
                            "value": {"detail": "Account is disabled."},
                        },
                    }
                }
            },
        },
    },
)
async def signin(
    request_data: LoginRequest,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> TokenResponse:
    """
    Authenticate user with email and password credentials.

    This endpoint validates user credentials and issues JWT access and
    refresh tokens upon successful authentication. Session device info
    is captured from the request headers.

    Args:
        request_data (LoginRequest): The signin request containing:
            - email: The user's registered email address
            - password: The user's password
            - remember_me: Optional flag for extended token lifetime (30 days)
        request (Request): The FastAPI request object used to extract
            device information from User-Agent header for session tracking.
        session (AsyncSession): The async database session injected via
            dependency injection.

    Returns:
        TokenResponse: A response object containing:
            - access_token: Short-lived JWT for API authentication
            - refresh_token: Long-lived token for obtaining new access tokens
            - token_type: Always "bearer"
            - expires_in: Access token lifetime in seconds

    Raises:
        InvalidCredentialsException: If the email/password combination is
            incorrect or the user account doesn't exist.
        AuthenticationException: If the email is unverified, account is
            disabled, or other authentication errors occur.

    Note:
        OAuth-only users (who registered via Google/GitHub) cannot use
        this endpoint and must sign in through their OAuth provider.
    """
    try:
        async with session.begin():
            # Authenticate user
            user = await AuthService.email_signin(
                session=session,
                email=request_data.email,
                password=request_data.password,
            )

            # Load OAuth accounts for profile
            user = await user_db.get_by_id(
                session=session,
                id=user.id,
                options=[user_db.oauth_accounts_loader],
            )

            # Generate tokens
            device_info = _get_device_info_from_request(request)
            tokens = await AuthService.create_token_pair(
                session=session,
                user=user,
                remember_me=request_data.remember_me,
                device_info=device_info,
                commit_self=False,
            )

        return TokenResponse(
            access_token=tokens.access_token,
            refresh_token=tokens.refresh_token,
            token_type=tokens.token_type,
            expires_in=tokens.expires_in,
        )

    except InvalidCredentialsException:
        raise InvalidCredentialsException("Invalid email or password")
    except AuthenticationException:
        raise


# =============================================================================
# Token Management Endpoints
# =============================================================================


@router.post(
    "/token/refresh",
    response_model=AccessTokenResponse,
    summary="Refresh access token",
    description="""
## Refresh Access Token

Exchange a valid refresh token for a new access token. Use this endpoint
when the access token has expired to maintain the user's session without
requiring re-authentication.

### Request Body

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `refresh_token` | string | ✅ | The refresh token from sign-in/signup |

### Success Response (200)

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer",
  "expires_in": 900
}
```

### Token Lifecycle

```
┌─────────────────┐     ┌─────────────────┐
│  Access Token   │     │  Refresh Token  │
│   (15 minutes)  │     │  (7-30 days)    │
└────────┬────────┘     └────────┬────────┘
         │                       │
         ▼                       ▼
┌─────────────────┐     ┌─────────────────┐
│    Expired?     │ Yes │ POST /token/    │
│                 │────▶│    refresh      │
└─────────────────┘     └────────┬────────┘
                                 │
                                 ▼
                        ┌─────────────────┐
                        │  New Access     │
                        │    Token        │
                        └─────────────────┘
```

### Error Responses

| Status | Reason |
|--------|--------|
| `401 Unauthorized` | Token is invalid, expired, or revoked |
| `422 Unprocessable Entity` | Missing refresh_token field |

### Notes

- The **refresh token itself is not rotated** (same token remains valid)
- Refresh tokens can be revoked via `/signout` or `/signout/all`
- If refresh token expires, user must sign in again
- User account must still be active for refresh to succeed
""",
    responses={
        401: {
            "description": "Invalid, expired, or revoked refresh token",
            "content": {
                "application/json": {
                    "examples": {
                        "invalid_token": {
                            "summary": "Invalid token",
                            "value": {"detail": "Invalid refresh token."},
                        },
                        "expired_token": {
                            "summary": "Token expired",
                            "value": {"detail": "Refresh token has expired."},
                        },
                        "revoked_token": {
                            "summary": "Token revoked",
                            "value": {"detail": "Refresh token has been revoked."},
                        },
                    }
                }
            },
        },
    },
)
async def refresh_token(
    request_data: RefreshTokenRequest,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> AccessTokenResponse:
    """
    Exchange a valid refresh token for a new access token.

    This endpoint issues a new access token using a valid refresh token.
    The refresh token itself is not rotated and remains valid until its
    original expiration date or until explicitly revoked.

    Args:
        request_data (RefreshTokenRequest): The refresh request containing:
            - refresh_token: The current valid refresh token
        session (AsyncSession): The async database session injected via
            dependency injection.

    Returns:
        AccessTokenResponse: A response object containing:
            - access_token: New short-lived JWT for API authentication
            - token_type: Always "bearer"
            - expires_in: Access token lifetime in seconds (900 = 15 min)

    Raises:
        AuthenticationException: If the refresh token is invalid, expired,
            revoked, or the associated user account is deactivated.

    Note:
        Unlike token rotation schemes, this implementation keeps the same
        refresh token valid. Store your refresh token securely as it grants
        the ability to obtain new access tokens until it expires or is revoked.
    """
    try:
        new_access_token = await AuthService.refresh_access_token(
            session=session,
            refresh_token=request_data.refresh_token,
        )

        return AccessTokenResponse(
            access_token=new_access_token,
            token_type="bearer",
            expires_in=AuthService.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )

    except AuthenticationException:
        raise


@router.post(
    "/signout",
    response_model=MessageResponse,
    summary="Sign out",
    description="""
## Sign Out (Single Device)

Revoke a specific refresh token, effectively signing out from one device/session.
The associated access tokens will no longer be refreshable.

### Request Body

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `refresh_token` | string | ✅ | The refresh token to revoke |

### Success Responses (200)

**Token successfully revoked:**
```json
{
  "message": "Successfully signed out",
  "success": true
}
```

**Token not found or already revoked:**
```json
{
  "message": "Token not found or already revoked",
  "success": false
}
```

### Behavior

| Scenario | Result |
|----------|--------|
| Valid token | Token revoked, `success: true` |
| Already revoked | No change, `success: false` |
| Invalid/unknown token | No change, `success: false` |

### Notes

- This endpoint **does not require authentication** (stateless signout)
- Existing access tokens remain valid until they expire (15 min)
- For immediate invalidation across all devices, use `/signout/all`
- Does not affect other sessions/devices
""",
)
async def signout(
    request_data: RefreshTokenRequest,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> MessageResponse:
    """
    Revoke a specific refresh token to sign out from a single session.

    This endpoint invalidates the provided refresh token, effectively
    signing the user out from the device/session that token belongs to.
    Other active sessions remain unaffected.

    Args:
        request_data (RefreshTokenRequest): The signout request containing:
            - refresh_token: The refresh token to revoke
        session (AsyncSession): The async database session injected via
            dependency injection.

    Returns:
        MessageResponse: A response object containing:
            - message: Status message ("Successfully signed out" or
              "Token not found or already revoked")
            - success: Boolean indicating if a token was actually revoked

    Raises:
        None explicitly - this endpoint handles invalid tokens gracefully
            by returning success:false instead of raising exceptions.

    Note:
        This endpoint does not require authentication headers, only the
        refresh token in the request body. This allows signing out even
        when the access token has expired. Existing access tokens remain
        valid until they naturally expire (15 minutes).
    """
    async with session.begin():
        revoked = await AuthService.revoke_refresh_token(
            session=session,
            refresh_token=request_data.refresh_token,
            commit_self=False,
        )

    if revoked:
        return MessageResponse(message="Successfully signed out")
    return MessageResponse(message="Token not found or already revoked", success=False)


@router.post(
    "/signout/all",
    response_model=MessageResponse,
    summary="Sign out all devices",
    description="""
## Sign Out (All Devices)

Revoke **all** refresh tokens for the authenticated user, signing them out
from every device and session. Useful for security incidents or when
changing sensitive account settings.

### Authentication Required

```http
Authorization: Bearer <access_token>
```

### Success Response (200)

```json
{
  "message": "Signed out from 3 device(s)",
  "success": true
}
```

### Error Responses

| Status | Reason |
|--------|--------|
| `401 Unauthorized` | Missing or invalid access token |

### Use Cases

- 🔒 **Security breach** - Suspect unauthorized access
- 🔑 **Password change** - Automatically called after password change
- 📱 **Lost device** - Revoke access from lost/stolen device
- 🧹 **Session cleanup** - Clear all old sessions

### Notes

- Requires a valid **access token** (unlike single-device signout)
- The current session is **also revoked**
- Returns count of revoked sessions for confirmation
- Access tokens remain valid until expiry (15 min max)
""",
    responses={
        401: {
            "description": "Not authenticated",
            "content": {
                "application/json": {"example": {"detail": "Not authenticated"}}
            },
        },
    },
)
async def signout_all(
    user: CurrentActiveUser,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> MessageResponse:
    """
    Revoke all refresh tokens to sign out from all devices.

    This endpoint invalidates all active refresh tokens for the authenticated
    user, effectively signing them out from every device and session. This
    is useful for security emergencies or when the user suspects unauthorized
    access.

    Args:
        user (CurrentActiveUser): The currently authenticated user, injected
            via FastAPI dependency. Must have a valid access token.
        session (AsyncSession): The async database session injected via
            dependency injection.

    Returns:
        MessageResponse: A response object containing:
            - message: Confirmation with count ("Signed out from N device(s)")
            - success: Boolean indicating operation success

    Raises:
        HTTPException (401): If the user is not authenticated or the
            access token is invalid/expired.

    Note:
        The current access token remains valid until it expires (15 minutes),
        but no new access tokens can be obtained since all refresh tokens
        are revoked. The response includes the count of revoked sessions.
    """
    async with session.begin():
        count = await AuthService.revoke_all_user_tokens(
            session=session,
            user_id=user.id,
            commit_self=False,
        )

    return MessageResponse(message=f"Signed out from {count} device(s)")


# =============================================================================
# OAuth Endpoints
# =============================================================================


@router.get(
    "/oauth/{provider}",
    response_model=OAuthInitResponse,
    summary="Initiate OAuth flow",
    description="""
## Initiate OAuth Authentication

Begin the OAuth 2.0 authorization flow with a supported provider.
Returns an authorization URL to redirect the user to the provider's
consent screen.

### Supported Providers

| Provider | Path Value | Scopes Requested |
|----------|------------|------------------|
| Google | `google` | `openid`, `email`, `profile` |
| GitHub | `github` | `user:email`, `read:user` |

### Path Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `provider` | string | OAuth provider: `google` or `github` |

### Query Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `remember_me` | boolean | `false` | Extend session to 30 days |
| `callback_url` | string | `null` | Frontend URL for redirect after OAuth |

### Success Response (200)

```json
{
  "authorization_url": "https://accounts.google.com/o/oauth2/v2/auth?...",
  "state": "eyJhbGciOiJIUzI1NiIs..."
}
```

### OAuth Flow Diagram

```
┌──────────┐     ┌─────────────┐     ┌──────────────┐
│  Client  │     │   Backend   │     │   Provider   │
└────┬─────┘     └──────┬──────┘     └──────┬───────┘
     │                  │                   │
     │ GET /oauth/google│                   │
     │─────────────────▶│                   │
     │                  │                   │
     │ authorization_url│                   │
     │◀─────────────────│                   │
     │                  │                   │
     │ Redirect user to authorization_url  │
     │─────────────────────────────────────▶│
     │                  │                   │
     │                  │  User consents    │
     │                  │                   │
     │ Redirect to callback with code       │
     │◀─────────────────────────────────────│
     │                  │                   │
     │                  │                   │
```

### Callback URL Validation

If `callback_url` is provided:
- Must be in the configured **CORS origins** list
- Must use **HTTPS** in production environments
- Tokens will be returned as **URL fragment** parameters

### Error Responses

| Status | Reason |
|--------|--------|
| `400 Bad Request` | Invalid callback URL |
| `422 Unprocessable Entity` | Invalid provider value |

### Next Steps

1. Redirect user to `authorization_url`
2. User authenticates with provider
3. Provider redirects to `/oauth/{provider}/callback`
4. Tokens returned (JSON or URL fragment based on `callback_url`)
""",
    responses={
        400: {
            "description": "Invalid callback URL",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Invalid callback URL. Must be in allowed origins and use HTTPS in production."
                    }
                }
            },
        },
        422: {
            "description": "Invalid provider",
            "content": {
                "application/json": {
                    "example": {
                        "detail": [
                            {
                                "type": "enum",
                                "loc": ["path", "provider"],
                                "msg": "Input should be 'google' or 'github'",
                            }
                        ]
                    }
                }
            },
        },
    },
)
async def oauth_init(
    provider: OAuthProviders,
    request: Request,
    remember_me: bool = Query(False, description="Extend session to 30 days"),
    callback_url: str | None = Query(
        None,
        description="Frontend callback URL for redirect after OAuth. Must be in CORS origins.",
    ),
) -> OAuthInitResponse:
    """
    Generate the OAuth authorization URL for the specified provider.

    This endpoint initiates the OAuth flow by generating a provider-specific
    authorization URL. The client should redirect the user to this URL to
    begin the OAuth authentication process.

    Args:
        provider (OAuthProviders): The OAuth provider to authenticate with.
            Currently supported: "google", "github".
        request (Request): The FastAPI request object.
        remember_me (bool): If True, extends the session duration to 30 days.
            Defaults to False (7-day session).
        callback_url (str | None): Optional frontend URL for redirect after
            OAuth completion. Must be in allowed CORS origins. If provided,
            tokens are returned as URL fragment parameters.

    Returns:
        OAuthInitResponse: A response object containing:
            - authorization_url: The full OAuth authorization URL to redirect to
            - state: Signed CSRF protection token (passed through OAuth flow)

    Raises:
        BadRequestException: If the callback_url is provided but not in the
            allowed CORS origins or doesn't use HTTPS in production.

    Note:
        The state parameter is cryptographically signed and encodes the
        callback_url and remember_me preferences. It expires after 10 minutes.
        The callback_url must exactly match one registered in CORS settings.
    """
    # Validate callback URL if provided
    if callback_url and not OAuthStateManager.validate_callback_url(callback_url):
        raise BadRequestException(
            message="Invalid callback URL. Must be in allowed origins and use HTTPS in production."
        )

    # Get the OAuth provider service
    provider_class = AuthService.get_oauth_provider(provider)

    # Generate signed state with callback_url and remember_me encoded
    state = OAuthStateManager.encode_state(
        callback_url=callback_url,
        remember_me=remember_me,
    )

    # Build redirect URI (must match the callback route)
    redirect_uri = f"{settings.OAUTH_REDIRECT_BASE_URI}/oauth/{provider.value}/callback"

    # Get authorization URL
    auth_url = provider_class.get_authorization_url(
        redirect_uri=redirect_uri,
        state=state,
    )

    return OAuthInitResponse(
        authorization_url=auth_url,
        state=state,
    )


@router.get(
    "/oauth/{provider}/callback",
    response_model=TokenResponse,
    summary="OAuth callback",
    description="""
## OAuth Callback Handler

Handle the OAuth provider callback after user authorization. This endpoint:

1. Validates the CSRF state parameter
2. Exchanges the authorization code for provider tokens
3. Retrieves user profile from the provider
4. Creates or links user account
5. Issues application tokens

### Query Parameters

| Parameter | Type | Source | Description |
|-----------|------|--------|-------------|
| `code` | string | Provider | Authorization code from OAuth provider (absent on cancel) |
| `state` | string | Provider | CSRF state from `/oauth/{provider}` init |
| `error` | string | Provider | Error code if user cancelled or provider error (e.g., `access_denied`) |
| `error_description` | string | Provider | Human-readable error description (optional) |

### Response Behavior

The response depends on whether `callback_url` was provided during init:

#### Without `callback_url` → JSON Response (200)

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "refresh_token": "dGhpcyBpcyBhIHJlZnJl...",
  "token_type": "bearer",
  "expires_in": 900
}
```

#### With `callback_url` → Redirect (307)

Redirects to:
```
{callback_url}#access_token=...&refresh_token=...&token_type=bearer&expires_in=900
```

> ⚠️ **Note:** Tokens are in the **URL fragment** (`#`), not query params (`?`).
> This prevents tokens from being logged in server access logs.

### User Account Handling

| Scenario | Behavior |
|----------|----------|
| New email | Create new user account |
| Existing email (same provider) | Sign in to existing account |
| Existing email (different provider) | Link OAuth to existing account |
| Existing email (has password) | Link OAuth, preserve password |

### Error Responses

| Status | Scenario | Behavior |
|--------|----------|----------|
| `400` | Invalid/expired state | JSON error (can't redirect) |
| `307` | OAuth error + callback_url | Redirect to `{callback_url}?error=...` |
| `400` | OAuth error, no callback_url | JSON error response |

### Error Redirect Format

When `callback_url` is set and an error occurs:
```
{callback_url}?error=oauth_error&error_description=...
```

### User Cancellation

If the user cancels on the provider's consent page, the provider redirects back
with an `error` parameter (e.g., `access_denied`). This endpoint detects the
cancellation and redirects to `callback_url` with the error details passed through.

### Security Notes

- State parameter expires after **10 minutes**
- State is cryptographically signed to prevent tampering
- Authorization codes are **single-use** (provider enforced)
- Email from provider is automatically marked as **verified**
""",
    responses={
        307: {
            "description": "Redirect to frontend callback URL with tokens in fragment",
            "headers": {
                "Location": {
                    "description": "Redirect URL with tokens: `{callback_url}#access_token=...&refresh_token=...`",
                    "schema": {"type": "string"},
                }
            },
        },
        400: {
            "description": "OAuth error or invalid state",
            "content": {
                "application/json": {
                    "examples": {
                        "invalid_state": {
                            "summary": "Invalid state parameter",
                            "value": {"detail": "Invalid state parameter."},
                        },
                        "oauth_error": {
                            "summary": "OAuth provider error",
                            "value": {"detail": "OAuth authentication failed"},
                        },
                    }
                }
            },
        },
    },
)
async def oauth_callback(
    provider: OAuthProviders,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_async_session)],
    code: Annotated[
        str | None, Query(description="Authorization code from provider")
    ] = None,
    state: Annotated[
        str | None, Query(description="State parameter for CSRF validation")
    ] = None,
    error: Annotated[
        str | None,
        Query(description="Error code from provider (e.g., access_denied)"),
    ] = None,
    error_description: Annotated[
        str | None, Query(description="Human-readable error description")
    ] = None,
) -> TokenResponse | RedirectResponse:
    """
    Complete OAuth flow by exchanging authorization code for tokens.

    This endpoint handles the OAuth callback after user authorization.
    It validates the state parameter, exchanges the authorization code
    for provider tokens, retrieves user info, and either creates a new
    user or links to an existing account.

    Args:
        provider (OAuthProviders): The OAuth provider that initiated the callback.
            Must match the provider used in oauth_init.
        request (Request): The FastAPI request object used to extract
            device information from User-Agent header.
        session (AsyncSession): The async database session injected via
            dependency injection.
        code (str | None): The authorization code received from the OAuth provider
            after user consent. None if user cancelled or error occurred.
        state (str | None): The signed CSRF protection token that was passed through
            the OAuth flow. Contains encoded callback_url and remember_me.
        error (str | None): Error code from the provider if user cancelled or
            an error occurred (e.g., "access_denied", "consent_required").
        error_description (str | None): Human-readable description of the error
            from the provider. Optional, not all providers include this.

    Returns:
        TokenResponse | RedirectResponse: Either:
            - TokenResponse (JSON) if no callback_url was provided
            - RedirectResponse (307) to callback_url with tokens in fragment

    Raises:
        InvalidStateException: If the state parameter is invalid, expired,
            or has been tampered with (CSRF protection).
        OAuthException: If the authorization code exchange fails or user
            info retrieval fails from the provider.

    Note:
        If the OAuth email matches an existing user, the OAuth account is
        linked to that user. Otherwise, a new verified user is created.
        When callback_url is set, tokens are returned in URL fragment (#)
        to prevent server-side logging of sensitive tokens.
    """
    # Handle provider error or user cancellation (e.g., access_denied)
    if error:
        auth_logger.info(
            f"OAuth callback: provider returned error for {provider.value}: "
            f"{error} - {error_description}"
        )
        # Try to decode state to get callback_url for redirect
        if state:
            state_data = OAuthStateManager.decode_state(state)
            if state_data and state_data.callback_url:
                # Build error redirect URL with provider error details
                error_params = {"error": error}
                if error_description:
                    error_params["error_description"] = error_description
                return RedirectResponse(
                    url=f"{state_data.callback_url}?{urlencode(error_params)}",
                    status_code=307,
                )
        # No valid state or callback_url - raise exception
        raise BadRequestException(message=f"OAuth error: {error}")

    # Validate required params for success flow
    if not code or not state:
        auth_logger.warning(
            f"OAuth callback: missing code or state for {provider.value}"
        )
        raise BadRequestException(message="Missing required OAuth parameters")

    # Decode and validate state
    state_data = OAuthStateManager.decode_state(state)
    if not state_data:
        auth_logger.warning(
            f"OAuth callback: invalid or expired state parameter for {provider.value}"
        )
        # If we can't decode state, we can't redirect - raise exception
        raise InvalidStateException()

    callback_url = state_data.callback_url
    remember_me = state_data.remember_me

    try:
        # Get the OAuth provider service
        provider_class = AuthService.get_oauth_provider(provider)

        # Build redirect URI (must match the one used in auth URL)
        redirect_uri = (
            f"{settings.OAUTH_REDIRECT_BASE_URI}/oauth/{provider.value}/callback"
        )

        # Exchange code for tokens
        oauth_tokens = await provider_class.exchange_code_for_tokens(
            code=code,
            redirect_uri=redirect_uri,
        )

        # Get user info from provider
        user_info = await provider_class.get_user_info(
            access_token=oauth_tokens.access_token,
        )

        # Authenticate or create user
        async with session.begin():
            user = await AuthService.oauth_authenticate(
                session=session,
                user_info=user_info,
                commit_self=False,
            )

            # Load OAuth accounts
            user = await user_db.get_by_id(
                session=session,
                id=user.id,
                options=[user_db.oauth_accounts_loader],
            )

            # Set up product resources (workspace + Career subscription)
            # This is idempotent - safe to call on existing users
            if user:
                await _setup_user_products(session, user)

            # Generate tokens
            device_info = _get_device_info_from_request(request)
            tokens = await AuthService.create_token_pair(
                session=session,
                user=user,
                remember_me=remember_me,
                device_info=device_info,
                commit_self=False,
            )

        # If callback URL provided, redirect with tokens in fragment
        if callback_url:
            fragment_params = urlencode(
                {
                    "access_token": tokens.access_token,
                    "refresh_token": tokens.refresh_token,
                    "token_type": tokens.token_type,
                    "expires_in": tokens.expires_in,
                }
            )
            return RedirectResponse(
                url=f"{callback_url}#{fragment_params}",
                status_code=307,
            )

        # No callback URL, return JSON response
        return TokenResponse(
            access_token=tokens.access_token,
            refresh_token=tokens.refresh_token,
            token_type=tokens.token_type,
            expires_in=tokens.expires_in,
        )

    except OAuthException as e:
        auth_logger.error(f"OAuth callback failed: {e}")
        if callback_url:
            error_params = {"error": "oauth_error", "error_description": e.message}
            return RedirectResponse(
                url=f"{callback_url}?{urlencode(error_params)}",
                status_code=307,
            )
        raise

    except Exception as e:
        auth_logger.error(f"OAuth callback failed unexpectedly: {e}")
        if callback_url:
            error_params = {
                "error": "oauth_error",
                "error_description": "OAuth authentication failed",
            }
            return RedirectResponse(
                url=f"{callback_url}?{urlencode(error_params)}",
                status_code=307,
            )
        raise OAuthException(message="OAuth authentication failed")


# =============================================================================
# Password Reset Endpoints
# =============================================================================


@router.post(
    "/password/reset",
    response_model=MessageResponse,
    summary="Request password reset",
    description="""
## Request Password Reset

Initiate the password reset flow by sending a 6-digit OTP code
to the user's registered email address.

### Request Body

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `email` | string | ✅ | Email address of the account |

### Success Response (200)

```json
{
  "message": "If the email exists and has a password, a reset code has been sent",
  "success": true
}
```

### Security Design

This endpoint **always returns the same response** regardless of:
- Whether the email exists
- Whether the user has a password set
- Whether the email was successfully sent

This prevents **email enumeration attacks** where attackers could
discover which emails are registered.

### Conditions for OTP to be Sent

| Condition | OTP Sent? |
|-----------|----------|
| Email exists + has password | ✅ Yes |
| Email exists + OAuth-only (no password) | ❌ No |
| Email doesn't exist | ❌ No |

### Next Steps

1. User receives OTP via email (valid for **10 minutes**)
2. Submit OTP + new password to `/password/reset/confirm`

### Notes

- Previous reset OTPs are invalidated when requesting a new one
- OAuth-only users should sign in with their OAuth provider
- Rate limiting may apply to prevent abuse
""",
)
async def request_password_reset(
    request_data: PasswordResetRequest,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> MessageResponse:
    """
    Request a password reset OTP to be sent to the user's email.

    This endpoint initiates the password reset flow by generating and
    sending an OTP code to the provided email address. The response is
    intentionally vague to prevent email enumeration attacks.

    Args:
        request_data (PasswordResetRequest): The reset request containing:
            - email: The email address associated with the account
        session (AsyncSession): The async database session injected via
            dependency injection.

    Returns:
        MessageResponse: A response object containing:
            - message: Generic confirmation message (always the same)
            - success: Boolean indicating operation success (always True)

    Raises:
        None explicitly - this endpoint always returns success for security.

    Note:
        For security, this endpoint always returns the same response
        regardless of whether the email exists or if the user has a password.
        OTP is only sent if the email exists AND the user has a password
        (not OAuth-only). The OTP is valid for 10 minutes.
    """
    async with session.begin():
        user = await user_db.get_one_by_conditions(
            session=session,
            conditions=[user_db.model.email == request_data.email],
        )

        if user:
            # Only send if user has a password (not OAuth-only)
            if user.password_hash:
                await AuthService.send_otp(
                    session=session,
                    email=user.email,
                    purpose=OTPPurpose.PASSWORD_RESET,
                    user_id=user.id,
                    user_name=user.full_name,
                    commit_self=False,
                )

    # Always return success for security
    return MessageResponse(
        message="If the email exists and has a password, a reset code has been sent"
    )


@router.post(
    "/password/reset/confirm",
    response_model=MessageResponse,
    summary="Confirm password reset",
    description="""
## Confirm Password Reset

Complete the password reset process by verifying the OTP and setting
a new password. All existing sessions are revoked for security.

### Request Body

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `email` | string | ✅ | Email address of the account |
| `otp_code` | string | ✅ | 6-digit verification code |
| `new_password` | string | ✅ | New password (see requirements) |

### Password Requirements

- Minimum **8 characters**
- At least **one uppercase letter** (A-Z)
- At least **one lowercase letter** (a-z)
- At least **one digit** (0-9)

### Success Response (200)

```json
{
  "message": "Password has been reset successfully",
  "success": true
}
```

### Security Actions on Success

1. ✅ Password updated
2. ✅ OTP invalidated
3. ✅ **All refresh tokens revoked** (signs out all devices)

### Error Responses

| Status | Reason |
|--------|--------|
| `400 Bad Request` | Invalid or expired OTP code |
| `422 Unprocessable Entity` | Invalid OTP format or password requirements not met |
| `429 Too Many Requests` | Exceeded 5 verification attempts |

### Notes

- OTP codes expire after **10 minutes**
- Maximum **5 attempts** per OTP, then must request new code
- User must sign in again after password reset
- If OTP attempts exhausted, request new code via `/password/reset`
""",
    responses={
        400: {
            "description": "Invalid or expired OTP",
            "content": {
                "application/json": {"example": {"detail": "Invalid verification code"}}
            },
        },
        429: {
            "description": "Too many verification attempts",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Too many verification attempts. Please request a new code."
                    }
                }
            },
        },
    },
)
async def confirm_password_reset(
    request_data: PasswordResetConfirmRequest,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> MessageResponse:
    """
    Verify OTP and set a new password, revoking all existing sessions.

    This endpoint completes the password reset flow by validating the OTP
    code, updating the user's password, and revoking all existing refresh
    tokens for security.

    Args:
        request_data (PasswordResetConfirmRequest): The confirmation request
            containing:
            - email: The email address for the account
            - otp_code: The 6-digit OTP code received via email
            - new_password: The new password to set (must meet requirements)
        session (AsyncSession): The async database session injected via
            dependency injection.

    Returns:
        MessageResponse: A response object containing:
            - message: Confirmation that password was reset successfully
            - success: Boolean indicating operation success

    Raises:
        OTPInvalidException: If the OTP code is incorrect or has expired.
        TooManyAttemptsException: If the maximum OTP verification attempts
            (5 attempts) have been exceeded.
        AuthenticationException: If there's a general authentication error.

    Note:
        All existing sessions are revoked when the password is reset,
        requiring the user to sign in again on all devices. This is a
        security measure to protect against account compromise.
    """
    try:
        async with session.begin():
            # Verify OTP
            await AuthService.verify_otp(
                session=session,
                email=request_data.email,
                otp_code=request_data.otp_code,
                purpose=OTPPurpose.PASSWORD_RESET,
                commit_self=False,
            )

            # Reset password
            await AuthService.reset_password(
                session=session,
                email=request_data.email,
                new_password=request_data.new_password,
                commit_self=False,
            )

            # Revoke all tokens for security
            user = await user_db.get_one_by_conditions(
                session=session,
                conditions=[user_db.model.email == request_data.email],
            )
            if user:
                await AuthService.revoke_all_user_tokens(
                    session=session,
                    user_id=user.id,
                    commit_self=False,
                )

        return MessageResponse(message="Password has been reset successfully")

    except OTPInvalidException:
        raise OTPInvalidException("Invalid verification code")
    except TooManyAttemptsException:
        raise TooManyAttemptsException(
            "Too many verification attempts. Please request a new code."
        )
    except AuthenticationException:
        raise


@router.post(
    "/password/change",
    response_model=MessageResponse,
    summary="Change password",
    description="""
## Change Password

Update the password for the currently authenticated user. Requires
verification of the current password for security.

### Authentication Required

```http
Authorization: Bearer <access_token>
```

### Request Body

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `current_password` | string | ✅ | User's current password |
| `new_password` | string | ✅ | New password (see requirements) |

### Password Requirements

- Minimum **8 characters**
- At least **one uppercase letter** (A-Z)
- At least **one lowercase letter** (a-z)
- At least **one digit** (0-9)

### Success Response (200)

```json
{
  "message": "Password changed successfully. You have been signed out from other devices.",
  "success": true
}
```

### Security Actions on Success

1. ✅ Password updated
2. ✅ **All other sessions revoked** (current session preserved)
3. ✅ Event logged for audit trail

### Error Responses

| Status | Reason |
|--------|--------|
| `401 Unauthorized` | Not authenticated or current password incorrect |
| `422 Unprocessable Entity` | Password requirements not met |

### Notes

- OAuth-only users must first set a password via different flow
- Current session remains active after password change
- All **other** devices/sessions are signed out
- Consider using this when security is a concern
""",
    responses={
        401: {
            "description": "Not authenticated or current password incorrect",
            "content": {
                "application/json": {
                    "examples": {
                        "not_authenticated": {
                            "summary": "Not authenticated",
                            "value": {"detail": "Not authenticated"},
                        },
                        "wrong_password": {
                            "summary": "Current password incorrect",
                            "value": {"detail": "Current password is incorrect"},
                        },
                    }
                }
            },
        },
    },
)
async def change_password(
    request_data: ChangePasswordRequest,
    user: CurrentActiveUser,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> MessageResponse:
    """
    Change password for the authenticated user.

    This endpoint allows authenticated users to update their password.
    The current password must be verified before setting the new one.
    For security, all other sessions are revoked after the password change.

    Args:
        request_data (ChangePasswordRequest): The change request containing:
            - current_password: The user's current password for verification
            - new_password: The new password to set (must meet requirements)
        user (CurrentActiveUser): The currently authenticated user, injected
            via FastAPI dependency.
        session (AsyncSession): The async database session injected via
            dependency injection.

    Returns:
        MessageResponse: A response object containing:
            - message: Confirmation that password was changed successfully
            - success: Boolean indicating operation success

    Raises:
        InvalidCredentialsException: If the current password is incorrect.
        HTTPException (401): If the user is not authenticated.
        AuthenticationException: If there's a general authentication error.

    Note:
        After changing the password, all sessions except the current one
        are revoked. The user remains signed in on the current device but
        must sign in again on all other devices.
    """
    try:
        async with session.begin():
            await AuthService.change_password(
                session=session,
                user=user,
                current_password=request_data.current_password,
                new_password=request_data.new_password,
                revoke_tokens=True,
                commit_self=False,
            )

        return MessageResponse(
            message="Password changed successfully. You have been signed out from other devices."
        )

    except InvalidCredentialsException:
        raise InvalidCredentialsException("Current password is incorrect")
    except AuthenticationException:
        raise


# =============================================================================
# Profile Endpoints
# =============================================================================


@router.get(
    "/me",
    response_model=ProfileResponse,
    summary="Get current user profile",
    description="""
## Get Current User Profile

Retrieve the complete profile information for the authenticated user,
including account status, OAuth connections, and metadata.

### Authentication Required

```http
Authorization: Bearer <access_token>
```

### Success Response (200)

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "email": "user@example.com",
  "email_verified": true,
  "full_name": "John Doe",
  "avatar_url": "https://example.com/avatar.jpg",
  "is_active": true,
  "created_at": "2024-01-15T10:30:00Z",
  "updated_at": "2024-01-20T14:22:00Z",
  "has_password": true,
  "oauth_providers": ["google", "github"]
}
```

### Response Fields

| Field | Type | Description |
|-------|------|-------------|
| `id` | UUID | Unique user identifier |
| `email` | string | User's email address |
| `email_verified` | boolean | Whether email is verified |
| `full_name` | string | User's display name |
| `avatar_url` | string | URL to profile picture |
| `is_active` | boolean | Account active status |
| `created_at` | datetime | Account creation timestamp |
| `updated_at` | datetime | Last profile update timestamp |
| `has_password` | boolean | `true` if user can sign in with password |
| `oauth_providers` | array | List of linked OAuth providers |

### Understanding `has_password`

| Value | Meaning |
|-------|--------|
| `true` | User signed up with email/password OR has set a password |
| `false` | OAuth-only user, cannot use password signin |

### Error Responses

| Status | Reason |
|--------|--------|
| `401 Unauthorized` | Missing or invalid access token |
| `404 Not Found` | User deleted (edge case) |
""",
    responses={
        401: {
            "description": "Not authenticated",
            "content": {
                "application/json": {"example": {"detail": "Not authenticated"}}
            },
        },
        404: {
            "description": "User not found (rare edge case)",
            "content": {"application/json": {"example": {"detail": "User not found"}}},
        },
    },
)
async def get_profile(
    user: CurrentActiveUser,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> ProfileResponse:
    """
    Retrieve the authenticated user's complete profile information.

    This endpoint returns detailed profile data for the currently
    authenticated user, including account status, OAuth provider
    connections, and metadata timestamps.

    Args:
        user (CurrentActiveUser): The currently authenticated user, injected
            via FastAPI dependency. Must have a valid access token.
        session (AsyncSession): The async database session injected via
            dependency injection.

    Returns:
        ProfileResponse: A response object containing:
            - id: Unique user identifier (UUID)
            - email: User's email address
            - email_verified: Whether email has been verified
            - full_name: User's display name
            - avatar_url: URL to profile picture (may be None)
            - is_active: Account active status
            - created_at: Account creation timestamp
            - updated_at: Last profile modification timestamp
            - has_password: Whether user can sign in with password
            - oauth_providers: List of linked OAuth providers

    Raises:
        HTTPException (401): If the user is not authenticated or the
            access token is invalid/expired.
        HTTPException (404): If the user record was deleted (edge case).

    Note:
        The has_password field indicates whether the user registered with
        email/password or has set a password. OAuth-only users will have
        this set to False until they explicitly set a password.
    """
    # Reload user with OAuth accounts
    reloaded_user = await user_db.get_by_id(
        session=session,
        id=user.id,
        options=[user_db.oauth_accounts_loader],
    )
    if reloaded_user is None:
        raise HTTPException(status_code=404, detail="User not found")

    return _build_profile_response(reloaded_user)


@router.get(
    "/me/avatar/upload-credentials",
    response_model=CloudinaryUploadCredentials,
    summary="Get avatar upload credentials",
    description="""
## Get Avatar Upload Credentials

Generate signed Cloudinary credentials for secure client-side profile picture upload.
The frontend can use these credentials to upload directly to Cloudinary without
exposing sensitive API secrets.

### Authentication Required

```http
Authorization: Bearer <access_token>
```

### Success Response (200)

```json
{
  "upload_url": "https://api.cloudinary.com/v1_1/your-cloud/image/upload",
  "api_key": "123456789012345",
  "timestamp": 1706745600,
  "signature": "abcdef1234567890abcdef1234567890abcdef12",
  "cloud_name": "your-cloud",
  "folder": "avatars",
  "resource_type": "image",
  "upload_preset": null,
  "eager": null
}
```

### Response Fields

| Field | Type | Description |
|-------|------|-------------|
| `upload_url` | string | Cloudinary upload endpoint URL |
| `api_key` | string | Cloudinary API key (safe for frontend) |
| `timestamp` | integer | Unix timestamp for signature validation |
| `signature` | string | Signed hash for secure upload authentication |
| `cloud_name` | string | Your Cloudinary cloud name |
| `folder` | string | Target folder for uploaded avatars |
| `resource_type` | string | Resource type (`image`) |
| `upload_preset` | string | Upload preset (if configured) |
| `eager` | string | Eager transformations (if any) |

### Frontend Usage Example

```javascript
// 1. Get credentials from this endpoint
const response = await fetch('/auth/me/avatar/upload-credentials', {
  headers: { 'Authorization': `Bearer ${accessToken}` }
});
const credentials = await response.json();

// 2. Upload directly to Cloudinary
const formData = new FormData();
formData.append('file', selectedFile);
formData.append('api_key', credentials.api_key);
formData.append('timestamp', credentials.timestamp);
formData.append('signature', credentials.signature);
formData.append('folder', credentials.folder);

const uploadResponse = await fetch(credentials.upload_url, {
  method: 'POST',
  body: formData
});
const result = await uploadResponse.json();

// 3. Update profile with the returned URL
await fetch('/auth/me', {
  method: 'PATCH',
  headers: {
    'Authorization': `Bearer ${accessToken}`,
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({ avatar_url: result.secure_url })
});
```

### Error Responses

| Status | Reason |
|--------|--------|
| `401 Unauthorized` | Missing or invalid access token |
| `500 Internal Server Error` | Cloudinary not configured |
| `503 Service Unavailable` | Failed to generate credentials |

### Notes

- Credentials are **time-limited** (signature includes timestamp)
- Files are uploaded to the `avatars` folder in Cloudinary
- Only **image** uploads are allowed with these credentials
- After upload, use `PATCH /auth/me` to update `avatar_url`
""",
    responses={
        401: {
            "description": "Not authenticated",
            "content": {
                "application/json": {"example": {"detail": "Not authenticated"}}
            },
        },
        500: {
            "description": "Cloudinary not configured",
            "content": {
                "application/json": {
                    "example": {"detail": "Cloudinary is not properly configured."}
                }
            },
        },
        503: {
            "description": "Failed to generate credentials",
            "content": {
                "application/json": {
                    "example": {"detail": "Failed to generate upload credentials"}
                }
            },
        },
    },
)
async def get_avatar_upload_credentials(
    user: CurrentActiveUser,
) -> CloudinaryUploadCredentials:
    """
    Generate signed Cloudinary credentials for secure client-side avatar upload.

    This endpoint generates all necessary parameters (signature, timestamp,
    api_key, etc.) that the frontend needs to upload a profile picture
    directly to Cloudinary without exposing the API secret.

    Args:
        user (CurrentActiveUser): The currently authenticated user, injected
            via FastAPI dependency. Used to ensure only authenticated users
            can generate upload credentials.

    Returns:
        CloudinaryUploadCredentials: A Pydantic model containing:
            - upload_url: The Cloudinary upload endpoint URL
            - api_key: The Cloudinary API key (safe to expose)
            - timestamp: Unix timestamp used for signing
            - signature: The generated signature for the upload
            - cloud_name: The Cloudinary cloud name
            - folder: Target folder ("avatars")
            - resource_type: Set to "image" for profile pictures

    Raises:
        HTTPException (401): If the user is not authenticated.
        AppException (500): If Cloudinary is not properly configured.
        AppException (503): If signature generation fails.

    Note:
        The generated credentials are time-sensitive. The frontend should
        use them promptly after receiving them. After uploading to Cloudinary,
        the frontend should call PATCH /auth/me with the returned secure_url
        to update the user's avatar_url.
    """
    auth_logger.info(f"Generating avatar upload credentials for user {user.id}")
    return CloudinaryService.generate_upload_credentials(
        folder="avatars",
        resource_type="image",
    )


@router.patch(
    "/me",
    response_model=ProfileResponse,
    summary="Update user profile",
    description="""
## Update User Profile

Partially update the authenticated user's profile. Only provided fields
are updated; omitted fields remain unchanged.

### Authentication Required

```http
Authorization: Bearer <access_token>
```

### Request Body (all fields optional)

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `full_name` | string | 1-255 chars | User's display name |
| `avatar_url` | string | max 512 chars | URL to profile picture |

### Example Request

```json
{
  "full_name": "Jane Doe"
}
```

Only `full_name` will be updated; `avatar_url` remains unchanged.

### Success Response (200)

Returns the complete updated profile:

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "email": "user@example.com",
  "email_verified": true,
  "full_name": "Jane Doe",
  "avatar_url": "https://example.com/avatar.jpg",
  "is_active": true,
  "created_at": "2024-01-15T10:30:00Z",
  "updated_at": "2024-01-21T09:15:00Z",
  "has_password": true,
  "oauth_providers": ["google"]
}
```

### Error Responses

| Status | Reason |
|--------|--------|
| `401 Unauthorized` | Missing or invalid access token |
| `404 Not Found` | User deleted (edge case) |
| `422 Unprocessable Entity` | Validation failed (e.g., name too long) |

### Notes

- **Email cannot be changed** via this endpoint (requires verification flow)
- Empty request body (`{}`) is valid (no changes made)
- `updated_at` timestamp is refreshed on any change
""",
    responses={
        401: {
            "description": "Not authenticated",
            "content": {
                "application/json": {"example": {"detail": "Not authenticated"}}
            },
        },
        404: {
            "description": "User not found (rare edge case)",
            "content": {"application/json": {"example": {"detail": "User not found"}}},
        },
    },
)
async def update_profile(
    request_data: ProfileUpdateRequest,
    user: CurrentActiveUser,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> ProfileResponse:
    """
    Partially update the authenticated user's profile.

    This endpoint allows users to update specific profile fields without
    affecting others. Only provided fields are updated; omitted fields
    remain unchanged (PATCH semantics).

    Args:
        request_data (ProfileUpdateRequest): The update request containing
            optional fields:
            - full_name: New display name (1-255 characters)
            - avatar_url: New profile picture URL (max 512 characters)
        user (CurrentActiveUser): The currently authenticated user, injected
            via FastAPI dependency.
        session (AsyncSession): The async database session injected via
            dependency injection.

    Returns:
        ProfileResponse: The complete updated profile containing all fields
            including id, email, full_name, avatar_url, oauth_providers, etc.

    Raises:
        HTTPException (401): If the user is not authenticated or the
            access token is invalid/expired.
        HTTPException (404): If the user record was deleted (edge case).
        HTTPException (422): If validation fails (e.g., name too long).

    Note:
        Email cannot be changed via this endpoint as it requires a separate
        verification flow. An empty request body is valid and results in
        no changes. The updated_at timestamp is refreshed on any modification.
    """
    # Build update data (only include provided fields)
    update_data = {}
    if request_data.full_name is not None:
        update_data["full_name"] = request_data.full_name
    if request_data.avatar_url is not None:
        update_data["avatar_url"] = request_data.avatar_url

    async with session.begin():
        if update_data:
            await user_db.update(
                session=session,
                id=user.id,
                updates=update_data,
                commit_self=False,
            )

        # Reload user with OAuth accounts
        reloaded_user = await user_db.get_by_id(
            session=session,
            id=user.id,
            options=[user_db.oauth_accounts_loader],
        )
        if reloaded_user is None:
            raise HTTPException(status_code=404, detail="User not found")

    return _build_profile_response(reloaded_user)


@router.delete(
    "/me",
    response_model=MessageResponse,
    summary="Delete account",
    description="""
## Delete User Account

Permanently delete (soft delete) the authenticated user's account.
This action signs out all devices and marks the account as deleted.

### Authentication Required

```http
Authorization: Bearer <access_token>
```

### Success Response (200)

```json
{
  "message": "Account has been deleted",
  "success": true
}
```

### What Happens on Deletion

1. ✅ Account marked as **soft deleted** (not permanently removed)
2. ✅ All refresh tokens **revoked** (signed out everywhere)
3. ✅ Email becomes **available** for new registration
4. ✅ OAuth connections **preserved** (for potential recovery)
5. ✅ Event **logged** for audit trail

### Soft Delete vs Hard Delete

| Aspect | Soft Delete (Current) |
|--------|----------------------|
| Data retained | ✅ Yes (configurable period) |
| Can recover | ⚠️ Contact support |
| Email reusable | ✅ Yes |
| Tokens valid | ❌ No |

### Error Responses

| Status | Reason |
|--------|--------|
| `401 Unauthorized` | Missing or invalid access token |

### ⚠️ Warning

This action:
- **Signs out** the user from all devices immediately
- Cannot be easily undone by the user
- May result in **data loss** after the retention period

### Notes

- Consider implementing a confirmation step in your UI
- Account recovery may be possible within a grace period (contact support)
- Associated data (posts, comments, etc.) handling depends on application policy
""",
    responses={
        401: {
            "description": "Not authenticated",
            "content": {
                "application/json": {"example": {"detail": "Not authenticated"}}
            },
        },
    },
)
async def delete_account(
    user: CurrentActiveUser,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> MessageResponse:
    """
    Soft delete the authenticated user's account and revoke all tokens.

    This endpoint permanently marks the user's account as deleted and
    revokes all active sessions. The account data is retained for a
    configurable period before permanent deletion.

    Args:
        user (CurrentActiveUser): The currently authenticated user, injected
            via FastAPI dependency. Must have a valid access token.
        session (AsyncSession): The async database session injected via
            dependency injection.

    Returns:
        MessageResponse: A response object containing:
            - message: Confirmation that account was deleted
            - success: Boolean indicating operation success

    Raises:
        HTTPException (401): If the user is not authenticated or the
            access token is invalid/expired.
        AuthenticationException: If there's a general authentication error.

    Note:
        This performs a soft delete, meaning the account data is retained
        temporarily. All refresh tokens are immediately revoked, signing
        the user out from all devices. The email address becomes available
        for new registrations. Account recovery may be possible within
        a grace period by contacting support.
    """
    async with session.begin():
        # Soft delete user
        await user_db.soft_delete(
            session=session,
            id=user.id,
            commit_self=False,
        )

        # Revoke all tokens
        await AuthService.revoke_all_user_tokens(
            session=session,
            user_id=user.id,
            commit_self=False,
        )

    auth_logger.info(f"Account deleted: {user.email}")

    return MessageResponse(message="Account has been deleted")


# =============================================================================
# Session Management Endpoints
# =============================================================================


@router.post(
    "/sessions",
    response_model=ActiveSessionsResponse,
    summary="Get active sessions",
    description="""
## List Active Sessions

Retrieve all active sessions (refresh tokens) for the authenticated user.
Useful for session management UI where users can view and revoke sessions.

### Authentication Required

```http
Authorization: Bearer <access_token>
```

### Request Body

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `refresh_token` | string | ✅ | Current session's refresh token (to identify current session) |

### Why POST instead of GET?

The current refresh token is needed to identify which session is the
"current" one. Since tokens should not be passed in URLs (security),
this endpoint uses POST with a request body.

### Success Response (200)

```json
{
  "sessions": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "device_info": "Chrome 120 on Windows",
      "created_at": "2024-01-20T10:30:00Z",
      "expires_at": "2024-01-27T10:30:00Z",
      "is_current": true
    },
    {
      "id": "660f9500-f30c-52e5-b827-557766551111",
      "device_info": "Safari on iPhone",
      "created_at": "2024-01-18T14:22:00Z",
      "expires_at": "2024-02-17T14:22:00Z",
      "is_current": false
    }
  ],
  "total": 2
}
```

### Session Fields

| Field | Type | Description |
|-------|------|-------------|
| `id` | UUID | Session identifier |
| `device_info` | string | Browser/device description (from User-Agent) |
| `created_at` | datetime | When session was created (sign-in time) |
| `expires_at` | datetime | When refresh token expires |
| `is_current` | boolean | `true` if this is the requesting session |

### Understanding `expires_at`

| Sign-in Type | Expiration |
|--------------|------------|
| Normal (`remember_me: false`) | 7 days from sign-in |
| Extended (`remember_me: true`) | 30 days from sign-in |

### Error Responses

| Status | Reason |
|--------|--------|
| `401 Unauthorized` | Missing or invalid access token |
| `422 Unprocessable Entity` | Missing refresh_token in body |

### Use Cases

- 📱 **Session management UI** - Show users their active sessions
- 🔒 **Security audit** - Check for unauthorized sessions
- 🧹 **Cleanup** - Identify old sessions to revoke

### Notes

- Only **active** (non-expired, non-revoked) sessions are returned
- `device_info` may be `null` if User-Agent was not available
- Use `/signout` to revoke individual sessions
- Use `/signout/all` to revoke all sessions at once
""",
    responses={
        401: {
            "description": "Not authenticated",
            "content": {
                "application/json": {"example": {"detail": "Not authenticated"}}
            },
        },
    },
)
async def get_sessions(
    user: CurrentActiveUser,
    request_data: RefreshTokenRequest,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> ActiveSessionsResponse:
    """
    List all active sessions for the authenticated user.

    This endpoint retrieves all non-expired, non-revoked sessions (refresh
    tokens) for the current user. It identifies which session is the
    "current" one by comparing the provided refresh token.

    Args:
        user (CurrentActiveUser): The currently authenticated user, injected
            via FastAPI dependency.
        request_data (RefreshTokenRequest): The request containing:
            - refresh_token: Current session's refresh token to identify
              which session is the "current" one in the response.
        session (AsyncSession): The async database session injected via
            dependency injection.

    Returns:
        ActiveSessionsResponse: A response object containing:
            - sessions: List of active session objects, each with:
                - id: Session identifier (UUID)
                - device_info: Browser/device description from User-Agent
                - created_at: When the session was created (sign-in time)
                - expires_at: When the refresh token expires
                - is_current: True if this is the requesting session
            - total: Total count of active sessions

    Raises:
        HTTPException (401): If the user is not authenticated or the
            access token is invalid/expired.
        HTTPException (422): If the refresh_token is missing from body.

    Note:
        This endpoint uses POST instead of GET because the refresh token
        should not be passed in URLs for security reasons. The device_info
        may be null if the User-Agent header was not available during signin.
    """
    # Get current token hash for comparison
    current_token_hash = AuthService.hash_token(request_data.refresh_token)

    sessions = await AuthService.get_active_sessions(
        session=session,
        user_id=user.id,
    )

    session_list = [
        ActiveSessionResponse(
            id=s.id,
            device_info=s.device_info,
            created_at=s.created_at,
            expires_at=s.expires_at,
            is_current=s.token_hash == current_token_hash,
        )
        for s in sessions
    ]

    return ActiveSessionsResponse(
        sessions=session_list,
        total=len(session_list),
    )


__all__ = ["router"]
