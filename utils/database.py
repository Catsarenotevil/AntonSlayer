"""
Database helper
"""

import aiosqlite

DB_FILE = "database.db"

async def init_db():
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS state (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        await db.execute("""
            INSERT OR IGNORE INTO state (key, value)
            VALUES ('last_match_id', NULL)
        """)
        await db.commit()

        print("initialized database")

async def get_last_match_id():
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute(
            "SELECT value FROM state WHERE key = 'last_match_id'"
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None


async def set_last_match_id(match_id: str):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute(
            "UPDATE state SET value = ? WHERE key = 'last_match_id'",
            (match_id,)
        )
        await db.commit()
