from dotenv import load_dotenv
load_dotenv()  # load OPENCODE_GO_API_KEY before imports that need it

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.db.database import init_db

app = FastAPI(title="Crisis Monitor", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup():
    init_db()


@app.get("/health")
async def health():
    return {"status": "ok"}


# Routes registered below
from src.routes import router
app.include_router(router, prefix="/api")
