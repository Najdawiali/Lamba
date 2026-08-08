"""
Full reset script — nukes PostgreSQL tables + OpenSearch index, then re-seeds.
"""
import asyncio
import sys
import os
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


async def nuke():
    from app.database import engine, Base
    from app.config import settings

    # 2. Nuke PostgreSQL tables
    logger.info("=== Dropping all PostgreSQL tables ===")
    # Import all models so Base.metadata knows about them
    import app.models  # noqa: F401
    from sqlalchemy import text
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        logger.info("All tables dropped.")
        # Recreate extensions
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis;"))
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
        logger.info("Extensions ensured.")

    await engine.dispose()
    logger.info("=== Database fully wiped ===")


if __name__ == "__main__":
    asyncio.run(nuke())
