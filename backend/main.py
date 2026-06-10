from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI

from backend.api.health import health_check
from backend.config import get_settings
from backend.storage.sqlite import initialize_database


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    initialize_database(settings.database_path)
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="Encoder Parameter Search", version="0.1.0", lifespan=lifespan)
    app.get("/health")(health_check)
    return app


app = create_app()
