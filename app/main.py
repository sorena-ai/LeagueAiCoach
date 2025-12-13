import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.assistant.data import ensure_all_champion_data_exists
from app.auth import routes as auth_routes
from app.config import settings
from app.core.mongodb import close_mongo_client, get_mongo_client
from app.routes import assistant
from app.users import routes as user_routes
from app.utils.datadog_logging import build_datadog_handler

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    force=True,  # Override any existing logging configuration
)

# Explicitly set the root logger level
root_logger = logging.getLogger()
root_logger.setLevel(getattr(logging, settings.log_level.upper()))

# Ensure handlers are configured for console output
if not root_logger.handlers:
    handler = logging.StreamHandler()
    handler.setLevel(getattr(logging, settings.log_level.upper()))
    formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    handler.setFormatter(formatter)
    root_logger.addHandler(handler)

# Attach Datadog logging handler when enabled
if settings.datadog_logs_enabled:
    try:
        datadog_handler = build_datadog_handler(settings)
        if datadog_handler:
            datadog_handler.setFormatter(
                logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
            )
            root_logger.addHandler(datadog_handler)

            # Also attach to uvicorn loggers to capture access logs
            logging.getLogger("uvicorn").addHandler(datadog_handler)
            logging.getLogger("uvicorn.access").addHandler(datadog_handler)

            root_logger.info(
                "Datadog logging enabled for service %s (%s)",
                settings.datadog_service,
                settings.datadog_site,
            )
    except Exception:
        root_logger.exception("Failed to initialize Datadog logging handler")

logging.getLogger("pymongo").setLevel(logging.INFO)
logging.getLogger("motor").setLevel(logging.INFO)

logger = logging.getLogger(__name__)
logger.info(f"Logging configured at level: {settings.log_level.upper()}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager for startup and shutdown events."""
    # Startup
    logger.info("Starting Sensei League of Legends Coach API...")
    logger.info(f"Environment: {settings.environment}")

    # Verify all champion data directories exist with correct structure (172 champions each)
    try:
        ensure_all_champion_data_exists()
    except FileNotFoundError:
        logger.exception("Champion data validation failed")
        raise

    # Ensure MongoDB is reachable
    mongo_client = get_mongo_client()
    try:
        await mongo_client.admin.command("ping")
        logger.info("Connected to MongoDB")
    except Exception:
        logger.exception("Unable to connect to MongoDB")
        raise

    logger.info("Application startup complete")

    yield

    # Shutdown
    logger.info("Shutting down Sensei League of Legends Coach API...")
    close_mongo_client()


# Create FastAPI application
app = FastAPI(
    title="Sensei - League of Legends AI Coach",
    description="AI-powered League of Legends coaching assistant using multimodal analysis",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# Configure CORS
allowed_origins = ["*"] if settings.environment == "development" else settings.allowed_origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(auth_routes.public_router)
app.include_router(auth_routes.router)
app.include_router(user_routes.router)
app.include_router(assistant.router)


@app.get("/")
async def root():
    """Root endpoint."""
    return JSONResponse(
        status_code=200,
        content={
            "service": "Sensei - League of Legends AI Coach",
            "version": "1.0.0",
            "status": "running",
            "docs": "/docs",
        },
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.environment == "development",
    )
