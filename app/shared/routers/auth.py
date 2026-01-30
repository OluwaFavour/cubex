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
from app.shared.services.oauth import OAuthStateManager
from app.shared.utils import get_device_info


router = APIRouter(tags=["Authentication"])


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


# =============================================================================
# Email Signup Endpoints
# =============================================================================


@router.post(
    "/signup",
    response_model=SignupResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Sign up with email",
    description="Create a new account with email and password. "
    "A verification code will be sent to the email address.",
)
async def signup(
    request_data: SignupRequest,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> SignupResponse:
    """
    Sign up a new user with email and password.

    After signup, an OTP verification code is sent to the email.
    The user must verify their email using the /signup/verify endpoint.
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
    description="Verify email with OTP code and receive authentication tokens.",
)
async def verify_signup(
    request_data: OTPVerifyRequest,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> TokenResponse:
    """
    Verify email with OTP and complete the signup process.

    Returns access and refresh tokens on successful verification.
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
    description="Resend the OTP verification code to the email address.",
)
async def resend_verification(
    request_data: ResendOTPRequest,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> MessageResponse:
    """
    Resend the verification code to the user's email.
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
    description="Authenticate with email and password. "
    "Set remember_me=true for extended session (30 days).",
)
async def signin(
    request_data: LoginRequest,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> TokenResponse:
    """
    Sign in with email and password.

    Returns access and refresh tokens on successful authentication.
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
    description="Get a new access token using a valid refresh token.",
)
async def refresh_token(
    request_data: RefreshTokenRequest,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> AccessTokenResponse:
    """
    Refresh the access token using a valid refresh token.
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
    description="Revoke the current refresh token (sign out from this device).",
)
async def signout(
    request_data: RefreshTokenRequest,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> MessageResponse:
    """
    Sign out by revoking the refresh token.
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
    description="Revoke all refresh tokens (sign out from all devices).",
)
async def signout_all(
    user: CurrentActiveUser,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> MessageResponse:
    """
    Sign out from all devices by revoking all refresh tokens.
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
    description="Get the authorization URL to redirect user for OAuth consent.",
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
    Initiate OAuth flow by generating authorization URL.

    The state parameter is signed and includes:
    - remember_me preference
    - callback_url for frontend redirect

    If callback_url is provided, it must be in the allowed CORS origins.
    In production, HTTPS is required.
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
    description="Handle OAuth provider callback and exchange code for tokens.",
    responses={
        307: {"description": "Redirect to frontend callback URL with tokens"},
    },
)
async def oauth_callback(
    provider: OAuthProviders,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_async_session)],
    code: Annotated[str, Query(description="Authorization code from provider")],
    state: Annotated[str, Query(description="State parameter for CSRF validation")],
) -> TokenResponse | RedirectResponse:
    """
    Handle OAuth callback from the provider.

    Validates state, exchanges code for tokens, creates/links user,
    and either:
    - Returns TokenResponse if no callback_url was provided
    - Redirects to callback_url with tokens in URL fragment
    """
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
            return RedirectResponse(
                url=f"{callback_url}?error={e.message}",
                status_code=307,
            )
        raise

    except Exception as e:
        auth_logger.error(f"OAuth callback failed unexpectedly: {e}")
        if callback_url:
            return RedirectResponse(
                url=f"{callback_url}?error=oauth_error",
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
    description="Send a password reset OTP to the user's email.",
)
async def request_password_reset(
    request_data: PasswordResetRequest,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> MessageResponse:
    """
    Request a password reset by sending OTP to email.

    For security, always returns success even if email doesn't exist.
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
    description="Reset password with OTP verification.",
)
async def confirm_password_reset(
    request_data: PasswordResetConfirmRequest,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> MessageResponse:
    """
    Confirm password reset with OTP and set new password.
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
    description="Change password for authenticated user.",
)
async def change_password(
    request_data: ChangePasswordRequest,
    user: CurrentActiveUser,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> MessageResponse:
    """
    Change password for the authenticated user.

    Requires current password verification. Revokes all other sessions.
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
    description="Get the profile of the currently authenticated user.",
)
async def get_profile(
    user: CurrentActiveUser,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> ProfileResponse:
    """
    Get the current user's profile.
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


@router.patch(
    "/me",
    response_model=ProfileResponse,
    summary="Update user profile",
    description="Update the profile of the currently authenticated user.",
)
async def update_profile(
    request_data: ProfileUpdateRequest,
    user: CurrentActiveUser,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> ProfileResponse:
    """
    Update the current user's profile.
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
    description="Soft delete the current user's account.",
)
async def delete_account(
    user: CurrentActiveUser,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> MessageResponse:
    """
    Soft delete the current user's account.

    The account can potentially be recovered within a grace period.
    All refresh tokens are revoked.
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
    description="List all active sessions for the current user.",
)
async def get_sessions(
    user: CurrentActiveUser,
    request_data: RefreshTokenRequest,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> ActiveSessionsResponse:
    """
    Get all active sessions for the current user.

    Pass the current refresh token to identify which session is current.
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
