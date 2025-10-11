import asyncio


def run_async(coro):
    """Run an async coroutine from Streamlit/UI code.

    Keeps implementation simple (KISS). Streamlit typically does not run an
    event loop in the main thread, so asyncio.run is sufficient. If an event
    loop is already running, fall back to creating a new task via asyncio.run.
    """
    try:
        loop = asyncio.get_event_loop()
        # If a loop exists and is running, prefer asyncio.run anyway for clarity
        if loop.is_running():
            return asyncio.run(coro)
        return loop.run_until_complete(coro)
    except RuntimeError:
        # No current event loop
        return asyncio.run(coro)

