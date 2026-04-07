import asyncio

import pytest


@pytest.mark.asyncio
async def test_main_account_session_coordinator_serializes_same_key_access():
    from backend.services.main_account_session_coordinator import (
        MainAccountSessionCoordinator,
    )

    coordinator = MainAccountSessionCoordinator()
    events = []
    ready = asyncio.Event()

    async def holder():
        async with coordinator.acquire("shopee", "main-a"):
            events.append("holder-enter")
            ready.set()
            await asyncio.sleep(0.05)
            events.append("holder-exit")

    async def waiter():
        await ready.wait()
        async with coordinator.acquire("shopee", "main-a"):
            events.append("waiter-enter")

    await asyncio.gather(holder(), waiter())

    assert events == ["holder-enter", "holder-exit", "waiter-enter"]


@pytest.mark.asyncio
async def test_main_account_session_coordinator_allows_different_keys_to_run_concurrently():
    from backend.services.main_account_session_coordinator import (
        MainAccountSessionCoordinator,
    )

    coordinator = MainAccountSessionCoordinator()
    first_entered = asyncio.Event()
    second_entered = asyncio.Event()

    async def first():
        async with coordinator.acquire("shopee", "main-a"):
            first_entered.set()
            await second_entered.wait()

    async def second():
        async with coordinator.acquire("shopee", "main-b"):
            second_entered.set()
            await first_entered.wait()

    await asyncio.wait_for(asyncio.gather(first(), second()), timeout=1)


@pytest.mark.asyncio
async def test_main_account_session_coordinator_reports_waiter_count():
    from backend.services.main_account_session_coordinator import (
        MainAccountSessionCoordinator,
    )

    coordinator = MainAccountSessionCoordinator()
    acquired = asyncio.Event()
    release = asyncio.Event()

    async def holder():
        async with coordinator.acquire("shopee", "main-a"):
            acquired.set()
            await release.wait()

    holder_task = asyncio.create_task(holder())
    await acquired.wait()

    waiter_task = asyncio.create_task(coordinator.acquire("shopee", "main-a").__aenter__())
    await asyncio.sleep(0.02)

    assert coordinator.waiter_count("shopee", "main-a") == 1

    waiter_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter_task

    release.set()
    await holder_task
