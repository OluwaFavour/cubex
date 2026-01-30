from app.infrastructure.messaging.publisher import publish_event


def get_start_consumers():
    """Lazy import to avoid circular dependency."""
    from app.infrastructure.messaging.main import start_consumers

    return start_consumers


# Provide start_consumers via property-like access
async def start_consumers(keep_alive: bool):
    """Start message consumers. Wrapper to avoid circular import."""
    from app.infrastructure.messaging.main import start_consumers as _start_consumers

    return await _start_consumers(keep_alive)


__all__ = ["publish_event", "start_consumers"]
