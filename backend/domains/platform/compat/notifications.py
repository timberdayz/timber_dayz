from __future__ import annotations

from typing import Callable, Awaitable, Any


def get_create_notification() -> Callable[..., Awaitable[Any]]:
    """
    Compatibility hook:

    Tests and some external callers monkeypatch `backend.routers.notifications.create_notification`.
    Importing from that module at call time preserves the monkeypatch behavior while keeping the
    dependency explicit and centralized.
    """

    from backend.routers.notifications import create_notification as create_notification_func

    return create_notification_func


async def notify_user_registered(*args: Any, **kwargs: Any) -> Any:
    from backend.routers.notifications import notify_user_registered as notify_user_registered_func

    return await notify_user_registered_func(*args, **kwargs)


async def notify_account_unlocked(*args: Any, **kwargs: Any) -> Any:
    from backend.routers.notifications import notify_account_unlocked as notify_account_unlocked_func

    return await notify_account_unlocked_func(*args, **kwargs)


async def notify_account_locked(*args: Any, **kwargs: Any) -> Any:
    from backend.routers.notifications import notify_account_locked as notify_account_locked_func

    return await notify_account_locked_func(*args, **kwargs)


async def revoke_all_user_sessions(*args: Any, **kwargs: Any) -> Any:
    from backend.routers.notifications import revoke_all_user_sessions as revoke_all_user_sessions_func

    return await revoke_all_user_sessions_func(*args, **kwargs)


async def notify_password_reset(*args: Any, **kwargs: Any) -> Any:
    from backend.routers.notifications import notify_password_reset as notify_password_reset_func

    return await notify_password_reset_func(*args, **kwargs)


async def notify_user_approved(*args: Any, **kwargs: Any) -> Any:
    from backend.routers.notifications import notify_user_approved as notify_user_approved_func

    return await notify_user_approved_func(*args, **kwargs)


async def notify_user_rejected(*args: Any, **kwargs: Any) -> Any:
    from backend.routers.notifications import notify_user_rejected as notify_user_rejected_func

    return await notify_user_rejected_func(*args, **kwargs)


async def notify_user_suspended(*args: Any, **kwargs: Any) -> Any:
    from backend.routers.notifications import notify_user_suspended as notify_user_suspended_func

    return await notify_user_suspended_func(*args, **kwargs)
