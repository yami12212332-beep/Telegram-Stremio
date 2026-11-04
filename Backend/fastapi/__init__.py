import importlib.util

import uvicorn

from Backend.config import Telegram
from Backend.fastapi.main import app

#----- Uvicorn server bound to the FastAPI app
Port = Telegram.PORT
config = uvicorn.Config(
    app=app,
    host="0.0.0.0",
    port=Port,
    loop="uvloop" if importlib.util.find_spec("uvloop") else "auto",
    http="httptools" if importlib.util.find_spec("httptools") else "h11",
    timeout_keep_alive=60,
    timeout_graceful_shutdown=5,
)
server = uvicorn.Server(config)
