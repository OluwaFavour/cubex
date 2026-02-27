"""
Utility functions for the application.

- Secure password hashing using bcrypt
- Password verification against hashed values
- JWT token creation and decoding
- HMAC-based OTP hashing for queryable secure storage
"""

from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import secrets
from typing import Any
import uuid

import aiofiles
import bcrypt
from fastapi import FastAPI
import jwt

from app.core.config import settings, utils_logger


def hash_password(password: str | None) -> str:
    """
    Hash a password using bcrypt with a secure salt.

    This function uses bcrypt, which is specifically designed for password hashing
    and includes:
    - Automatic salt generation (random for each hash)
    - Adaptive cost factor (can be increased as hardware improves)
    - Resistance to rainbow table attacks

    Args:
        password: The plain text password to hash. Cannot be None.

    Returns:
        str: The bcrypt hashed password (60 characters).
             Format: $2b$[cost]$[22 character salt][31 character hash]

    Raises:
        ValueError: If password is None.

    Examples:
        >>> hashed = hash_password("MySecurePassword123")
        >>> print(len(hashed))
        60
        >>> hashed.startswith("$2b$")
        True

    Security Notes:
        - Uses bcrypt's default work factor (currently 12 rounds)
        - Each call generates a unique hash due to random salt
        - Same password will produce different hashes (by design)
        - Resistant to timing attacks
    """
    if password is None:
        utils_logger.error("Attempted to hash None password")
        raise ValueError("Password cannot be None")

    try:
        password_bytes = password.encode("utf-8")

        # Bcrypt has a 72-byte limit, truncate if necessary
        # This is secure because 72 bytes of entropy is more than sufficient
        if len(password_bytes) > 72:
            utils_logger.debug(
                f"Password exceeds 72 bytes ({len(password_bytes)} bytes), truncating to 72 bytes"
            )
            password_bytes = password_bytes[:72]

        # bcrypt.gensalt() uses a default of 12 rounds which is secure and performant
        salt = bcrypt.gensalt()
        hashed = bcrypt.hashpw(password_bytes, salt)

        utils_logger.info("Password hashed successfully")
        # Return as string (decoded from bytes)
        return hashed.decode("utf-8")

    except Exception as e:
        utils_logger.error(f"Failed to hash password: {type(e).__name__} - {str(e)}")
        raise


def verify_password(password: str | None, hashed_password: str | None) -> bool:
    """
    Verify a password against a bcrypt hash.

    This function safely compares a plain text password with a bcrypt hash
    using constant-time comparison to prevent timing attacks.

    Args:
        password: The plain text password to verify. Can be None.
        hashed_password: The bcrypt hash to verify against. Can be None.

    Returns:
        bool: True if password matches the hash, False otherwise.
              Returns False for any invalid inputs (None, invalid hash format, etc.)

    Examples:
        >>> hashed = hash_password("MyPassword123")
        >>> verify_password("MyPassword123", hashed)
        True
        >>> verify_password("WrongPassword", hashed)
        False
        >>> verify_password(None, hashed)
        False

    Security Notes:
        - Uses constant-time comparison (bcrypt.checkpw)
        - Safe against timing attacks
        - Handles invalid inputs gracefully without raising exceptions
        - Case-sensitive comparison
    """
    if password is None or hashed_password is None:
        utils_logger.warning(
            "Password verification attempted with None value(s): "
            f"password={'None' if password is None else 'provided'}, "
            f"hashed_password={'None' if hashed_password is None else 'provided'}"
        )
        return False

    try:
        password_bytes = password.encode("utf-8")
        hashed_bytes = hashed_password.encode("utf-8")

        # Bcrypt has a 72-byte limit, truncate if necessary (same as in hash_password)
        if len(password_bytes) > 72:
            utils_logger.debug(
                f"Password exceeds 72 bytes ({len(password_bytes)} bytes), truncating to 72 bytes for verification"
            )
            password_bytes = password_bytes[:72]

        # Use bcrypt's constant-time comparison
        result = bcrypt.checkpw(password_bytes, hashed_bytes)

        if result:
            utils_logger.info("Password verification successful")
        else:
            utils_logger.warning("Password verification failed: incorrect password")

        return result

    except (ValueError, AttributeError) as e:
        # Invalid hash format or encoding issues
        utils_logger.warning(
            f"Password verification failed due to invalid hash format or encoding: {type(e).__name__}"
        )
        return False
    except Exception as e:
        # Catch any other unexpected errors and return False
        # This ensures the function never crashes
        utils_logger.error(
            f"Unexpected error during password verification: {type(e).__name__} - {str(e)}"
        )
        return False


def create_jwt_token(
    data: dict[str, Any] | None, expires_delta: timedelta | None = None
) -> str:
    """
    Create a JWT token with the given data and expiration time.

    This function encodes a dictionary into a JWT (JSON Web Token) using the
    HS256 algorithm with the application's secret key. The token includes an
    expiration claim (exp) for security.

    Args:
        data: Dictionary containing the data to encode in the token.
              Cannot be None. Common keys include 'user_id', 'email', etc.
        expires_delta: Optional timedelta for token expiration.
                      If None, defaults to 15 minutes from now.
                      Can be negative for immediate expiration (testing only).

    Returns:
        str: Encoded JWT token string in the format: header.payload.signature

    Raises:
        ValueError: If data is None.

    Examples:
        >>> from datetime import timedelta
        >>> token = create_jwt_token({"user_id": "123", "email": "user@example.com"})
        >>> print(len(token.split('.')))
        3
        >>> # Custom expiration
        >>> token = create_jwt_token({"user_id": "456"}, expires_delta=timedelta(hours=1))

    Security Notes:
        - Uses HS256 algorithm (HMAC with SHA-256)
        - Signs with JWT_SECRET_KEY from settings
        - Always includes expiration claim (exp) for security
        - Default expiration: 15 minutes
        - Token can be decoded with decode_jwt_token()
    """
    if data is None:
        utils_logger.error("Attempted to create JWT token with None data")
        raise ValueError("Data cannot be None")

    try:
        to_encode = data.copy()

        if expires_delta is None:
            expires_delta = timedelta(minutes=15)

        expire = datetime.now(timezone.utc) + expires_delta
        to_encode["exp"] = expire

        # Add issued-at time for token uniqueness (important for token rotation)
        to_encode["iat"] = datetime.now(timezone.utc)

        to_encode["jti"] = str(uuid.uuid4())

        # Encode the JWT token
        encoded_jwt = jwt.encode(
            to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM
        )

        utils_logger.info(
            f"JWT token created successfully with expiration: {expire.isoformat()}"
        )
        return encoded_jwt

    except Exception as e:
        utils_logger.error(f"Failed to create JWT token: {type(e).__name__} - {str(e)}")
        raise


def decode_jwt_token(token: str | None) -> dict[str, Any] | None:
    """
    Decode and validate a JWT token.

    This function decodes a JWT token and validates its signature and expiration.
    Returns None for any invalid, expired, or tampered tokens.

    Args:
        token: The JWT token string to decode. Can be None or empty.

    Returns:
        dict[str, Any] | None: Dictionary containing the decoded token data
                                 including all original fields plus 'exp' (expiration).
                                 Returns None if token is invalid, expired, or tampered.

    Examples:
        >>> token = create_jwt_token({"user_id": "123"})
        >>> decoded = decode_jwt_token(token)
        >>> print(decoded["user_id"])
        123
        >>> # Invalid token
        >>> decoded = decode_jwt_token("invalid.token.here")
        >>> print(decoded)
        None

    Security Notes:
        - Validates signature using JWT_SECRET_KEY
        - Checks expiration automatically
        - Returns None for any validation failure (safe default)
        - Constant-time signature verification
        - Resistant to timing attacks
    """
    if not token:
        utils_logger.warning(
            f"JWT token decoding attempted with invalid token: "
            f"{'None' if token is None else 'empty string'}"
        )
        return None

    try:
        # Decode and validate the JWT token
        payload = jwt.decode(
            token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
        )

        utils_logger.info("JWT token decoded and validated successfully")
        return payload

    except jwt.ExpiredSignatureError:
        utils_logger.warning("JWT token decoding failed: token has expired")
        return None
    except jwt.InvalidTokenError as e:
        utils_logger.warning(
            f"JWT token decoding failed: invalid token - {type(e).__name__}"
        )
        return None
    except Exception as e:
        utils_logger.error(
            f"Unexpected error during JWT token decoding: {type(e).__name__} - {str(e)}"
        )
        return None


def convert_unix_timestamp_to_datetime(timestamp: int | None) -> datetime | None:
    """
    Convert a Unix timestamp (seconds since epoch) to a timezone-aware datetime object.

    Args:
        timestamp: Unix timestamp in seconds. Can be None.

    Returns:
        A timezone-aware datetime object in UTC corresponding to the given timestamp,
        or None if the input timestamp is None.

    Examples:
        >>> dt = convert_unix_to_datetime(1700000000)
        >>> print(dt.isoformat())
        2023-11-14T06:13:20+00:00

        >>> dt_none = convert_unix_to_datetime(None)
        >>> print(dt_none)
        None
    """
    if timestamp is None:
        return None
    return datetime.fromtimestamp(timestamp, tz=timezone.utc)


def generate_otp_code(length: int = 6) -> str:
    """
    Generate a numeric One-Time Password (OTP) code of specified length.

    Args:
        length: Length of the OTP code to generate. Default is 6.

    Returns:
        A string representing the numeric OTP code.
    """

    # Use secrets module for security-sensitive random numbers
    otp = "".join(secrets.choice("0123456789") for _ in range(length))

    utils_logger.info(f"OTP code of length {length} generated successfully")
    return otp


def mask_otp(otp: str) -> str:
    """
    Mask an OTP code for logging purposes, showing only first and last digit.

    Args:
        otp: The OTP code to mask.

    Returns:
        A masked version of the OTP (e.g., "123456" -> "1****6").

    Examples:
        >>> mask_otp("123456")
        '1****6'
        >>> mask_otp("1234")
        '1**4'
        >>> mask_otp("12")
        '12'
    """
    if len(otp) <= 2:
        return otp

    return f"{otp[0]}{'*' * (len(otp) - 2)}{otp[-1]}"


def hmac_hash_otp(otp: str | None, secret: str | None) -> str:
    """
    Hash an OTP using HMAC-SHA256 for secure, queryable storage.

    Unlike bcrypt, HMAC produces deterministic hashes that can be used
    to query the database directly while still providing security through
    the secret key. This is ideal for OTP verification where the hash
    needs to be queryable.

    Args:
        otp: The OTP code to hash. Cannot be None or empty.
        secret: The secret key for HMAC. Cannot be None or empty.

    Returns:
        str: The HMAC-SHA256 hash as a 64-character hexadecimal string.

    Raises:
        ValueError: If otp or secret is None or empty.

    Examples:
        >>> hashed = hmac_hash_otp("123456", "my_secret_key")
        >>> len(hashed)
        64
        >>> hmac_hash_otp("123456", "my_secret_key") == hashed
        True

    Security Notes:
        - Uses HMAC-SHA256 which is cryptographically secure
        - Deterministic output allows database queries
        - Security depends on keeping the secret key private
        - Different from bcrypt which is designed for passwords
    """
    if not otp:
        utils_logger.error("Attempted to hash None or empty OTP")
        raise ValueError("OTP cannot be None or empty")

    if not secret:
        utils_logger.error("Attempted to hash OTP with None or empty secret")
        raise ValueError("Secret cannot be None or empty")

    try:
        otp_bytes = otp.encode("utf-8")
        secret_bytes = secret.encode("utf-8")

        hash_obj = hmac.new(secret_bytes, otp_bytes, hashlib.sha256)
        hashed = hash_obj.hexdigest()

        utils_logger.debug(f"OTP {mask_otp(otp)} hashed successfully with HMAC-SHA256")
        return hashed

    except Exception as e:
        utils_logger.error(f"Failed to hash OTP: {type(e).__name__} - {str(e)}")
        raise


def hmac_verify_otp(
    otp: str | None, hashed_otp: str | None, secret: str | None
) -> bool:
    """
    Verify an OTP against its HMAC-SHA256 hash using constant-time comparison.

    This function safely compares an OTP with its stored hash using
    constant-time comparison to prevent timing attacks.

    Args:
        otp: The plain text OTP to verify. Can be None.
        hashed_otp: The HMAC-SHA256 hash to verify against. Can be None.
        secret: The secret key used for hashing. Can be None.

    Returns:
        bool: True if OTP matches the hash, False otherwise.
              Returns False for any invalid inputs (None, empty, invalid format).

    Examples:
        >>> hashed = hmac_hash_otp("123456", "secret")
        >>> hmac_verify_otp("123456", hashed, "secret")
        True
        >>> hmac_verify_otp("654321", hashed, "secret")
        False
        >>> hmac_verify_otp(None, hashed, "secret")
        False

    Security Notes:
        - Uses hmac.compare_digest for constant-time comparison
        - Safe against timing attacks
        - Handles invalid inputs gracefully without raising exceptions
    """
    if not otp or not hashed_otp or not secret:
        utils_logger.warning(
            "OTP verification attempted with invalid value(s): "
            f"otp={'None/empty' if not otp else 'provided'}, "
            f"hashed_otp={'None/empty' if not hashed_otp else 'provided'}, "
            f"secret={'None/empty' if not secret else 'provided'}"
        )
        return False

    try:
        try:
            int(hashed_otp, 16)
        except ValueError:
            utils_logger.warning("OTP verification failed: invalid hash format")
            return False

        computed_hash = hmac_hash_otp(otp, secret)

        # Use constant-time comparison to prevent timing attacks
        result = hmac.compare_digest(computed_hash, hashed_otp)

        if result:
            utils_logger.info(f"OTP {mask_otp(otp)} verification successful")
        else:
            utils_logger.warning(f"OTP {mask_otp(otp)} verification failed: mismatch")

        return result

    except Exception as e:
        utils_logger.error(
            f"Unexpected error during OTP verification: {type(e).__name__} - {str(e)}"
        )
        return False


def create_request_fingerprint(
    endpoint: str,
    method: str,
    payload_hash: str,
    usage_estimate: dict | None = None,
) -> str:
    """
    Create a deterministic fingerprint hash for request idempotency.

    This function generates a unique fingerprint based on the request's
    key characteristics. Two requests with identical fingerprints are
    considered the same request for idempotency purposes.

    The fingerprint is computed as HMAC-SHA256 of a canonical JSON
    representation of the request components.

    Args:
        endpoint: The API endpoint path being called.
        method: HTTP method (GET, POST, etc.).
        payload_hash: Hash of the request payload (provided by client).
        usage_estimate: Optional usage estimation dict with keys:
                       input_chars, max_output_tokens, model.

    Returns:
        str: 64-character hexadecimal fingerprint hash.

    Examples:
        >>> fp1 = create_request_fingerprint("/v1/extract", "POST", "abc123")
        >>> fp2 = create_request_fingerprint("/v1/extract", "POST", "abc123")
        >>> fp1 == fp2
        True
        >>> fp3 = create_request_fingerprint("/v1/extract", "POST", "def456")
        >>> fp1 == fp3
        False

    Security Notes:
        - Uses HMAC-SHA256 with a fixed secret for consistency
        - JSON serialization is sorted for deterministic output
        - Same inputs always produce the same fingerprint
    """
    data = {
        "endpoint": endpoint.lower().strip(),
        "method": method.upper().strip(),
        "payload_hash": payload_hash,
        "usage_estimate": None,
    }

    # Normalize usage_estimate if provided
    if usage_estimate:
        data["usage_estimate"] = {
            "input_chars": usage_estimate.get("input_chars"),
            "max_output_tokens": usage_estimate.get("max_output_tokens"),
            "model": usage_estimate.get("model"),
        }

    # Create canonical JSON string (sorted keys for determinism)
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":"))

    # Use HMAC-SHA256 with a fixed secret for consistency
    # The secret doesn't need to be secret here - it's for consistency, not security
    secret = "request_fingerprint_v1"
    hash_obj = hmac.new(
        secret.encode("utf-8"),
        canonical.encode("utf-8"),
        hashlib.sha256,
    )

    fingerprint = hash_obj.hexdigest()
    utils_logger.debug(
        f"Created request fingerprint: endpoint={endpoint}, method={method}, "
        f"fingerprint={fingerprint[:16]}..."
    )

    return fingerprint


def get_device_info(user_agent: str | None) -> str | None:
    """
    Parse user agent string to extract basic device information.

    This is a simple parser that extracts browser and OS information.
    For production use with detailed parsing, consider using user-agents library.

    Args:
        user_agent: User-Agent header string from request

    Returns:
        Parsed device info string or None if user_agent is None

    Examples:
        >>> ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        >>> info = get_device_info(ua)
        >>> "Windows" in info
        True
    """
    if not user_agent:
        return None

    # Simple parsing logic
    device_info_parts = []

    # Detect OS
    if "Windows" in user_agent:
        device_info_parts.append("Windows")
    elif "Mac OS X" in user_agent or "Macintosh" in user_agent:
        device_info_parts.append("macOS")
    elif "Linux" in user_agent and "Android" not in user_agent:
        device_info_parts.append("Linux")
    elif "Android" in user_agent:
        device_info_parts.append("Android")
    elif "iOS" in user_agent or "iPhone" in user_agent or "iPad" in user_agent:
        device_info_parts.append("iOS")

    # Detect browser
    if "Edg/" in user_agent:
        device_info_parts.append("Edge")
    elif "Chrome" in user_agent and "Edg/" not in user_agent:
        device_info_parts.append("Chrome")
    elif "Safari" in user_agent and "Chrome" not in user_agent:
        device_info_parts.append("Safari")
    elif "Firefox" in user_agent:
        device_info_parts.append("Firefox")

    if device_info_parts:
        return " / ".join(device_info_parts)

    # Fallback: truncate user agent if too long
    return user_agent[:100] if len(user_agent) > 100 else user_agent


def generate_openapi_json(app: FastAPI) -> str:
    """
    Generate OpenAPI JSON schema for the given FastAPI application.

    Args:
        app: The FastAPI application instance.

    Returns:
        A pretty-printed JSON string of the OpenAPI schema.
    """
    openapi_schema = app.openapi()

    openapi_json = json.dumps(openapi_schema, indent=4)
    utils_logger.info("OpenAPI JSON schema generated successfully")
    return openapi_json


async def write_to_file_async(file_path: str, data: str) -> None:
    """
    Asynchronously write data to a file.

    Args:
        file_path: Path to the file where data should be written.
        data: The string data to write to the file.

    Returns:
        None
    """
    try:
        async with aiofiles.open(file_path, mode="w", encoding="utf-8") as file:
            await file.write(data)
        utils_logger.info(f"Data written to file {file_path} successfully.")
    except Exception as e:
        utils_logger.error(
            f"Failed to write data to file {file_path}: {type(e).__name__} - {str(e)}"
        )
        raise

