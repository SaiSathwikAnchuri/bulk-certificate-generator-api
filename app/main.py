"""Main application entry point."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.database import Base, engine
import app.models  # noqa: F401 - registers models with Base.metadata
from app.routes.jobs import router as jobs_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan context manager for startup and shutdown events."""
    try:
        Base.metadata.create_all(bind=engine)
    except Exception as exc:
        print(f"[Warning] Database tables could not be initialized on startup: {exc}")
    yield


def create_app() -> FastAPI:
    """Application factory for creating and configuring the FastAPI instance."""
    app = FastAPI(
        title="Bulk Certificate Generator API",
        description="Scalable backend API to generate and track certificates in bulk.",
        version="1.0.0",
        lifespan=lifespan,
    )

    @app.get("/health", tags=["Health"])
    def health_check() -> dict[str, str]:
        """Health check endpoint to verify service uptime."""
        return {"status": "ok"}

    app.include_router(jobs_router)

    return app


app = create_app()
