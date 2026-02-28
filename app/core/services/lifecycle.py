"""Post-signup hook registry — decouples core auth from app-specific setup.

Apps register their hooks at startup; the auth router calls
``run_post_signup_hooks`` after a user's first successful sign-up.

Usage (registration, in each app's startup or a central place)::

    from app.core.services.lifecycle import register_post_signup_hook
    register_post_signup_hook(my_app_setup_callback)

Hook signature::

    async def my_hook(session: AsyncSession, user: User) -> None: ...

Hooks are called in registration order. Individual failures are logged
but do **not** abort the sign-up flow.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Callable, Coroutine, Any

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
    from app.core.db.models import User

PostSignupHook = Callable[["AsyncSession", "User"], Coroutine[Any, Any, None]]

_hooks: list[PostSignupHook] = []

logger = logging.getLogger(__name__)


def register_post_signup_hook(hook: PostSignupHook) -> None:
    """Register a coroutine to be called after user sign-up."""
    _hooks.append(hook)


async def run_post_signup_hooks(session: "AsyncSession", user: "User") -> None:
    """Execute all registered post-signup hooks, logging failures."""
    for hook in _hooks:
        try:
            await hook(session, user)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Post-signup hook %s failed for user %s: %s",
                hook.__qualname__,
                user.id,
                exc,
            )


def reset_hooks() -> None:
    """Clear all registered hooks — intended for test teardown only."""
    _hooks.clear()
