"""FastAPI server that spawns Pipecat bots for voice sessions."""

import asyncio
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator

import aiohttp
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from luca.bot import create_bot
from luca.utils.config import get_settings
from luca.utils.logging import get_logger, setup_logging

logger = get_logger("bot_runner")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan handler."""
    setup_logging()
    logger.info("Luca bot runner starting up")
    yield
    logger.info("Luca bot runner shutting down")


app = FastAPI(
    title="Luca Bot Runner",
    description="FastAPI server for spawning Pipecat voice AI bots",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ConnectResponse(BaseModel):
    """Response model for the /connect endpoint."""

    room_url: str
    token: str


async def create_daily_room() -> dict[str, Any]:
    """Create a new Daily room via the REST API."""
    settings = get_settings()

    if not settings.daily_api_key:
        raise HTTPException(status_code=500, detail="DAILY_API_KEY not configured")

    async with aiohttp.ClientSession() as session:
        headers = {"Authorization": f"Bearer {settings.daily_api_key}"}
        async with session.post(
            "https://api.daily.co/v1/rooms",
            headers=headers,
            json={
                "properties": {
                    "exp": None,  # Room doesn't expire
                    "enable_chat": False,
                    "enable_screenshare": False,
                    "start_video_off": True,
                    "start_audio_off": False,
                }
            },
        ) as response:
            if response.status != 200:
                error_text = await response.text()
                logger.error(f"Failed to create Daily room: {error_text}")
                raise HTTPException(status_code=500, detail="Failed to create room")
            return await response.json()


async def get_daily_token(room_name: str) -> str:
    """Get a meeting token for a Daily room."""
    settings = get_settings()

    async with aiohttp.ClientSession() as session:
        headers = {"Authorization": f"Bearer {settings.daily_api_key}"}
        async with session.post(
            "https://api.daily.co/v1/meeting-tokens",
            headers=headers,
            json={"properties": {"room_name": room_name}},
        ) as response:
            if response.status != 200:
                error_text = await response.text()
                logger.error(f"Failed to get Daily token: {error_text}")
                raise HTTPException(status_code=500, detail="Failed to get token")
            data = await response.json()
            return data["token"]


@app.get("/health")
async def health() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "healthy"}


@app.post("/connect", response_model=ConnectResponse)
async def connect() -> ConnectResponse:
    """Create a new room and spawn a bot to join it."""
    # Create room
    room_data = await create_daily_room()
    room_url = room_data["url"]
    room_name = room_data["name"]

    logger.info(f"Created room: {room_name}")

    # Get token for the client
    token = await get_daily_token(room_name)

    # Spawn bot in background
    asyncio.create_task(spawn_bot(room_url, room_name))

    return ConnectResponse(room_url=room_url, token=token)


async def spawn_bot(room_url: str, room_name: str) -> None:
    """Spawn a bot to join the given room."""
    # Get a separate token for the bot
    bot_token = await get_daily_token(room_name)

    logger.info(f"Spawning bot for room: {room_name}")

    try:
        await create_bot(room_url, bot_token)
    except Exception as e:
        logger.error(f"Bot error: {e}")
    finally:
        logger.info(f"Bot finished for room: {room_name}")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=7860)
