import asyncio
import os
import sys
from pathlib import Path
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

# Default connection URL:
# When running inside the Docker network (splitbites-api): splitbites-postgres:5432
# When running from host (hp-mini): localhost:5433
DEFAULT_DB_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@splitbites-postgres:5432/splitbites"
    if os.path.exists("/.dockerenv")
    else "postgresql+asyncpg://postgres:postgres@localhost:5433/splitbites"
)

SCHEMA_CANDIDATES = [
    Path(__file__).parent / "schema.sql",
    Path("/app/app/database/schema.sql"),
    Path("/app/database/schema.sql"),
    Path(__file__).resolve().parents[2] / "schema.sql",
    Path("/home/tbannon80/splitbites/app/database/schema.sql"),
    Path("/home/tbannon80/schema.sql"),
]

def load_schema_sql() -> str:
    for candidate in SCHEMA_CANDIDATES:
        if candidate.is_file():
            print(f"[init_db] Reading PostgreSQL schema from: {candidate}")
            return candidate.read_text(encoding="utf-8")
    raise FileNotFoundError(f"Could not locate schema.sql in candidates: {SCHEMA_CANDIDATES}")

def parse_sql_statements(sql_content: str) -> list[str]:
    """Parse raw SQL content into clean executable SQL statements."""
    statements = []
    current = []
    for line in sql_content.splitlines():
        trimmed = line.strip()
        if trimmed.startswith("--") or not trimmed:
            continue
        current.append(line)
        if trimmed.endswith(";"):
            stmt = "\n".join(current).strip()
            if stmt:
                statements.append(stmt)
            current = []
    if current:
        stmt = "\n".join(current).strip()
        if stmt:
            statements.append(stmt)
    return statements

async def init_database(db_url: str = DEFAULT_DB_URL):
    print(f"[init_db] Initializing SplitBites database using asyncpg...")
    print(f"[init_db] Target Database URL: {db_url}")

    schema_sql = load_schema_sql()
    statements = parse_sql_statements(schema_sql)
    print(f"[init_db] Parsed {len(statements)} SQL statements from schema.")

    engine = create_async_engine(db_url, echo=False)

    try:
        async with engine.begin() as conn:
            for stmt in statements:
                await conn.execute(text(stmt))
        print("[init_db] Schema DDL executed successfully against PostgreSQL container.")

        # Verification check
        await verify_tables(engine)
    finally:
        await engine.dispose()

async def verify_tables(engine):
    print("\n[init_db] ========================================")
    print("[init_db] === Table & Extension Verification ===")
    print("[init_db] ========================================")
    async with engine.connect() as conn:
        # 1. Verify pgvector extension
        res = await conn.execute(text("SELECT extname, extversion FROM pg_extension WHERE extname = 'vector'"))
        row = res.fetchone()
        if row:
            print(f"  [+] Extension 'vector' (pgvector) : ENABLED (v{row[1]})")
        else:
            print("  [-] Extension 'vector' (pgvector) : NOT FOUND")

        # 2. Verify target tables
        required_tables = ["households", "recipes", "meal_plans", "meal_plan_items"]
        res = await conn.execute(
            text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public' ORDER BY table_name"
            )
        )
        existing_tables = set(r[0] for r in res.fetchall())
        print(f"  [+] Total tables detected in database : {len(existing_tables)}")

        print("\n[init_db] Checking required roadmap tables:")
        all_ok = True
        for t in required_tables:
            if t in existing_tables:
                count_res = await conn.execute(text(f"SELECT COUNT(*) FROM {t}"))
                count = count_res.scalar()
                print(f"  * Table '{t}': CREATED & ACTIVE ({count} rows)")
            else:
                print(f"  * Table '{t}': MISSING")
                all_ok = False

        # 3. Verify embedding column in recipes table
        res = await conn.execute(
            text(
                "SELECT column_name, data_type, udt_name FROM information_schema.columns "
                "WHERE table_name = 'recipes' AND column_name = 'embedding'"
            )
        )
        col = res.fetchone()
        if col:
            print(f"\n  [+] Recipe vector embedding column: PRESENT (UDT: {col[2]})")
        else:
            print("\n  [-] Recipe vector embedding column: MISSING")
            all_ok = False

        if all_ok:
            print("\n[init_db] Verification Status: ALL REQUIRED TABLES & PGVECTOR EXTENSION VERIFIED!")
        else:
            print("\n[init_db] Verification Status: SOME CHECKS FAILED!")

if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_DB_URL
    asyncio.run(init_database(url))
