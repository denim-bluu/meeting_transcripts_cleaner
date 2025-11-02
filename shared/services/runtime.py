"""Async helpers for running coroutines from synchronous code."""

import asyncio


def run_async(coro):
    """Run an async coroutine from synchronous code.

    - Use asyncio.run when no event loop is active.
    - Otherwise spin up a temporary loop to execute the coroutine.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        # No running loop; safe to use asyncio.run directly
        return asyncio.run(coro)

    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)
    finally:
        asyncio.set_event_loop(None)
        try:
            loop.close()
        except Exception:
            pass

