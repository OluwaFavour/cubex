"""
Support models for cubex_api.

"""

from sqlalchemy import (
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db.models.base import BaseModel
from app.core.enums import SalesRequestStatus


class SalesRequest(BaseModel):
    """Model for sales requests."""

    __tablename__ = "sales_requests"

    first_name: Mapped[str] = mapped_column(String(255), nullable=False)
    last_name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[SalesRequestStatus] = mapped_column(
        String(20),
        nullable=False,
        default=SalesRequestStatus.PENDING,
        server_default=SalesRequestStatus.PENDING.value,
    )
