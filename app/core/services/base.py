"""Base class for singleton services with managed initialization state."""


class SingletonService:
    """Mixin for services that follow the singleton-via-classmethods pattern.

    Provides:
    - ``_initialized`` flag
    - ``is_initialized()`` class method
    - ``_reset()`` class method for test teardown

    Subclasses must call ``cls._initialized = True`` at the end of their
    own ``init()`` class method. The ``init()`` signature is intentionally
    left open because some services are synchronous while others are
    async and accept different parameters.
    """

    _initialized: bool = False

    @classmethod
    def is_initialized(cls) -> bool:
        """Return whether the service has been initialised."""
        return cls._initialized

    @classmethod
    def _reset(cls) -> None:
        """Reset singleton state — intended for test teardown only."""
        cls._initialized = False
