import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from dotenv import load_dotenv

# Load .env into process environment BEFORE any other imports use it (LiteLLM needs this)
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# Configure LiteLLM retries for transient errors (Anthropic 529 overloaded)
import litellm
litellm.num_retries = 3
litellm.retry_after = 5  # seconds between retries

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import engine, Base, _is_sqlite
from app.websocket_manager import ws_manager
from app.adk.agents.persistence import set_ws_manager
from app.adk.loop import start_loop, request_shutdown
from app.api import agents, trades, signals, market, ws

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    if _is_sqlite:
        logger.info("Creating database tables (SQLite)...")
        Base.metadata.create_all(bind=engine)
    else:
        logger.info("Using PostgreSQL — tables managed via schema.sql")

    # Wire up WebSocket manager to persistence agent
    set_ws_manager(ws_manager)

    # Start trading loop
    logger.info("Starting trading loop...")
    loop_task = start_loop()

    yield

    # Shutdown
    logger.info("Shutting down trading loop...")
    request_shutdown()
    loop_task.cancel()


app = FastAPI(
    title="Crypto Trading Mission Control",
    version="0.1.0",
    lifespan=lifespan,
)

cors_origins = os.getenv("CORS_ORIGIN", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(agents.router)
app.include_router(trades.router)
app.include_router(signals.router)
app.include_router(market.router)
app.include_router(ws.router)


@app.get("/api/health")
def health():
    return {"status": "ok", "version": "0.1.0"}
