import asyncio
import logging
import os
import runpy
import sys
import traceback


def start(app_dir):
    """Entry point called from ServerService on a background thread."""
    app_dir = os.path.abspath(str(app_dir))
    os.chdir(app_dir)
    if app_dir not in sys.path:
        sys.path.insert(0, app_dir)
    os.environ.setdefault("PYTHONUNBUFFERED", "1")

    log_path = os.path.join(app_dir, "server.log")
    try:
        log_file = open(log_path, "w", buffering=1, encoding="utf-8", errors="replace")
    except Exception:
        log_file = sys.stderr

    sys.stdout = log_file
    sys.stderr = log_file
    logging.basicConfig(
        level=logging.INFO,
        stream=log_file,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        print("=== Telegram-Stremio Android start ===", flush=True)
        runpy.run_module("Backend", run_name="__main__")
    except SystemExit:
        pass
    except BaseException:
        traceback.print_exc(file=log_file)
        log_file.flush()
        raise
