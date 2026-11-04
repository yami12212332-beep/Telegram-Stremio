import asyncio
import logging
import os
import runpy
import sys


def start(app_dir):
    """Entry point called from ServerService on a background thread."""
    app_dir = os.path.abspath(str(app_dir))
    os.chdir(app_dir)
    if app_dir not in sys.path:
        sys.path.insert(0, app_dir)
    os.environ.setdefault("PYTHONUNBUFFERED", "1")

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        runpy.run_module("Backend", run_name="__main__")
    except SystemExit:
        pass
    except BaseException:
        logging.exception("Telegram-Stremio Python server crashed")
        raise
