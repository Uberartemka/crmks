from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from routes.index import register_routes
from startup.db_init import startup_init_db
from services.queue_service import init_queue_manager as _init_queue_manager
from db_async import init_async_pool, close_async_pool
from token_store import init_token_store, close_token_store

load_dotenv(override=True)


async def on_startup() -> None:
    startup_init_db()
    # _init_queue_manager()  # disabled on Railway — queue requires PostgreSQL + Chromium
    await init_async_pool()
    await init_token_store()


async def on_shutdown() -> None:
    await close_async_pool()
    await close_token_store()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await on_startup()
    yield
    await on_shutdown()


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_routes(app)
