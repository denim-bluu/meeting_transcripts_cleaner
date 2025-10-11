import asyncio


def run_async(coro):
    """Run an async coroutine from Streamlit/UI code.

    Simple and predictable:
    - Try `asyncio.run` (works in typical Streamlit usage)
    - If already inside a running loop, create a fresh loop to execute
    """
    try:
        return asyncio.run(coro)
    except RuntimeError:
        # Fallback when a loop is already running
        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            return loop.run_until_complete(coro)
        finally:
            try:
                loop.close()
            except Exception:
                pass
