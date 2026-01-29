from fastapi import Request, status
from fastapi.responses import JSONResponse

from app.shared.config import request_logger
from app.shared.exceptions.types import AppException, DatabaseException


async def general_exception_handler(request: Request, exc: AppException):
    """
    Handles general exceptions by returning a JSON response with the error message.

    Args:
        request: The request object.
        exc (AppException): The exception instance.

    Returns:
        JSONResponse: A response containing the error message and status code 500.
    """
    request_logger.error(f"GeneralException: {exc}")
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": f"An unexpected error occurred.\n{str(exc)}"},
    )


async def database_exception_handler(request: Request, exc: DatabaseException):
    """
    Handles database exceptions by returning a JSON response with the error message.

    Args:
        request: The request object.
        exc (DatabaseException): The database exception instance.

    Returns:
        JSONResponse: A response containing the error message and status code 500.
    """
    request_logger.error(f"DatabaseException: {exc}")
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": f"A database error occurred.\n{str(exc)}"},
    )


exception_schema = {
    status.HTTP_500_INTERNAL_SERVER_ERROR: {
        "description": "Internal Server Error",
        "content": {
            "application/json": {
                "example": {"detail": "Some internal server error message"},
            }
        },
    },
    status.HTTP_500_INTERNAL_SERVER_ERROR: {
        "description": "Database Error",
        "content": {
            "application/json": {
                "example": {"detail": "A database error occurred."},
            }
        },
    },
}
