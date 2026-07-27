import asyncio
import asyncpg
import structlog
from src.config import settings

logger = structlog.get_logger()


async def initialize_database():
    """Reads sql/init_schema.sql and applies hypertables and indexes to TimescaleDB."""
    logger.info(
        "Connecting to TimescaleDB...",
        host=settings.POSTGRES_HOST,
        db=settings.POSTGRES_DB,
    )

    try:
        conn = await asyncpg.connect(
            user=settings.POSTGRES_USER,
            password=settings.POSTGRES_PASSWORD,
            database=settings.POSTGRES_DB,
            host=settings.POSTGRES_HOST,
            port=settings.POSTGRES_PORT,
        )

        with open("sql/init_schema.sql", "r") as f:
            schema_sql = f.read()

        logger.info("Executing database schema initialization...")
        await conn.execute("DROP TABLE IF EXISTS trade_signals, model_pricings, play_events, odds_ticks CASCADE;")
        await conn.execute(schema_sql)
        await conn.close()
        logger.info("✅ TimescaleDB Schema Initialized Successfully!")

    except Exception as e:
        logger.warning("Database connection failed (Docker container starting?):", error=str(e))


if __name__ == "__main__":
    asyncio.run(initialize_database())
