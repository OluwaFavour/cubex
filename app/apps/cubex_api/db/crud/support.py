"""
CRUD operations for support models.

This module provides database operations for sales requests.
"""

from app.apps.cubex_api.db.models.support import SalesRequest
from app.core.db.crud.base import BaseDB


class SalesRequestDB(BaseDB[SalesRequest]):
    """CRUD operations for SalesRequest model."""

    def __init__(self):
        """Initialize with SalesRequest model."""
        super().__init__(SalesRequest)


# Global instance for dependency injection
sales_request_db = SalesRequestDB()


__all__ = [
    "SalesRequestDB",
    "sales_request_db",
]
