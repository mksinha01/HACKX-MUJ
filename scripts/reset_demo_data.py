"""Reset all demo/seeded data from the database and uploaded files.

Deletes ALL records from:
  - face_embeddings
  - photos
  - sightings
  - missing_persons
  - notifications
  - audit_logs

Also cleans up uploaded photo and face-crop files.
Does NOT drop tables, does NOT delete users/agents/cameras schema.
"""
import asyncio
import logging
import shutil
import sys
from pathlib import Path

# Ensure project root is importable
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))
sys.path.insert(0, str(ROOT_DIR / "backend"))

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger("reset_demo_data")


async def reset_all_demo_data() -> None:
    """Delete all seeded/demo records from the SQLite database and clean uploaded files."""
    from sqlalchemy import text
    import app.database as db_module

    # Initialize DB connection (handles fallback to SQLite)
    await db_module.init_db()

    # After init_db, the engine and session factory may have been reassigned (SQLite fallback)
    engine = db_module.engine
    session_factory = db_module.async_session_factory

    logger.info(f"Connected to database: {engine.url}")

    # Tables to purge, in correct FK dependency order (children first)
    tables_to_purge = [
        "notifications",
        "audit_logs",
        "sightings",
        "face_embeddings",
        "photos",
        "missing_persons",
    ]

    async with session_factory() as session:
        async with session.begin():
            for table_name in tables_to_purge:
                try:
                    result = await session.execute(text(f"DELETE FROM {table_name}"))
                    count = result.rowcount
                    logger.info(f"  Deleted {count} rows from '{table_name}'")
                except Exception as e:
                    logger.warning(f"  Could not purge '{table_name}': {e}")

    logger.info("Database records purged successfully.")

    # Clean uploaded files (photos and face crops)
    uploads_dir = ROOT_DIR / "uploads"
    for subfolder in ["photos", "faces", "evidence"]:
        folder = uploads_dir / subfolder
        if folder.exists():
            file_count = sum(1 for f in folder.iterdir() if f.is_file())
            if file_count > 0:
                shutil.rmtree(folder)
                folder.mkdir(parents=True, exist_ok=True)
                logger.info(f"  Cleaned {file_count} files from uploads/{subfolder}/")
            else:
                logger.info(f"  uploads/{subfolder}/ already empty.")
        else:
            logger.info(f"  uploads/{subfolder}/ does not exist, skipping.")

    # Remove stale seeded_test_data.db if present
    stale_db = ROOT_DIR / "seeded_test_data.db"
    if stale_db.exists():
        stale_db.unlink()
        logger.info("  Removed stale seeded_test_data.db")

    await engine.dispose()
    logger.info("\n✅ All demo data has been completely removed!")
    logger.info("   Restart the backend to see a clean, empty dashboard.")


if __name__ == "__main__":
    asyncio.run(reset_all_demo_data())
