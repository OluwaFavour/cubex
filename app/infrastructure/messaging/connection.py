import aio_pika

from app.shared.config import settings

_connection: aio_pika.RobustConnection | None = None


async def get_connection() -> aio_pika.RobustConnection:
    """
    Asynchronously retrieves a robust connection to RabbitMQ.

    If a connection does not exist or is closed, a new robust connection is established
    using the URL specified in the application settings. Otherwise, the existing connection
    is returned.

    Returns:
        aio_pika.RobustConnection: An active robust connection to RabbitMQ.
    """
    global _connection
    if _connection is None or _connection.is_closed:
        _connection = await aio_pika.connect_robust(settings.RABBITMQ_URL)  # type: ignore[assignment]
    return _connection  # type: ignore[return-value]
