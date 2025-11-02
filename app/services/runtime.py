"""Async helpers reused by the Reflex UI."""

import asyncio


def run_async(coro):
    """Run an async coroutine from synchronous code.

    Mirrors the Streamlit-era helper so existing backend services can be reused.
    """

    try:
        asyncio.get_running_loop()
    except RuntimeError:
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





