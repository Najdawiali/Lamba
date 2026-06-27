import asyncio
import logging
from dotenv import load_dotenv
load_dotenv()

from app.database import engine, Base
from app.models.chat import ChatSession, ChatMessage
from app.models import *

async def create_tables():
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)
    logger.info("Creating tables...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Tables created.")

if __name__ == "__main__":
    asyncio.run(create_tables())
