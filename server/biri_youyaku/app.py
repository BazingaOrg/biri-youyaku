from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from biri_youyaku.config import settings
from biri_youyaku.db import init_db
from biri_youyaku.jobs.runner import recover_unfinished_jobs
from biri_youyaku.logging import configure_logging
from biri_youyaku.routes import config_router, healthz_router, jobs_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    init_db()
    recover_unfinished_jobs()
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="Biri-Youyaku Server", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(config_router)
    app.include_router(healthz_router)
    app.include_router(jobs_router)
    return app


app = create_app()
