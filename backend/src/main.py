from dotenv import load_dotenv
load_dotenv(override=True)  # load OPENCODE_GO_API_KEY before imports that need it

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from src.db.database import init_db
from src.middleware.logging import RequestLoggingMiddleware
from src.scheduler import start_scheduler, stop_scheduler

logger = logging.getLogger("crisis_monitor.main")

# ── Paths (no hardcoded /root/ references) ────────────────────────────────
# main.py lives at src/main.py; parents[1] is the backend/ root.
_BACKEND_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_LOG = str(_BACKEND_ROOT / "server.log")
_LOG_PATH = os.environ.get("CRISIS_LOG_PATH", _DEFAULT_LOG)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown lifecycle — replaces @app.on_event handlers."""
    # Startup
    init_db()
    # Configure root logger format for structured output
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[logging.FileHandler(_LOG_PATH), logging.StreamHandler()],
    )
    # Pipeline log file: captures per-node progress and completions
    pipeline_handler = logging.FileHandler("/tmp/crisis-pipeline.log")
    pipeline_handler.setLevel(logging.INFO)
    pipeline_handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    # Attach to src.agent and src.routes loggers so pipeline progress is captured
    for logger_name in ("src.routes", "src.agent.graph"):
        logging.getLogger(logger_name).addHandler(pipeline_handler)

    start_scheduler()

    yield  # app runs here

    # Shutdown
    stop_scheduler()


app = FastAPI(title="Crisis Monitor", version="0.1.0", lifespan=lifespan)

# ── CORS ─────────────────────────────────────────────────────────────────
# Read allowed origins from env; default to localhost only.
# Add the production IP/domain to CORS_ALLOWED_ORIGINS in .env:
#   CORS_ALLOWED_ORIGINS=http://localhost:3001,http://187.77.130.62:3001
_cors_origins = [
    o.strip()
    for o in os.environ.get("CORS_ALLOWED_ORIGINS", "http://localhost:3001").split(",")
    if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Metrics collection (after CORS so it captures everything) ---
from src.middleware.metrics import MetricsMiddleware

app.add_middleware(MetricsMiddleware)

# --- Structured request logging (must be after CORS so headers are available) ---
app.add_middleware(RequestLoggingMiddleware)


# --- Global exception handler (Layer 1: no stack traces in responses) ---
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    request_id = getattr(request.state, "request_id", "unknown")
    logger.exception("Unhandled exception request_id=%s", request_id)
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "code": "INTERNAL_ERROR",
            "request_id": request_id,
        },
    )


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


# Routes registered below
from src.routes import router
app.include_router(router, prefix="/api")
