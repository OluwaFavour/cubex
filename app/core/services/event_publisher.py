"""Abstract event publisher — decouples core/app code from infrastructure.

At startup the real RabbitMQ publisher is registered; in tests a no-op or
mock can be substituted.

Usage in service code::

    from app.core.services.event_publisher import get_publisher
    await get_publisher()(queue_name, event, headers)

Registration (in ``lifespan``)::

    from app.core.services.event_publisher import register_publisher
    from app.infrastructure.messaging import publish_event
    register_publisher(publish_event)
"""

from __future__ import annotations

from typing import Any, Protocol


class EventPublisher(Protocol):
    """Callable that publishes an event dict to a named queue."""

    async def __call__(
        self,
        queue_name: str,
        event: dict[str, Any],
        headers: dict[str, Any] = ...,
    ) -> None: ...


_publisher: EventPublisher | None = None


def register_publisher(publisher: EventPublisher) -> None:
    """Register the concrete publisher (called once at startup)."""
    global _publisher
    _publisher = publisher


def get_publisher() -> EventPublisher:
    """Return the registered publisher or raise if not yet registered."""
    if _publisher is None:
        raise RuntimeError(
            "No event publisher registered. "
            "Call register_publisher() during application startup."
        )
    return _publisher


def reset_publisher() -> None:
    """Clear the registered publisher — intended for test teardown only."""
    global _publisher
    _publisher = None
