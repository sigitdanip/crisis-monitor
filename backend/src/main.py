from dotenv import load_dotenv
load_dotenv(override=True)  # load OPENCODE_GO_API_KEY before imports that need it

import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from src.db.database import init_db
from src.middleware.logging import RequestLoggingMiddleware

logger = logging.getLogger("crisis_monitor.main")

app = FastAPI(title="Crisis Monitor", version="0.1.0")

# --- CORS ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3001", "http://187.77.130.62:3001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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


@app.on_event("startup")
async def startup() -> None:
    init_db()
    # Configure root logger format for structured output
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[logging.FileHandler("/root/crisis-monitor/backend/server.log"), logging.StreamHandler()],
    )


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


# Routes registered below
from src.routes import router
app.include_router(router, prefix="/api")
