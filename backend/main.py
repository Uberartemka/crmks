from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from routes.index import register_routes
from startup.db_init import startup_init_db
from services.queue_service import init_queue_manager as _init_queue_manager

load_dotenv(override=True)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def on_startup() -> None:
    startup_init_db()
    _init_queue_manager()


app.on_event("startup")(on_startup)

register_routes(app)

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
